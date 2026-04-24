CREATE TABLE IF NOT EXISTS published_pages (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    published_at TEXT NOT NULL,
    published_by TEXT NOT NULL,
    manifest_path TEXT NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_published_pages_workspace_version
    ON published_pages(workspace_id, version);

CREATE INDEX IF NOT EXISTS idx_published_pages_workspace_published
    ON published_pages(workspace_id, published_at DESC);
