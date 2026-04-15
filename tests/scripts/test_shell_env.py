from __future__ import annotations

import subprocess
from pathlib import Path
from shlex import quote

ROOT_DIR = Path(__file__).resolve().parents[2]
ENV_LIB_PATH = ROOT_DIR / "scripts" / "lib" / "env.sh"


def run_bash(script: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", "-c", script],
        text=True,
        capture_output=True,
        check=False,
    )


def test_load_env_file_overrides_inherited_values(tmp_path: Path) -> None:
    env_file = tmp_path / "api.env"
    env_file.write_text(
        "\n".join(
            [
                "# Local API env",
                "DATABASE_URL=sqlite:///./data/uploads/state/ai_views.sqlite3",
                "UPLOAD_DIR=./data/uploads",
                'QUOTED_VALUE="hello world"',
            ]
        ),
        encoding="utf-8",
    )

    result = run_bash(
        "\n".join(
            [
                "set -euo pipefail",
                f"source {quote(str(ENV_LIB_PATH))}",
                "export DATABASE_URL=sqlite:////data/uploads/state/ai_views.sqlite3",
                f"load_env_file {quote(str(env_file))}",
                'printf "%s\\n" "$DATABASE_URL"',
                'printf "%s\\n" "$UPLOAD_DIR"',
                'printf "%s\\n" "$QUOTED_VALUE"',
            ]
        )
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == [
        "sqlite:///./data/uploads/state/ai_views.sqlite3",
        "./data/uploads",
        "hello world",
    ]


def test_load_env_file_rejects_invalid_keys(tmp_path: Path) -> None:
    env_file = tmp_path / "api.env"
    env_file.write_text("INVALID-KEY=value\n", encoding="utf-8")

    result = run_bash(
        "\n".join(
            [
                "set -euo pipefail",
                f"source {quote(str(ENV_LIB_PATH))}",
                f"load_env_file {quote(str(env_file))}",
            ]
        )
    )

    assert result.returncode == 1
    assert "Invalid env key" in result.stderr
