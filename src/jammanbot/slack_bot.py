from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timedelta
import logging
import re
from typing import Any

from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
from slack_sdk.errors import SlackApiError

from .codex_bridge import CodexBridge
from .config import Settings
from .cafeteria import fetch_bundang_menu, format_bundang_menu, is_cafeteria_intent
from .db import Store, StoredMessage
from .link_summary import LinkFetchError, extract_urls, fetch_link_content
from .prompts import build_link_prompt, build_summary_prompt


MENTION_RE = re.compile(r"<@[A-Z0-9]+>")

HELP_TEXT = """음, 잠만봇은 대충 이렇게 쓰면 돼.

채널이나 스레드에서는 나를 멘션해줘.
- `@JammanBot 뭐 얘기했어?`
- `@JammanBot 요약`
- `@JammanBot 못 본 거 요약`
- `@JammanBot 최근 30분만`
- `@JammanBot 1시간 전부터`
- `@JammanBot 오늘 얘기만`
- `@JammanBot 오늘 점심 뭐야?`
- `@JammanBot 한줄로`
- `@JammanBot 자세히`
- `@JammanBot 링크 요약 https://example.com`

DM에서는 멘션 없이 바로 말해도 돼.
- `요약`
- `못 본 거 요약`
- `최근 30분만`
- `오늘 점심 뭐야?`
- `한줄로`
- `링크 요약 https://example.com`

그냥 부르면 "음... 왜?" 정도로만 반응해.
기본은 지금 있는 스레드나 최근 대화만 보고 말해. 다른 스레드 기억까지 뒤지는 건 아직 안 해."""

CHANNEL_STATE_THREAD_TS = "__channel__"


@dataclass(frozen=True)
class BotReply:
    text: str
    mark_catchup: bool = False


