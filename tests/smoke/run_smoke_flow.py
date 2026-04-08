#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import tempfile
import time
from pathlib import Path
from typing import Any

import httpx
import pandas as pd

XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run SmartHRBI smoke flow")
    parser.add_argument("--api-base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--web-base-url", default="http://127.0.0.1:3000")
    parser.add_argument("--timeout-seconds", type=int, default=90)
    parser.add_argument("--user-id", default="smoke-hr")
    parser.add_argument("--project-id", default="smoke-project")
    parser.add_argument("--role", default="hr")
    return parser.parse_args()


def wait_for_http_ok(client: httpx.Client, url: str, timeout_seconds: int) -> None:
    deadline = time.time() + timeout_seconds
    last_error = "unknown"
    while time.time() < deadline:
        try:
            response = client.get(url)
            if response.status_code == 200:
                return
            last_error = f"status={response.status_code}"
        except Exception as exc:  # noqa: BLE001
            last_error = str(exc)
        time.sleep(1)
    raise RuntimeError(f"timeout waiting for {url}: {last_error}")


def parse_sse(raw: str) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for frame in raw.split("\n\n"):
        frame = frame.strip()
        if not frame:
            continue
        event = "message"
        data_lines: list[str] = []
        event_id: str | None = None

        for line in frame.splitlines():
            if line.startswith("id:"):
                event_id = line.split(":", 1)[1].strip()
                continue
            if line.startswith("event:"):
                event = line.split(":", 1)[1].strip()
                continue
            if line.startswith("data:"):
                data_lines.append(line.split(":", 1)[1].strip())

        if not data_lines:
            continue

        merged = "\n".join(data_lines)
        payload: Any
        try:
            payload = json.loads(merged)
        except json.JSONDecodeError:
            payload = {"raw": merged}
        events.append({"id": event_id, "event": event, "data": payload})
    return events


def build_excel_files(workdir: Path) -> list[Path]:
    first = pd.DataFrame(
        [
            {
                "employee_id": "E-1001",
                "employee_name": "Alice",
                "department": "HR",
                "status": "active",
                "salary": 12000,
                "region": "CN-East",
            },
            {
                "employee_id": "E-1002",
                "employee_name": "Bob",
                "department": "PM",
                "status": "active",
                "salary": 13500,
                "region": "CN-East",
            },
        ]
    )
    second = pd.DataFrame(
        [
            {
                "Name": "Cindy",
                "Employee ID": "E-1003",
                "Dept": "HR",
                "State": "inactive",
                "Project": "Nebula",
                "Score": 82,
            },
            {
                "Name": "David",
                "Employee ID": "E-1004",
                "Dept": "PM",
                "State": "active",
                "Project": "Galaxy",
                "Score": 91,
            },
        ]
    )

    first_file = workdir / "employees_a.xlsx"
    second_file = workdir / "employees_b.xlsx"
    first.to_excel(first_file, index=False)
    second.to_excel(second_file, index=False)
    return [first_file, second_file]


