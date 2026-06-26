from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator


@dataclass(frozen=True)
class StoredMessage:
    team_id: str
    channel_id: str
    thread_ts: str
    ts: str
    user_id: str | None
    text: str
    bot_id: str | None
    subtype: str | None


class Store:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.init()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def init(self) -> None:
        with self.connect() as conn:
            conn.executescript(
                """
                PRAGMA journal_mode = WAL;

                CREATE TABLE IF NOT EXISTS messages (
                    team_id TEXT NOT NULL,
                    channel_id TEXT NOT NULL,
                    thread_ts TEXT NOT NULL,
                    ts TEXT NOT NULL,
                    user_id TEXT,
                    bot_id TEXT,
                    subtype TEXT,
                    text TEXT NOT NULL DEFAULT '',
                    raw_json TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (team_id, channel_id, ts)
                );

                CREATE INDEX IF NOT EXISTS idx_messages_thread
                    ON messages (team_id, channel_id, thread_ts, CAST(ts AS REAL));

                CREATE TABLE IF NOT EXISTS thread_state (
                    team_id TEXT NOT NULL,
                    channel_id TEXT NOT NULL,
                    thread_ts TEXT NOT NULL,
                    summary TEXT NOT NULL DEFAULT '',
                    last_summary_ts TEXT,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (team_id, channel_id, thread_ts)
                );

                CREATE TABLE IF NOT EXISTS user_thread_state (
                    team_id TEXT NOT NULL,
                    channel_id TEXT NOT NULL,
                    thread_ts TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    last_catchup_ts TEXT,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (team_id, channel_id, thread_ts, user_id)
                );

                CREATE TABLE IF NOT EXISTS link_summaries (
                    team_id TEXT NOT NULL,
                    channel_id TEXT NOT NULL,
                    url TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (team_id, channel_id, url)
                );
                """
            )

    def upsert_message(self, team_id: str, channel_id: str, message: dict[str, Any]) -> None:
        ts = str(message.get("ts") or "")
        if not ts:
            return
        thread_ts = str(message.get("thread_ts") or ts)
        text = str(message.get("text") or "")
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO messages (
                    team_id, channel_id, thread_ts, ts, user_id, bot_id, subtype, text, raw_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(team_id, channel_id, ts)
                DO UPDATE SET
                    thread_ts=excluded.thread_ts,
                    user_id=excluded.user_id,
                    bot_id=excluded.bot_id,
                    subtype=excluded.subtype,
                    text=excluded.text,
                    raw_json=excluded.raw_json,
                    updated_at=CURRENT_TIMESTAMP
                """,
                (
                    team_id,
                    channel_id,
                    thread_ts,
                    ts,
                    message.get("user"),
                    message.get("bot_id"),
                    message.get("subtype"),
                    text,
                    json.dumps(message, ensure_ascii=False),
                ),
            )

    def get_thread_messages(
        self,
        team_id: str,
        channel_id: str,
        thread_ts: str,
        limit: int,
    ) -> list[StoredMessage]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM messages
                WHERE team_id = ? AND channel_id = ? AND thread_ts = ?
                ORDER BY CAST(ts AS REAL) ASC
                LIMIT ?
                """,
                (team_id, channel_id, thread_ts, limit),
            ).fetchall()
        return [self._row_to_message(row) for row in rows]

    def get_recent_channel_messages(
        self,
        team_id: str,
        channel_id: str,
        limit: int,
    ) -> list[StoredMessage]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM (
                    SELECT * FROM messages
                    WHERE team_id = ? AND channel_id = ?
                    ORDER BY CAST(ts AS REAL) DESC
                    LIMIT ?
                )
                ORDER BY CAST(ts AS REAL) ASC
                """,
                (team_id, channel_id, limit),
            ).fetchall()
        return [self._row_to_message(row) for row in rows]

    def set_user_catchup(
        self,
        team_id: str,
        channel_id: str,
        thread_ts: str,
        user_id: str,
        last_catchup_ts: str,
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO user_thread_state (
                    team_id, channel_id, thread_ts, user_id, last_catchup_ts
                )
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(team_id, channel_id, thread_ts, user_id)
                DO UPDATE SET
                    last_catchup_ts=excluded.last_catchup_ts,
                    updated_at=CURRENT_TIMESTAMP
                """,
                (team_id, channel_id, thread_ts, user_id, last_catchup_ts),
            )

    def get_link_summary(self, team_id: str, channel_id: str, url: str) -> str | None:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT summary FROM link_summaries
                WHERE team_id = ? AND channel_id = ? AND url = ?
                """,
                (team_id, channel_id, url),
            ).fetchone()
        return None if row is None else str(row["summary"])

    def save_link_summary(
        self,
        team_id: str,
        channel_id: str,
        url: str,
        summary: str,
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO link_summaries (team_id, channel_id, url, summary)
                VALUES (?, ?, ?, ?)
                """,
                (team_id, channel_id, url, summary),
            )

    @staticmethod
    def _row_to_message(row: sqlite3.Row) -> StoredMessage:
        return StoredMessage(
            team_id=str(row["team_id"]),
            channel_id=str(row["channel_id"]),
            thread_ts=str(row["thread_ts"]),
            ts=str(row["ts"]),
            user_id=row["user_id"],
            text=str(row["text"] or ""),
            bot_id=row["bot_id"],
            subtype=row["subtype"],
        )

