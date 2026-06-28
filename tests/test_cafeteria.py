from __future__ import annotations

from datetime import datetime
import unittest
from zoneinfo import ZoneInfo

from jammanbot.cafeteria import (
    CafeteriaMenu,
    CafeteriaMenuItem,
    _parse_target_date,
    format_bundang_menu,
    is_cafeteria_intent,
)


class CafeteriaTests(unittest.TestCase):
    def test_parse_compact_next_weekday(self) -> None:
        now = datetime(2026, 6, 27, 10, 0, tzinfo=ZoneInfo("Asia/Seoul"))

        target = _parse_target_date("다음주월요일점심메뉴", now)

        self.assertEqual(target.date().isoformat(), "2026-06-29")

    def test_parse_bare_day_in_current_month(self) -> None:
        now = datetime(2026, 6, 27, 10, 0, tzinfo=ZoneInfo("Asia/Seoul"))

        target = _parse_target_date("26일점심메뉴", now)

        self.assertEqual(target.date().isoformat(), "2026-06-26")

    def test_cafeteria_intent_does_not_steal_summary_request(self) -> None:
        self.assertFalse(is_cafeteria_intent("점심 이후 얘기 요약"))
        self.assertTrue(is_cafeteria_intent("점심 메뉴 뭐야"))

    def test_format_menu_only_shows_course_and_main_name(self) -> None:
        menu = CafeteriaMenu(
            date="2026-06-26",
            meal_type="LN",
            campus="분당캠퍼스",
            restaurant_seq="21",
            restaurant_name="비원",
            items=[
                CafeteriaMenuItem(
                    course="A코너",
                    name="제육야채볶음",
                    sides=["쌀밥"],
                    kcal="999",
                    guide="",
                    soldout=False,
                )
            ],
        )

        text = format_bundang_menu(menu)

        self.assertIn("- A코너: 제육야채볶음", text)
        self.assertNotIn("999", text)
        self.assertNotIn("쌀밥", text)


if __name__ == "__main__":
    unittest.main()