def main() -> int:
    args = parse_args()

    api_base_url = args.api_base_url.rstrip("/")
    web_base_url = args.web_base_url.rstrip("/")

    with httpx.Client(timeout=40.0) as client:
        wait_for_http_ok(client, f"{api_base_url}/healthz", args.timeout_seconds)
        wait_for_http_ok(client, web_base_url, args.timeout_seconds)

        login_response = client.post(
            f"{api_base_url}/auth/login",
            json={
                "user_id": args.user_id,
                "project_id": args.project_id,
                "role": args.role,
                "department": "HR",
                "clearance": 2,
            },
        )
        login_response.raise_for_status()
        token = login_response.json().get("access_token")
        if not token:
            raise RuntimeError("missing access_token")

        auth_headers = {"Authorization": f"Bearer {token}"}

        with tempfile.TemporaryDirectory(prefix="smarthrbi-smoke-") as tmp_dir:
            files = build_excel_files(Path(tmp_dir))
            upload_files = [
                ("files", (file_path.name, file_path.read_bytes(), XLSX_MIME))
                for file_path in files
            ]
            upload_response = client.post(
                f"{api_base_url}/datasets/upload",
                headers=auth_headers,
                data={"user_id": args.user_id, "project_id": args.project_id},
                files=upload_files,
            )
            upload_response.raise_for_status()
            upload_payload = upload_response.json()

        dataset_table = str(upload_payload.get("dataset_table", ""))
        batch_id = str(upload_payload.get("batch_id", ""))
        if not dataset_table or not batch_id:
            raise RuntimeError("upload response missing dataset_table or batch_id")

        semantic_response = client.post(
            f"{api_base_url}/semantic/query",
            headers=auth_headers,
            json={
                "user_id": args.user_id,
                "project_id": args.project_id,
                "dataset_table": dataset_table,
                "metric": "headcount_total",
                "group_by": ["department"],
                "role": args.role,
                "department": "HR",
                "clearance": 2,
            },
        )
        semantic_response.raise_for_status()
        semantic_payload = semantic_response.json()
        if int(semantic_payload.get("row_count", 0)) <= 0:
            raise RuntimeError("semantic query returned no rows")

        stream_response = client.post(
            f"{api_base_url}/chat/stream",
            headers=auth_headers,
            json={
                "user_id": args.user_id,
                "project_id": args.project_id,
                "dataset_table": dataset_table,
                "message": "headcount by department",
                "conversation_id": "smoke-conversation",
                "role": args.role,
                "department": "HR",
                "clearance": 2,
            },
        )
        stream_response.raise_for_status()

        stream_events = parse_sse(stream_response.text)
        if not stream_events:
            raise RuntimeError("chat stream produced no events")

        final_events = [event for event in stream_events if event["event"] == "final"]
        spec_events = [event for event in stream_events if event["event"] == "spec"]
        if not final_events or not spec_events:
            raise RuntimeError("chat stream missing spec/final events")

        final_payload = final_events[-1]["data"]
        if not isinstance(final_payload, dict) or final_payload.get("status") != "completed":
            raise RuntimeError(f"chat stream final status is not completed: {final_payload}")

        spec_payload = spec_events[-1]["data"]
        if not isinstance(spec_payload, dict) or not isinstance(spec_payload.get("spec"), dict):
            raise RuntimeError("chat stream spec payload invalid")

        save_response = client.post(
            f"{api_base_url}/views",
            headers=auth_headers,
            json={
                "user_id": args.user_id,
                "project_id": args.project_id,
                "dataset_table": dataset_table,
                "role": args.role,
                "department": "HR",
                "clearance": 2,
                "title": "Smoke View",
                "conversation_id": "smoke-conversation",
                "ai_state": {
                    "messages": [
                        {"id": "smoke-user", "role": "user", "text": "headcount by department"},
                        {
                            "id": "smoke-assistant",
                            "role": "assistant",
                            "text": str(final_payload.get("text", "")),
                        },
                    ],
                    "active_spec": spec_payload.get("spec"),
                    "dataset_table": dataset_table,
                },
            },
        )
        save_response.raise_for_status()
        save_payload = save_response.json()
        view_id = str(save_payload.get("view_id", ""))
        if not view_id:
            raise RuntimeError("save view response missing view_id")

        share_response = client.get(f"{api_base_url}/share/{view_id}", headers=auth_headers)
        share_response.raise_for_status()
        share_payload = share_response.json()
        if str(share_payload.get("view_id", "")) != view_id:
            raise RuntimeError("share payload view_id mismatch")

        summary = {
            "batch_id": batch_id,
            "dataset_table": dataset_table,
            "semantic_rows": semantic_payload.get("row_count", 0),
            "view_id": view_id,
            "share_path": share_payload.get("share_path"),
            "stream_events": len(stream_events),
        }
        print(json.dumps(summary, ensure_ascii=False))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
