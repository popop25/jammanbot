from __future__ import annotations

from datetime import datetime
import unittest
from unittest.mock import patch
from zoneinfo import ZoneInfo

import httpx

from jammanbot.cafeteria import (
    CafeteriaMenu,
    CafeteriaMenuItem,
    _is_ssl_verify_error,
    _post_menu,
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

    def test_detects_ssl_verify_error(self) -> None:
        error = RuntimeError("[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed")

        self.assertTrue(_is_ssl_verify_error(error))

    def test_ignores_non_ssl_error(self) -> None:
        error = RuntimeError("connection refused")

        self.assertFalse(_is_ssl_verify_error(error))

    def test_post_menu_retries_without_ssl_verification_on_certificate_error(self) -> None:
        ssl_error = httpx.ConnectError("[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed")
        with patch(
            "jammanbot.cafeteria._post_menu_once",
            side_effect=[ssl_error, {"menuList": []}],
        ) as post_once:
            data = _post_menu(cafeteria_seq="21", meal_type="LN", ymd="20260629")

        self.assertEqual(data, {"menuList": []})
        self.assertEqual(post_once.call_args_list[0].kwargs["verify_ssl"], True)
        self.assertEqual(post_once.call_args_list[1].kwargs["verify_ssl"], False)


if __name__ == "__main__":
    unittest.main()
