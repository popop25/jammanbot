from __future__ import annotations

import os
import shlex
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


def _csv(value: str | None) -> set[str]:
    if not value:
        return set()
    return {item.strip() for item in value.split(",") if item.strip()}


def _int_env(name: str, default: int) -> int:
    raw = os.getenv(name)
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    slack_bot_token: str
    slack_app_token: str
    db_path: Path
    codex_command: str
    codex_args: list[str]
    codex_timeout_seconds: int
    max_thread_messages: int
    max_channel_messages: int
    auto_link_channels: set[str]
    codex_workdir: Path

    @classmethod
    def load(cls) -> "Settings":
        load_dotenv()

        slack_bot_token = os.getenv("SLACK_BOT_TOKEN", "").strip()
        slack_app_token = os.getenv("SLACK_APP_TOKEN", "").strip()
        if not slack_bot_token:
            raise RuntimeError("SLACK_BOT_TOKEN is required.")
        if not slack_app_token:
            raise RuntimeError("SLACK_APP_TOKEN is required.")

        db_path = Path(os.getenv("JAMMANBOT_DB_PATH", "./data/jammanbot.sqlite3"))
        codex_args = shlex.split(
            os.getenv(
                "JAMMANBOT_CODEX_ARGS",
                "exec - --json --ephemeral --skip-git-repo-check",
            )
        )

        return cls(
            slack_bot_token=slack_bot_token,
            slack_app_token=slack_app_token,
            db_path=db_path,
            codex_command=os.getenv("JAMMANBOT_CODEX_COMMAND", "codex"),
            codex_args=codex_args,
            codex_timeout_seconds=_int_env("JAMMANBOT_CODEX_TIMEOUT_SECONDS", 240),
            max_thread_messages=_int_env("JAMMANBOT_MAX_THREAD_MESSAGES", 160),
            max_channel_messages=_int_env("JAMMANBOT_MAX_CHANNEL_MESSAGES", 80),
            auto_link_channels=_csv(os.getenv("JAMMANBOT_AUTO_LINK_CHANNELS")),
            codex_workdir=Path(os.getenv("JAMMANBOT_CODEX_WORKDIR", ".")).resolve(),
        )

