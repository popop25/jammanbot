from __future__ import annotations

import unittest

from jammanbot.lunchlog_agent import (
    build_rule_based_summary,
    parse_meal_rule_based,
    summarize_records,
)


class LunchLogAgentTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
