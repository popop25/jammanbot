from __future__ import annotations

import logging

from .codex_bridge import CodexBridge
from .config import Settings
from .db import Store
from .slack_bot import JammanSlackBot


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    settings = Settings.load()
    store = Store(settings.db_path)
    codex = CodexBridge(settings)
    JammanSlackBot(settings, store, codex).start()

