from __future__ import annotations

import os
from pathlib import Path

from anthropic import Anthropic

ENV_FILE = Path(__file__).resolve().parent / ".env"


def load_env_file(path: Path) -> None:
    if not path.exists():
        raise FileNotFoundError(f"Env file not found: {path}")

    with path.open("r", encoding="utf-8") as f:
        for raw_line in f:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value


load_env_file(ENV_FILE)

# Avoid blank Anthropic auth token overriding a valid API key.
if os.getenv("ANTHROPIC_AUTH_TOKEN", "").strip() == "":
    os.environ.pop("ANTHROPIC_AUTH_TOKEN", None)

anthropic_base_url = os.getenv("ANTHROPIC_BASE_URL")
ai_api_key = os.getenv("AI_API_KEY")
anthropic_auth_token = os.getenv("ANTHROPIC_AUTH_TOKEN")
model = os.getenv("AI_MODEL", "deepseek-chat")

if not (anthropic_auth_token or ai_api_key):
    raise RuntimeError("Missing AI_API_KEY or ANTHROPIC_AUTH_TOKEN in .env")

client = Anthropic(
    api_key=ai_api_key if ai_api_key else None,
    auth_token=anthropic_auth_token if anthropic_auth_token else None,
    base_url=anthropic_base_url if anthropic_base_url else None,
)

print("Testing Anthropic endpoint")
print(f"base_url={anthropic_base_url}")
print(f"model={model}")
print("Sending a simple request...")

response = client.messages.create(
    model=model,
    max_tokens=1000,
    system="You are a helpful assistant.",
    messages=[
        {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": "Hi, how are you?"
                }
            ]
        }
    ],
)

print("--- response ---")
print(getattr(response, "content", response))
print("--- done ---")
