# ADR-0002 Excel Upload Ingestion Current State

## Context

SmartHRBI's first product promise is "把 Excel 变成可分析的数据资产".
Before refactoring this capability, we need a stable record of the backend
behavior that already exists so future changes can preserve the external
contract intentionally.

This ADR documents the current implementation in:

- `apps/api/main.py`
- `apps/api/datasets.py`
- `apps/api/schema_inference.py`
- `apps/api/tool_calling.py`

It is a current-state ADR rather than a new architecture decision.

## Current API Contract

The backend exposes two dataset endpoints:

1. `POST /datasets/upload`
2. `GET /datasets/{batch_id}/quality-report`

`POST /datasets/upload` accepts multipart form data:

- `user_id`
- `project_id`
- one or more `files`

The route requires `datasets:upload`, then calls `ensure_scope()` so the
authenticated identity can only upload into its permitted user/project scope.
The roles that currently have `datasets:upload` are `admin`, `hr`, and `pm`;
`viewer` can read datasets but cannot upload them.

On success, the upload endpoint returns:

- `batch_id`
- `session_id`
- `dataset_table`
- `file_count`
- `duration_ms`
- `diagnostics`

`GET /datasets/{batch_id}/quality-report` reads the persisted upload metadata
and returns its `quality_report`. Non-admin callers can only read quality
reports for their own project.

## Upload Flow

The upload flow is implemented by `DatasetIngestionService.upload_files()`:

1. Validate that at least one file was supplied.
2. Reject batches larger than `MAX_FILES_PER_BATCH`.
3. Create a random hex `batch_id`.
4. Parse each uploaded file with `_parse_file()`.
5. Merge all parsed DataFrames with `_merge_files()`.
6. Optionally run LLM schema inference on the merged DataFrame.
7. Build a quality report.
8. Create or replace a DuckDB table named `dataset_{batch_id}` in the
   caller's user/project DuckDB session.
9. Persist batch metadata and append an upload event.
10. Return dataset identifiers and diagnostics to the caller.

Failure inside the ingestion service appends a failed upload event and raises
`DatasetUploadError`. The FastAPI route converts that error into an HTTP error
payload with:

- `code`
- `message`
- optional `reasons`

## File Validation And Parsing

The current file limits are:

- allowed extension: `.xlsx`
- max files per batch: `20`
- max file size: `10 MiB`

For each file:

1. The original filename defaults to `uploaded.xlsx` if absent.
2. The extension is checked before bytes are read.
3. Empty files and oversized files are rejected.
4. The raw file is saved under `UPLOAD_DIR/raw/{batch_id}/{safe_filename}`.
5. The file is read with `pandas.read_excel(path, dtype=object)`.
6. An Excel file with no usable sheet data is rejected.

The implementation currently relies on pandas/openpyxl rather than DuckDB's
Excel reader. `read_excel()` is called without an explicit sheet name, so the
default pandas behavior applies.

## Column Normalization

After reading each workbook, the backend normalizes columns with
`_normalize_dataframe()`:

- known aliases map to canonical names such as `employee_id`, `department`,
  `salary`, `hire_date`, `status`, `project`, `manager`, `city`, `region`,
  and `score`;
- aliases include common English headers and a few Chinese headers such as
  `员工编号`, `员工id`, `姓名`, `部门`, `薪资`, `入职日期`, and `离职日期`;
- otherwise, headers are lowercased and converted into safe snake_case-like
  identifiers;
- duplicate normalized names are suffixed with `_2`, `_3`, and so on;
- columns that are not part of the known canonical set are reported as
  `unrecognized_columns`;
- every parsed DataFrame receives a `source_file` column containing the
  original upload filename.

The parser also infers a lightweight per-column type for each file:

- `null`
- `boolean`
- `number`
- `datetime`
- `string`

This type inference is used for diagnostics and quality reporting. It does not
currently coerce the DataFrame columns into typed analytical columns before
loading them into DuckDB.

## Multi-File Merge

Multiple uploaded files are merged with union-by-name semantics:

1. The service builds an ordered superset of all normalized columns.
2. Each file's DataFrame is copied.
3. Missing columns are added with `pd.NA`.
4. Frames are reindexed to the shared column order.
5. Frames are concatenated into one merged DataFrame.

The returned diagnostics include:

- `union_mode: "union_by_name"`
- `source_file_count`
- `result_row_count`
- `result_column_count`
- per-file `unrecognized_columns`

## Optional LLM Schema Inference

After merging, the service may run schema inference through
`apps/api/schema_inference.py`.

