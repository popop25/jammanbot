from __future__ import annotations

import logging
import re
from typing import Any

from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
from slack_sdk.errors import SlackApiError

from .codex_bridge import CodexBridge
from .config import Settings
from .db import Store, StoredMessage
from .link_summary import extract_urls, fetch_link_content
from .prompts import build_link_prompt, build_summary_prompt


MENTION_RE = re.compile(r"<@[A-Z0-9]+>")


class JammanSlackBot:
    def __init__(self, settings: Settings, store: Store, codex: CodexBridge) -> None:
        self.settings = settings
        self.store = store
        self.codex = codex
        self.app = App(token=settings.slack_bot_token)
        self.bot_user_id: str | None = None
        self.logger = logging.getLogger("jammanbot")
        self._register_handlers()

    def start(self) -> None:
        auth = self.app.client.auth_test()
        self.bot_user_id = auth.get("user_id")
        self.logger.info("잠만봇 started as %s", self.bot_user_id)
        SocketModeHandler(self.app, self.settings.slack_app_token).start()

    def _register_handlers(self) -> None:
        self.app.event("message")(self._handle_message)
        self.app.event("app_mention")(self._handle_app_mention)

    def _handle_message(self, event: dict[str, Any], body: dict[str, Any], client: Any) -> None:
        team_id = self._team_id(body, event)
        channel_id = event.get("channel")
        if not channel_id:
            return

        message = self._message_from_event(event)
        self.store.upsert_message(team_id, channel_id, message)

        if channel_id not in self.settings.auto_link_channels:
            return
        if message.get("bot_id") or message.get("subtype"):
            return
        text = str(message.get("text") or "")
        if self.bot_user_id and f"<@{self.bot_user_id}>" in text:
            return

        urls = extract_urls(text)
        if not urls:
            return
        url = urls[0]
        if self.store.get_link_summary(team_id, channel_id, url):
            return

        thread_ts = str(message.get("thread_ts") or message.get("ts"))
        try:
            reply = self._summarize_link(team_id, channel_id, url, "자동 링크 요약")
            self._post_reply(client, channel_id, thread_ts, reply)
        except Exception:
            self.logger.exception("automatic link summary failed")

    def _handle_app_mention(
        self,
        event: dict[str, Any],
        body: dict[str, Any],
        client: Any,
    ) -> None:
        team_id = self._team_id(body, event)
        channel_id = event.get("channel")
        if not channel_id:
            return

        self.store.upsert_message(team_id, channel_id, self._message_from_event(event))

        command_text = self._command_text(str(event.get("text") or ""))
        reply_thread_ts = str(event.get("thread_ts") or event.get("ts"))

        try:
            if self._is_link_intent(command_text):
                url = self._pick_url(command_text, team_id, channel_id, reply_thread_ts, client)
                if not url:
                    self._post_reply(
                        client,
                        channel_id,
                        reply_thread_ts,
                        "요약할 링크를 못 찾았어요. 링크를 같이 보내주거나, 링크가 있는 스레드에서 불러주세요.",
                    )
                    return
                reply = self._summarize_link(team_id, channel_id, url, command_text)
            else:
                in_thread = bool(event.get("thread_ts"))
                if in_thread:
                    messages = self._load_thread_from_slack(
                        client, team_id, channel_id, reply_thread_ts
                    )
                    scope_label = "현재 Slack 스레드"
                else:
                    messages = self._load_channel_recent_from_slack(client, team_id, channel_id)
                    scope_label = f"현재 채널 최근 {len(messages)}개 메시지"

                mode = self._summary_mode(command_text)
                prompt = build_summary_prompt(
                    messages,
                    mode=mode,
                    command_text=command_text,
                    scope_label=scope_label,
                )
                reply = self.codex.run(prompt).text

            self._post_reply(client, channel_id, reply_thread_ts, reply)
            user_id = event.get("user")
            if user_id:
                self.store.set_user_catchup(
                    team_id,
                    channel_id,
                    reply_thread_ts,
                    str(user_id),
                    str(event.get("ts") or ""),
                )
        except Exception as exc:
            self.logger.exception("mention handling failed")
            self._post_reply(
                client,
                channel_id,
                reply_thread_ts,
                f"앗, 읽다가 멈췄어요. 원인: {str(exc)[-600:]}",
            )

    def _summarize_link(
        self,
        team_id: str,
        channel_id: str,
        url: str,
        command_text: str,
    ) -> str:
        cached = self.store.get_link_summary(team_id, channel_id, url)
        if cached:
            return cached
        content = fetch_link_content(url)
        prompt = build_link_prompt(content.url, content.title, content.text, command_text)
        summary = self.codex.run(prompt).text
        self.store.save_link_summary(team_id, channel_id, url, summary)
        return summary

    def _pick_url(
        self,
        command_text: str,
        team_id: str,
        channel_id: str,
        thread_ts: str,
        client: Any,
    ) -> str | None:
        urls = extract_urls(command_text)
        if urls:
            return urls[0]
        messages = self._load_thread_from_slack(client, team_id, channel_id, thread_ts)
        for message in reversed(messages):
            urls = extract_urls(message.text)
            if urls:
                return urls[0]
        return None

    def _load_thread_from_slack(
        self,
        client: Any,
        team_id: str,
        channel_id: str,
        thread_ts: str,
    ) -> list[StoredMessage]:
        try:
            response = client.conversations_replies(
                channel=channel_id,
                ts=thread_ts,
                limit=self.settings.max_thread_messages,
            )
            for message in response.get("messages", []):
                self.store.upsert_message(team_id, channel_id, message)
        except SlackApiError:
            self.logger.exception("failed to fetch Slack thread; using local store")
        return self.store.get_thread_messages(
            team_id,
            channel_id,
            thread_ts,
            self.settings.max_thread_messages,
        )

    def _load_channel_recent_from_slack(
        self,
        client: Any,
        team_id: str,
        channel_id: str,
    ) -> list[StoredMessage]:
        try:
            response = client.conversations_history(
                channel=channel_id,
                limit=self.settings.max_channel_messages,
            )
            for message in response.get("messages", []):
                self.store.upsert_message(team_id, channel_id, message)
        except SlackApiError:
            self.logger.exception("failed to fetch channel history; using local store")
        return self.store.get_recent_channel_messages(
            team_id,
            channel_id,
            self.settings.max_channel_messages,
        )

    def _post_reply(self, client: Any, channel_id: str, thread_ts: str, text: str) -> None:
        client.chat_postMessage(
            channel=channel_id,
            thread_ts=thread_ts,
            text=text[:35000],
            unfurl_links=False,
            unfurl_media=False,
        )

    def _command_text(self, text: str) -> str:
        if self.bot_user_id:
            text = text.replace(f"<@{self.bot_user_id}>", "")
        text = MENTION_RE.sub("", text)
        return " ".join(text.split()).strip() or "요약"

    @staticmethod
    def _is_link_intent(text: str) -> bool:
        if extract_urls(text):
            return True
        return any(word in text for word in ["링크", "url", "URL", "이거 요약", "기사"])

    @staticmethod
    def _summary_mode(text: str) -> str:
        if "한줄" in text or "한 줄" in text:
            return "one_line"
        if "자세" in text or "상세" in text or "길게" in text:
            return "detailed"
        return "summary"

    @staticmethod
    def _team_id(body: dict[str, Any], event: dict[str, Any]) -> str:
        return str(body.get("team_id") or event.get("team") or "default")

    @staticmethod
    def _message_from_event(event: dict[str, Any]) -> dict[str, Any]:
        if event.get("subtype") == "message_changed" and isinstance(event.get("message"), dict):
            return event["message"]
        return event

