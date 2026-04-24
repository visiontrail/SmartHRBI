from __future__ import annotations

from pathlib import Path

import pytest

from apps.api.chart_query_agent import (
    ChartQueryAgent,
    ChartQueryAgentError,
    SnapshotDuckDBCache,
    SnapshotMCPTools,
)
from apps.api.published_pages import PublishedChartSnapshot, PublishedPage, SnapshotWriter


def test_snapshot_duckdb_cache_evicts_least_recently_used_page(tmp_path: Path) -> None:
    cache = SnapshotDuckDBCache(max_entries=1, ttl_seconds=1800)
    first_page = _write_page(tmp_path, page_id="page-a", workspace_id="workspace-a", chart_id="employees")
    second_page = _write_page(tmp_path, page_id="page-b", workspace_id="workspace-b", chart_id="finance")

    first_entry = cache.get(page=first_page)
    assert first_entry.tables["employees"].table_name == "employees"

    second_entry = cache.get(page=second_page)
    assert second_entry.tables["finance"].table_name == "finance"
    assert list(cache._entries) == ["page-b"]  # noqa: SLF001


def test_chart_query_agent_injects_selected_chart_context(tmp_path: Path) -> None:
    page = _write_page(tmp_path, page_id="page-a", workspace_id="workspace-a", chart_id="employees")
    cache = SnapshotDuckDBCache(max_entries=10, ttl_seconds=1800)
    agent = ChartQueryAgent(tools=SnapshotMCPTools(cache=cache))

    prompt = agent.build_system_prompt(page=page, chart_id="employees")

    assert "Active chart context" in prompt
    assert "table_name: employees" in prompt
    assert "department, headcount" in prompt


def test_snapshot_query_tool_rejects_write_sql(tmp_path: Path) -> None:
    page = _write_page(tmp_path, page_id="page-a", workspace_id="workspace-a", chart_id="employees")
    tools = SnapshotMCPTools(cache=SnapshotDuckDBCache(max_entries=10, ttl_seconds=1800))

    result = tools.query_snapshot_table(page=page, sql="SELECT department, headcount FROM employees")
    assert result["rows"] == [{"department": "HR", "headcount": 4}]

    with pytest.raises(ChartQueryAgentError) as exc_info:
        tools.query_snapshot_table(page=page, sql="DELETE FROM employees")
    assert exc_info.value.code == "READ_ONLY_ONLY_SELECT"


def _write_page(tmp_path: Path, *, page_id: str, workspace_id: str, chart_id: str) -> PublishedPage:
    writer = SnapshotWriter(upload_dir=tmp_path / "uploads", max_rows=200)
    result = writer.write(
        workspace_id=workspace_id,
        version=1,
        layout={"grid": {"columns": 3}},
        sidebar=[],
        charts=[
            PublishedChartSnapshot(
                chart_id=chart_id,
                title="Headcount",
                chart_type="bar",
                spec={"chart_type": "bar", "title": "Headcount"},
                rows=[{"department": "HR", "headcount": 4}],
            )
        ],
        actor_role="viewer",
        published_at="2026-04-24T00:00:00+00:00",
    )
    return PublishedPage(
        id=page_id,
        workspace_id=workspace_id,
        version=1,
        published_at="2026-04-24T00:00:00+00:00",
        published_by="alice",
        manifest_path=str(result.manifest_path),
    )