Inference runs only when:

- `AI_API_KEY` is configured; and
- the ratio of unrecognized columns to total columns is at least `0.4`.

When triggered, the service sends sampled values from the merged DataFrame to an
OpenAI-compatible `/chat/completions` endpoint. The model is asked to return a
JSON schema overlay containing:

- canonical English snake_case column names;
- semantic types;
- human labels;
- simple auto-derived metrics.

If inference succeeds and returns columns:

1. The merged DataFrame is renamed with the inferred canonical column names.
2. parsed-file metadata is updated to reflect the new names.
3. a sidecar overlay is saved as
   `UPLOAD_DIR/metadata/{batch_id}_schema_overlay.json`.

If inference fails, times out, returns invalid JSON, or the HTTP call fails, the
upload continues without schema enrichment.

At query time, `ToolCallingService._effective_compiler()` loads this overlay
from the `dataset_table`'s batch id and merges overlay metrics into the base
semantic registry when possible.

## DuckDB Session Storage

Uploaded analytical data is stored in DuckDB files under:

`UPLOAD_DIR/duckdb/{session_id}.duckdb`

The `session_id` is derived from:

- sanitized `user_id`
- sanitized `project_id`
- a short SHA-1 digest of `user_id::project_id`

Each user/project pair receives a separate DuckDB file. Uploading creates or
replaces a table named:

`dataset_{batch_id}`

The merged pandas DataFrame is registered as `upload_df`, then materialized with:

`CREATE OR REPLACE TABLE "{dataset_table}" AS SELECT * FROM upload_df`

The service keeps a per-session Python lock so concurrent operations against
the same user/project DuckDB file are serialized in-process.

## Metadata And Events

For every successful upload, metadata is persisted to:

`UPLOAD_DIR/metadata/{batch_id}.json`

The metadata includes:

- batch identity and owner scope;
- session id and dataset table name;
- creation time and duration;
- per-file storage path, size, row count, normalized columns, column mapping,
  and unrecognized columns;
- merge diagnostics;
- quality report.

The service also appends JSON lines to:

`UPLOAD_DIR/upload_events.log`

The FastAPI route separately writes structured audit events for upload success
and failure through the audit logger.

## Quality Report

The quality report is computed from the parsed files and merged DataFrame.

It contains:

- batch id and generation time;
- summary file, row, and column counts;
- file-level row count, column count, null rates, inferred column types, and
  unrecognized columns;
- column-level null rate, duplicate rate, type drift flag, types by file, and
  participating files;
- blocking issues;
- `can_publish_to_semantic_layer`.

Current blocking issue rules:

- `type_drift`: high severity when a column has inconsistent non-null inferred
  types across files;
- `high_null_rate`: medium severity when a column's null rate is at least 95%.

`can_publish_to_semantic_layer` is false only when at least one high-severity
blocking issue exists.

## Security And Isolation

The upload backend currently enforces:

- RBAC permission check through `require_permission("datasets:upload")`;
- user/project scope validation through `ensure_scope()`;
- project-level access check for quality report reads;
- separate DuckDB files per user/project session;
- audit events for upload success, upload failure, and denied quality-report
  access.

Downstream semantic query and agent-tool execution still apply their own
read-only SQL guard, RLS injection, sensitive-column filtering, redaction, and
audit logging. The upload step itself does not run those query-time controls;
it only creates the dataset table and metadata used later by the query stack.

## Known Constraints

The current implementation has these important boundaries:

- only `.xlsx` is accepted; `.xls`, `.csv`, and `.tsv` are rejected;
- a batch cannot exceed 20 files;
- an individual file cannot exceed 10 MiB;
- parsing uses pandas/openpyxl and reads with default sheet behavior;
- uploaded raw files and metadata are stored on local disk under `UPLOAD_DIR`;
- DuckDB session isolation is local-file based, not centralized database
  tenancy;
- schema inference is opportunistic and non-blocking;
- quality reporting identifies type drift and high null rates, but does not
  perform full profiling, deduplication, primary-key discovery, or semantic
  model publication.

## Refactor Baseline

Any refactor of "把 Excel 变成可分析的数据资产" should deliberately preserve or
replace these externally visible behaviors:

- the upload and quality-report endpoint shapes;
- `dataset_table` naming or an explicit migration path for callers;
- union-by-name multi-file ingestion;
- per-user/project isolation;
- persisted raw files, metadata, events, and quality report availability;
- diagnostics fields consumed by the frontend;
- non-blocking schema inference failure behavior;
- permission and audit behavior.

