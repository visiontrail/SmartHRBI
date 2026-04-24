from __future__ import annotations

from pathlib import Path

from apps.api.chart_query_agent import ChartQueryAgent, SnapshotDuckDBCache, SnapshotMCPTools
from apps.api.published_pages import PublishedChartSnapshot, PublishedPage, SnapshotWriter


def test_chart_query_agent_loads_snapshot_and_scopes_sql_to_selected_chart(tmp_path: Path) -> None:
    writer = SnapshotWriter(upload_dir=tmp_path / "uploads", max_rows=200)
    snapshot = writer.write(
        workspace_id="workspace-1",
        version=1,
        layout={"grid": {"columns": 2}},
        sidebar=[],
        charts=[
            PublishedChartSnapshot(
                chart_id="headcount",
                title="Headcount",
                chart_type="bar",
                spec={"chart_type": "bar", "title": "Headcount"},
                rows=[{"department": "HR", "headcount": 4}],
            )
        ],
        actor_role="viewer",
        published_at="2026-04-24T00:00:00+00:00",
    )
    page = PublishedPage(
        id="page-1",
        workspace_id="workspace-1",
        version=1,
        published_at="2026-04-24T00:00:00+00:00",
        published_by="alice",
        manifest_path=str(snapshot.manifest_path),
    )
    tools = SnapshotMCPTools(cache=SnapshotDuckDBCache(max_entries=10, ttl_seconds=1800))
    agent = ChartQueryAgent(tools=tools)

    prompt = agent.build_system_prompt(page=page, chart_id="headcount")
    result = tools.query_snapshot_table(page=page, sql="SELECT headcount FROM headcount")

    assert "table_name: headcount" in prompt
    assert result["rows"] == [{"headcount": 4}]
