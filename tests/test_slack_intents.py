from __future__ import annotations

from types import SimpleNamespace
import unittest

from jammanbot.slack_bot import JammanSlackBot


class FakeCodex:
    def __init__(self) -> None:
        self.prompts: list[str] = []

    def run(self, prompt: str) -> SimpleNamespace:
        self.prompts.append(prompt)
        return SimpleNamespace(text="음... 그럴 수 있지. 잠깐 쉬어가자.")


class SlackIntentTests(unittest.TestCase):
    def test_smalltalk_good_morning(self) -> None:
        reply = JammanSlackBot._smalltalk_reply("좋은 아침")

        self.assertIsNotNone(reply)
        self.assertIn("좋은 아침", reply or "")

    def test_smalltalk_thanks(self) -> None:
        reply = JammanSlackBot._smalltalk_reply("고마워")

        self.assertIsNotNone(reply)
        self.assertIn("천만에", reply or "")

    def test_smalltalk_unknown_returns_none(self) -> None:
        self.assertIsNone(JammanSlackBot._smalltalk_reply("이건 아직 모르는 요청"))

    def test_summary_intent_still_wins_for_greeting_plus_summary(self) -> None:
        self.assertTrue(JammanSlackBot._is_summary_intent("안녕 요약 좀"))

    def test_today_alone_does_not_force_summary_intent(self) -> None:
        self.assertFalse(JammanSlackBot._is_summary_intent("오늘 좀 피곤하다"))
        self.assertTrue(JammanSlackBot._is_summary_intent("오늘 얘기만"))

    def test_unknown_short_text_uses_casual_chat(self) -> None:
        bot = JammanSlackBot.__new__(JammanSlackBot)
        bot.settings = SimpleNamespace(enable_casual_chat=True, casual_chat_max_chars=500)
        bot.codex = FakeCodex()

        reply = bot._reply_for_request(
            client=None,
            team_id="T1",
            channel_id="C1",
            thread_ts="1.0",
            state_thread_ts="__channel__",
            command_text="오늘 좀 피곤하다",
            source_event={"ts": "1.0", "user": "U1"},
            direct_message=False,
        )

        self.assertEqual(reply.text, "음... 그럴 수 있지. 잠깐 쉬어가자.")
        self.assertIn("오늘 좀 피곤하다", bot.codex.prompts[0])

    def test_casual_chat_can_be_disabled(self) -> None:
        bot = JammanSlackBot.__new__(JammanSlackBot)
        bot.settings = SimpleNamespace(enable_casual_chat=False, casual_chat_max_chars=500)
        bot.codex = FakeCodex()

        reply = bot._reply_for_request(
            client=None,
            team_id="T1",
            channel_id="C1",
            thread_ts="1.0",
            state_thread_ts="__channel__",
            command_text="오늘 좀 피곤하다",
            source_event={"ts": "1.0", "user": "U1"},
            direct_message=False,
        )

        self.assertIn("가벼운 대화", reply.text)
        self.assertEqual(bot.codex.prompts, [])

    def test_casual_chat_respects_length_limit(self) -> None:
        bot = JammanSlackBot.__new__(JammanSlackBot)
        bot.settings = SimpleNamespace(enable_casual_chat=True, casual_chat_max_chars=5)
        bot.codex = FakeCodex()

        self.assertFalse(bot._can_handle_casual_chat("오늘 좀 피곤하다"))


if __name__ == "__main__":
    unittest.main()
