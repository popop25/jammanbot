from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from jammanbot.db import Store


class StoreTests(unittest.TestCase):
    def test_get_recent_channel_messages_since(self) -> None:
        with TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / "jammanbot.sqlite3")
            for index, ts in enumerate(["1.0", "2.0", "3.0"], start=1):
                store.upsert_message(
                    "T1",
                    "C1",
                    {
                        "ts": ts,
                        "thread_ts": "root",
                        "user": f"U{index}",
                        "text": f"message {index}",
                    },
                )

            messages = store.get_recent_channel_messages_since("T1", "C1", "1.5", 10)

            self.assertEqual([message.text for message in messages], ["message 2", "message 3"])

    def test_get_thread_messages_since(self) -> None:
        with TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / "jammanbot.sqlite3")
            store.upsert_message("T1", "C1", {"ts": "1.0", "thread_ts": "1.0", "text": "root"})
            store.upsert_message("T1", "C1", {"ts": "2.0", "thread_ts": "1.0", "text": "reply"})
            store.upsert_message("T1", "C1", {"ts": "3.0", "thread_ts": "3.0", "text": "other"})

            messages = store.get_thread_messages_since("T1", "C1", "1.0", "1.5", 10)

            self.assertEqual([message.text for message in messages], ["reply"])


if __name__ == "__main__":
    unittest.main()
