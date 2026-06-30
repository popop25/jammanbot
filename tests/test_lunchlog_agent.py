from __future__ import annotations

import unittest

from jammanbot.lunchlog_agent import (
    LunchLogAgent,
    build_rule_based_summary,
    classify_message,
    parse_meal_rule_based,
    summarize_records,
)
from jammanbot.menu_cache import get_cached_menu


class DisabledGemini:
    enabled = False


class LunchLogAgentTests(unittest.TestCase):
    def test_classify_message_routes_core_intents(self) -> None:
        self.assertEqual(classify_message("오늘 점심 뭐야?"), "menu_query")
        self.assertEqual(classify_message("A코너 먹었고 맛있었어"), "meal_record")
        self.assertEqual(classify_message("이번 주 뭐 먹었지?"), "pattern_summary")
        self.assertEqual(classify_message("오늘 뭐 먹을까?"), "roulette")

    def test_parse_meal_rule_based_from_cafeteria_text(self) -> None:
        menu = {
            "items": [
                {"course": "A코너", "name": "북창동순두부"},
                {"course": "B코너", "name": "돈까스"},
            ]
        }

        record = parse_meal_rule_based(text="오늘 A코너 먹었고 맛있었어", menu=menu)

        self.assertEqual(record["mealType"], "LN")
        self.assertEqual(record["place"], "cafeteria")
        self.assertEqual(record["menuName"], "A코너: 북창동순두부")
        self.assertEqual(record["rating"], "good")

    def test_parse_meal_rule_based_outside(self) -> None:
        record = parse_meal_rule_based(text="오늘 밖에서 라멘 먹었는데 별로였어", menu={})

        self.assertEqual(record["place"], "outside")
        self.assertEqual(record["rating"], "bad")

    def test_summarize_records_counts_patterns(self) -> None:
        stats = summarize_records(
            [
                {"menuName": "A코너", "place": "cafeteria", "rating": "good"},
                {"menuName": "라멘", "place": "outside", "rating": "neutral"},
            ]
        )

        self.assertEqual(stats["total"], 2)
        self.assertEqual(stats["cafeteriaCount"], 1)
        self.assertEqual(stats["outsideCount"], 1)
        self.assertEqual(stats["goodCount"], 1)

    def test_rule_based_summary_handles_empty_records(self) -> None:
        summary = build_rule_based_summary({"total": 0})

        self.assertIn("아직 기록이 없어", summary)

    def test_handle_message_returns_menu_attachment(self) -> None:
        class StubAgent(LunchLogAgent):
            def get_menu(self, **_: object) -> dict:
                return {
                    "date": "2026-06-30",
                    "mealType": "LN",
                    "restaurantName": "분당캠퍼스 비원",
                    "items": [{"course": "A코너", "name": "북창동순두부", "soldout": False}],
                }

        response = StubAgent().handle_message(text="오늘 점심 뭐야?")

        self.assertEqual(response["type"], "menu")
        self.assertEqual(response["attachments"][0]["kind"], "menu")
        self.assertIn("A코너", response["reply"])

    def test_handle_message_returns_record(self) -> None:
        agent = LunchLogAgent(gemini=DisabledGemini())  # type: ignore[arg-type]

        response = agent.handle_message(
            text="A코너 먹었고 맛있었어",
            context={
                "currentMenu": {
                    "items": [{"course": "A코너", "name": "북창동순두부"}],
                }
            },
        )

        self.assertEqual(response["type"], "record")
        self.assertEqual(response["record"]["menuName"], "A코너: 북창동순두부")
        self.assertIn("기록", response["reply"])

    def test_bundled_menu_cache_has_current_lunch(self) -> None:
        menu = get_cached_menu(date="2026-06-30", meal_type="LN", campus="BD", cafeteria_seq="21")

        self.assertIsNotNone(menu)
        self.assertGreater(len(menu["items"]), 0)


if __name__ == "__main__":
    unittest.main()
