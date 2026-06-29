from __future__ import annotations

import unittest

from jammanbot.slack_bot import JammanSlackBot


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


if __name__ == "__main__":
    unittest.main()
