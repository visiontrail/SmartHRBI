from __future__ import annotations

from dataclasses import dataclass

from sqlglot import exp, parse, parse_one
from sqlglot.errors import ParseError


class SQLGuardError(Exception):
    def __init__(self, *, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message

    def to_detail(self) -> dict[str, str]:
        return {"code": self.code, "message": self.message}


class RLSError(Exception):
    def __init__(self, *, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message

    def to_detail(self) -> dict[str, str]:
        return {"code": self.code, "message": self.message}


class QueryAccessError(Exception):
    def __init__(self, *, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message

    def to_detail(self) -> dict[str, str]:
        return {"code": self.code, "message": self.message}


@dataclass(slots=True)
class AccessContext:
    user_id: str
    role: str
    department: str | None
    clearance: int = 0


class SQLReadOnlyValidator:
    _FORBIDDEN_TYPES = (
        exp.Delete,
        exp.Update,
        exp.Insert,
        exp.Drop,
        exp.Create,
        exp.Alter,
        exp.Merge,
        exp.TruncateTable,
        exp.Command,
    )

    def __init__(
        self,
        *,
        allowed_tables: set[str] | None = None,
        sensitive_tables: set[str] | None = None,
        sensitive_columns: set[str] | None = None,
        allowed_columns_by_table: dict[str, set[str]] | None = None,
    ) -> None:
        self.allowed_tables = _normalize_set(allowed_tables)
        self.sensitive_tables = _normalize_set(sensitive_tables)
        self.sensitive_columns = _normalize_set(sensitive_columns)
        self.allowed_columns_by_table = {
            key.lower(): {item.lower() for item in values}
            for key, values in (allowed_columns_by_table or {}).items()
        }

    def validate(self, sql: str) -> None:
        statement = self._parse_single_statement(sql)
        self._assert_select_only(statement)
        self._assert_tables(statement)
        self._assert_columns(statement)

    def _parse_single_statement(self, sql: str) -> exp.Expression:
        try:
            statements = parse(sql, read="duckdb")
        except ParseError as exc:
            raise SQLGuardError(code="SQL_PARSE_ERROR", message="SQL syntax is invalid") from exc

        if len(statements) != 1:
            raise SQLGuardError(
                code="MULTI_STATEMENT_NOT_ALLOWED",
                message="Only one SELECT statement is allowed",
            )
        return statements[0]

    def _assert_select_only(self, statement: exp.Expression) -> None:
        for forbidden in self._FORBIDDEN_TYPES:
            if list(statement.find_all(forbidden)):
                raise SQLGuardError(
                    code="READ_ONLY_ONLY_SELECT",
                    message="Only read-only SELECT statements are allowed",
                )

        if not list(statement.find_all(exp.Select)):
            raise SQLGuardError(
                code="READ_ONLY_ONLY_SELECT",
                message="Only read-only SELECT statements are allowed",
            )

    def _assert_tables(self, statement: exp.Expression) -> None:
        cte_aliases = {
            cte.alias_or_name.lower()
            for cte in statement.find_all(exp.CTE)
            if cte.alias_or_name
        }

        table_names: set[str] = set()
        for table in statement.find_all(exp.Table):
            table_name = table.name.lower()
            if table_name in cte_aliases:
                continue
            table_names.add(table_name)

        for table_name in table_names:
            if table_name in self.sensitive_tables:
                raise SQLGuardError(
                    code="TABLE_FORBIDDEN",
                    message="Query touches a restricted data source",
                )
            if self.allowed_tables and table_name not in self.allowed_tables:
                raise SQLGuardError(
                    code="TABLE_NOT_ALLOWED",
                    message="Query touches a non-whitelisted data source",
                )

    def _assert_columns(self, statement: exp.Expression) -> None:
        alias_map, table_names = self._collect_table_aliases(statement)

        for column in statement.find_all(exp.Column):
            column_name = column.name.lower()
            if column_name in self.sensitive_columns:
                raise SQLGuardError(
                    code="COLUMN_FORBIDDEN",
                    message="Query touches a restricted data column",
                )

            if not self.allowed_columns_by_table:
                continue

            table_name = column.table.lower() if column.table else None
            resolved_table = alias_map.get(table_name, table_name) if table_name else None
            if not resolved_table and len(table_names) == 1:
                resolved_table = next(iter(table_names))

            if not resolved_table:
                continue

            allowed_columns = self.allowed_columns_by_table.get(resolved_table)
            if allowed_columns and column_name not in allowed_columns:
                raise SQLGuardError(
                    code="COLUMN_NOT_ALLOWED",
                    message="Query touches a non-whitelisted data column",
                )

    def _collect_table_aliases(self, statement: exp.Expression) -> tuple[dict[str, str], set[str]]:
        aliases: dict[str, str] = {}
        table_names: set[str] = set()

        cte_aliases = {
            cte.alias_or_name.lower()
            for cte in statement.find_all(exp.CTE)
            if cte.alias_or_name
        }

        for table in statement.find_all(exp.Table):
            table_name = table.name.lower()
            if table_name in cte_aliases:
                continue

            table_names.add(table_name)
            aliases[table_name] = table_name

            alias_name = table.alias
            if alias_name:
                aliases[alias_name.lower()] = table_name

        return aliases, table_names


class RLSInjector:
    def __init__(
        self,
        *,
        department_column: str = "department",
        status_column: str = "status",
        enforce_viewer_status: bool = True,
    ) -> None:
        self.department_column = department_column
        self.status_column = status_column
        self.enforce_viewer_status = enforce_viewer_status

    def inject(self, sql: str, *, context: AccessContext) -> str:
        condition = self._build_condition(context)
        if condition is None:
            return sql

        try:
            statement = parse_one(sql, read="duckdb")
        except ParseError as exc:
            raise RLSError(code="SQL_PARSE_ERROR", message="SQL syntax is invalid") from exc

        select = statement if isinstance(statement, exp.Select) else statement.find(exp.Select)
        if select is None:
            raise RLSError(
                code="RLS_UNSUPPORTED_QUERY",
                message="Only SELECT queries can be scoped",
            )

        current_where = select.args.get("where")
        if current_where:
            combined = exp.and_(current_where.this, condition)
            select.set("where", exp.Where(this=combined))
        else:
            select.set("where", exp.Where(this=condition))

        return statement.sql(dialect="duckdb")

    def _build_condition(self, context: AccessContext) -> exp.Expression | None:
        role = context.role.strip().lower()
        if role == "admin" or context.clearance >= 9:
            return None

        if not context.department:
            raise RLSError(
                code="RLS_CONTEXT_MISSING",
                message="Unable to evaluate access scope for this request",
            )

        condition = exp.EQ(
            this=exp.column(self.department_column),
            expression=exp.Literal.string(context.department),
        )

        if role == "viewer" and self.enforce_viewer_status:
            active_condition = exp.EQ(
                this=exp.column(self.status_column),
                expression=exp.Literal.string("active"),
            )
            condition = exp.and_(condition, active_condition)

        return condition


def secure_query_sql(
    sql: str,
    *,
    context: AccessContext,
    guard: SQLReadOnlyValidator,
    rls_injector: RLSInjector,
) -> str:
    scoped_sql = rls_injector.inject(sql, context=context)
    try:
        guard.validate(scoped_sql)
    except SQLGuardError as exc:
        if exc.code in {"TABLE_FORBIDDEN", "TABLE_NOT_ALLOWED", "COLUMN_FORBIDDEN", "COLUMN_NOT_ALLOWED"}:
            raise QueryAccessError(
                code="ACCESS_DENIED",
                message="The requested query exceeds your data access scope.",
            ) from exc
        raise

    return scoped_sql


def _normalize_set(values: set[str] | None) -> set[str]:
    if not values:
        return set()
    return {item.lower() for item in values}