class JammanSlackBot:
    def __init__(self, settings: Settings, store: Store, codex: CodexBridge) -> None:
        self.settings = settings
        self.store = store
        self.codex = codex
        self.app = App(token=settings.slack_bot_token)
        self.bot_user_id: str | None = None
        self.logger = logging.getLogger("jammanbot")
        self.executor = ThreadPoolExecutor(
            max_workers=settings.worker_count,
            thread_name_prefix="jammanbot",
        )
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

        if self._should_ignore_message_event(event, message):
            return

        if event.get("channel_type") == "im":
            self._handle_direct_message(event, body, client)
            return

        if channel_id not in self.settings.auto_link_channels:
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
        self._submit_auto_link(client, team_id, channel_id, thread_ts, url)

    def _submit_auto_link(
        self,
        client: Any,
        team_id: str,
        channel_id: str,
        thread_ts: str,
        url: str,
    ) -> None:
        self.executor.submit(self._process_auto_link, client, team_id, channel_id, thread_ts, url)

    def _process_auto_link(
        self,
        client: Any,
        team_id: str,
        channel_id: str,
        thread_ts: str,
        url: str,
    ) -> None:
        try:
            reply = self._summarize_link(team_id, channel_id, url, "자동 링크 요약")
            self._post_reply(client, channel_id, thread_ts, reply)
        except Exception:
            self.logger.exception("automatic link summary failed")

    def _handle_direct_message(
        self,
        event: dict[str, Any],
        body: dict[str, Any],
        client: Any,
    ) -> None:
        team_id = self._team_id(body, event)
        channel_id = event.get("channel")
        if not channel_id:
            return

        command_text = self._command_text(str(event.get("text") or ""))
        reply_thread_ts = str(event.get("thread_ts") or event.get("ts"))
        state_thread_ts = self._state_thread_ts(event)

        self._submit_request(
            kind="dm",
            client=client,
            event=event,
            team_id=team_id,
            channel_id=channel_id,
            reply_thread_ts=reply_thread_ts,
            state_thread_ts=state_thread_ts,
            command_text=command_text,
            direct_message=True,
        )

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
        state_thread_ts = self._state_thread_ts(event)

        self._submit_request(
            kind="mention",
            client=client,
            event=event,
            team_id=team_id,
            channel_id=channel_id,
            reply_thread_ts=reply_thread_ts,
            state_thread_ts=state_thread_ts,
            command_text=command_text,
            direct_message=False,
        )

    def _submit_request(
        self,
        *,
        kind: str,
        client: Any,
        event: dict[str, Any],
        team_id: str,
        channel_id: str,
        reply_thread_ts: str,
        state_thread_ts: str,
        command_text: str,
        direct_message: bool,
    ) -> None:
        self.executor.submit(
            self._process_request_and_reply,
            kind=kind,
            client=client,
            event=event,
            team_id=team_id,
            channel_id=channel_id,
            reply_thread_ts=reply_thread_ts,
            state_thread_ts=state_thread_ts,
            command_text=command_text,
            direct_message=direct_message,
        )

    def _process_request_and_reply(
        self,
        *,
        kind: str,
        client: Any,
        event: dict[str, Any],
        team_id: str,
        channel_id: str,
        reply_thread_ts: str,
        state_thread_ts: str,
        command_text: str,
        direct_message: bool,
    ) -> None:
        try:
            bot_reply = self._reply_for_request(
                client=client,
                team_id=team_id,
                channel_id=channel_id,
                thread_ts=reply_thread_ts,
                state_thread_ts=state_thread_ts,
                command_text=command_text,
                source_event=event,
                direct_message=direct_message,
            )
            self._log_exchange(kind, channel_id, reply_thread_ts, command_text, bot_reply.text)
            self._post_reply(client, channel_id, reply_thread_ts, bot_reply.text)
            user_id = event.get("user")
            if user_id and bot_reply.mark_catchup:
                self.store.set_user_catchup(
                    team_id,
                    channel_id,
                    state_thread_ts,
                    str(user_id),
                    str(event.get("ts") or ""),
                )
        except Exception as exc:
            self.logger.exception("%s handling failed", kind)
            try:
                self._post_reply(
                    client,
                    channel_id,
                    reply_thread_ts,
                    f"앗, 읽다가 멈췄어요. 원인: {str(exc)[-600:]}",
                )
            except Exception:
                self.logger.exception("failed to post %s error reply", kind)

    def _reply_for_request(
        self,
        *,
        client: Any,
        team_id: str,
        channel_id: str,
        thread_ts: str,
        state_thread_ts: str,
        command_text: str,
        source_event: dict[str, Any],
        direct_message: bool,
    ) -> BotReply:
        if self._is_help_intent(command_text):
            return BotReply(HELP_TEXT)

        if self._is_idle_intent(command_text):
            return BotReply("음... 왜 불렀어?")

        if is_cafeteria_intent(command_text):
            menu = fetch_bundang_menu(command_text)
            return BotReply(format_bundang_menu(menu))

        if self._is_link_intent(command_text):
            url = self._pick_url(command_text, team_id, channel_id, thread_ts, client)
            if not url:
                return BotReply("요약할 링크를 못 찾았어. 링크를 같이 보내주거나, 링크 있는 데서 불러줘.")
            return BotReply(self._summarize_link(team_id, channel_id, url, command_text))

        if not self._is_summary_intent(command_text):
            return BotReply("음... 그건 아직 잘 모르겠어. 요약이면 `뭐 얘기했어?`라고 불러줘.")

        event_ts = str(source_event.get("ts") or "")
        user_id = str(source_event.get("user") or "")
        since_ts, since_label = self._since_ts_for_request(
            command_text=command_text,
            team_id=team_id,
            channel_id=channel_id,
            state_thread_ts=state_thread_ts,
            user_id=user_id,
        )

        in_thread = bool(source_event.get("thread_ts"))
        if in_thread:
            messages = self._load_thread_from_slack(
                client,
                team_id,
                channel_id,
                thread_ts,
                since_ts=since_ts,
            )
            scope_label = "현재 DM 스레드" if direct_message else "현재 Slack 스레드"
        else:
            messages = self._load_channel_recent_from_slack(
                client,
                team_id,
                channel_id,
                since_ts=since_ts,
            )
            if direct_message:
                scope_label = f"현재 DM 최근 {len(messages)}개 메시지"
            else:
                scope_label = f"현재 채널 최근 {len(messages)}개 메시지"

        messages = self._without_current_message(messages, event_ts)
        if since_ts:
            messages = self._messages_after(messages, since_ts)
            scope_label = f"{scope_label}, {since_label}"
            if not messages:
                return BotReply(f"음... {since_label} 새로 볼 얘기는 거의 없어.", mark_catchup=True)

        mode = self._summary_mode(command_text)
        prompt = build_summary_prompt(
            messages,
            mode=mode,
            command_text=command_text,
            scope_label=scope_label,
        )
        return BotReply(self.codex.run(prompt).text, mark_catchup=True)

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
        try:
            content = fetch_link_content(
                url,
                allow_private_hosts=self.settings.allow_private_link_hosts,
                max_bytes=self.settings.link_fetch_max_bytes,
            )
        except LinkFetchError as exc:
            return f"음... 이 링크는 바로 요약 못 하겠어. {exc}"
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
        *,
        since_ts: str | None = None,
    ) -> list[StoredMessage]:
        try:
            self._fetch_slack_pages(
                lambda cursor, limit: client.conversations_replies(
                    channel=channel_id,
                    ts=thread_ts,
                    limit=limit,
                    **self._cursor_arg(cursor),
                    **self._oldest_arg(since_ts),
                ),
                team_id=team_id,
                channel_id=channel_id,
                max_messages=self.settings.max_thread_messages,
            )
        except SlackApiError:
            self.logger.exception("failed to fetch Slack thread; using local store")
        if since_ts:
            return self.store.get_thread_messages_since(
                team_id,
                channel_id,
                thread_ts,
                since_ts,
                self.settings.max_thread_messages,
            )
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
        *,
        since_ts: str | None = None,
    ) -> list[StoredMessage]:
        try:
            self._fetch_slack_pages(
                lambda cursor, limit: client.conversations_history(
                    channel=channel_id,
                    limit=limit,
                    **self._cursor_arg(cursor),
                    **self._oldest_arg(since_ts),
                ),
                team_id=team_id,
                channel_id=channel_id,
                max_messages=self.settings.max_channel_messages,
            )
        except SlackApiError:
            self.logger.exception("failed to fetch channel history; using local store")
        if since_ts:
            return self.store.get_recent_channel_messages_since(
                team_id,
                channel_id,
                since_ts,
                self.settings.max_channel_messages,
            )
        return self.store.get_recent_channel_messages(
            team_id,
            channel_id,
            self.settings.max_channel_messages,
        )

    def _fetch_slack_pages(
        self,
        fetch_page: Any,
        *,
        team_id: str,
        channel_id: str,
        max_messages: int,
    ) -> None:
        cursor: str | None = None
        fetched = 0
        while fetched < max_messages:
            page_limit = min(200, max_messages - fetched)
            response = fetch_page(cursor, page_limit)
            messages = response.get("messages", [])
            for message in messages:
                self.store.upsert_message(team_id, channel_id, message)
            fetched += len(messages)
            cursor = (response.get("response_metadata") or {}).get("next_cursor")
            if not cursor or not messages:
                break

    @staticmethod
    def _oldest_arg(since_ts: str | None) -> dict[str, Any]:
        if not since_ts:
            return {}
        return {"oldest": since_ts, "inclusive": False}

    @staticmethod
    def _cursor_arg(cursor: str | None) -> dict[str, Any]:
        if not cursor:
            return {}
        return {"cursor": cursor}

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
        return " ".join(text.split()).strip()

    @staticmethod
    def _is_link_intent(text: str) -> bool:
        if extract_urls(text):
            return True
        return any(word in text for word in ["링크", "url", "URL", "이거 요약", "기사"])

    @staticmethod
    def _is_idle_intent(text: str) -> bool:
        normalized = text.lower().strip()
        return normalized in {
            "",
            "잠만봇",
            "jammanbot",
            "jamman",
            "야",
            "저기",
            "어이",
            "안녕",
            "ㅎㅇ",
            "하이",
        }

    @staticmethod
    def _is_summary_intent(text: str) -> bool:
        normalized = text.lower().strip()
        if not normalized:
            return False
        return any(
            word in normalized
            for word in [
                "요약",
                "정리",
                "뭐 얘기",
                "뭔 얘기",
                "무슨 얘기",
                "뭐했",
                "뭐 했",
                "캐치업",
                "catchup",
                "catch up",
                "못 본",
                "못본",
                "안 본",
                "안본",
                "놓친",
                "새로",
                "최근",
                "전부터",
                "이후",
                "오늘",
                "어제",
                "한줄",
                "한 줄",
                "자세",
                "상세",
            ]
        )

    @staticmethod
    def _is_help_intent(text: str) -> bool:
        normalized = text.lower().strip()
        return any(
            word in normalized
            for word in [
                "도움말",
                "사용법",
                "명령어",
                "help",
                "뭐 할 수",
                "뭐할수",
                "어떻게 써",
                "어떻게 사용",
            ]
        )

    @staticmethod
    def _summary_mode(text: str) -> str:
        if "한줄" in text or "한 줄" in text:
            return "one_line"
        if "자세" in text or "상세" in text or "길게" in text:
            return "detailed"
        return "summary"

    def _since_ts_for_request(
        self,
        *,
        command_text: str,
        team_id: str,
        channel_id: str,
        state_thread_ts: str,
        user_id: str,
    ) -> tuple[str | None, str | None]:
        explicit = self._parse_time_window(command_text)
        if explicit:
            return explicit

        if self._is_catchup_intent(command_text) and user_id:
            last_seen = self.store.get_user_catchup(
                team_id,
                channel_id,
                state_thread_ts,
                user_id,
            )
            if last_seen:
                return last_seen, "지난번에 잠만봇이 읽어준 뒤로"
        return None, None

    @staticmethod
    def _is_catchup_intent(text: str) -> bool:
        normalized = text.lower().strip()
        return any(
            word in normalized
            for word in [
                "못 본",
                "못본",
                "안 본",
                "안본",
                "놓친",
                "새로",
                "캐치업",
                "catchup",
                "catch up",
                "이후",
            ]
        )

    @staticmethod
    def _parse_time_window(text: str) -> tuple[str, str] | None:
        normalized = text.lower().strip()
        now = datetime.now().astimezone()

        if "오늘" in normalized:
            start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            return str(start.timestamp()), "오늘 0시부터"

        if "어제" in normalized:
            start = (now - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
            return str(start.timestamp()), "어제 0시부터"

        amount_match = re.search(r"(?:최근\s*)?(\d+)\s*(분|시간|일)\s*(?:전부터|전|동안|만|이후)?", normalized)
        if amount_match and (
            "최근" in normalized
            or "전" in normalized
            or "동안" in normalized
            or "부터" in normalized
            or "이후" in normalized
            or "만" in normalized
        ):
            amount = int(amount_match.group(1))
            unit = amount_match.group(2)
            if unit == "분":
                start = now - timedelta(minutes=amount)
                label = f"최근 {amount}분"
            elif unit == "시간":
                start = now - timedelta(hours=amount)
                label = f"최근 {amount}시간"
            else:
                start = now - timedelta(days=amount)
                label = f"최근 {amount}일"
            return str(start.timestamp()), label

        clock_match = re.search(
            r"(오전|오후)?\s*(\d{1,2})시(?:\s*(\d{1,2})분)?\s*(?:이후|부터)",
            normalized,
        )
        if clock_match:
            ampm = clock_match.group(1)
            hour = int(clock_match.group(2))
            minute = int(clock_match.group(3) or 0)
            if ampm == "오후" and hour < 12:
                hour += 12
            if ampm == "오전" and hour == 12:
                hour = 0
            if 0 <= hour <= 23 and 0 <= minute <= 59:
                start = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
                if start > now:
                    start = start - timedelta(days=1)
                return str(start.timestamp()), f"{hour:02d}:{minute:02d} 이후"

        return None

    @staticmethod
    def _team_id(body: dict[str, Any], event: dict[str, Any]) -> str:
        return str(body.get("team_id") or event.get("team") or "default")

    @staticmethod
    def _message_from_event(event: dict[str, Any]) -> dict[str, Any]:
        if event.get("subtype") == "message_changed" and isinstance(event.get("message"), dict):
            return event["message"]
        return event

    @staticmethod
    def _state_thread_ts(event: dict[str, Any]) -> str:
        return str(event.get("thread_ts") or CHANNEL_STATE_THREAD_TS)

    @staticmethod
    def _without_current_message(
        messages: list[StoredMessage],
        event_ts: str,
    ) -> list[StoredMessage]:
        if not event_ts:
            return messages
        return [message for message in messages if message.ts != event_ts]

    @staticmethod
    def _messages_after(
        messages: list[StoredMessage],
        since_ts: str,
    ) -> list[StoredMessage]:
        try:
            since = float(since_ts)
        except ValueError:
            return messages
        selected: list[StoredMessage] = []
        for message in messages:
            try:
                if float(message.ts) > since:
                    selected.append(message)
            except ValueError:
                selected.append(message)
        return selected

    def _should_ignore_message_event(
        self,
        event: dict[str, Any],
        message: dict[str, Any],
    ) -> bool:
        if event.get("subtype"):
            return True
        if message.get("bot_id") or message.get("subtype"):
            return True
        if self.bot_user_id and message.get("user") == self.bot_user_id:
            return True
        return False

    def _log_exchange(
        self,
        kind: str,
        channel_id: str,
        thread_ts: str,
        command_text: str,
        reply: str,
    ) -> None:
        self.logger.info(
            "%s channel=%s thread=%s request=%r reply_preview=%r",
            kind,
            channel_id,
            thread_ts,
            command_text[:180],
            reply[:220],
        )
