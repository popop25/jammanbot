from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import re
from zoneinfo import ZoneInfo

import httpx


SEOUL = ZoneInfo("Asia/Seoul")
MENU_URL = "https://mc.skhystec.com/V3/prc/selectMenuList.prc"
BUNDANG_CAMPUS_CODE = "BD"
BUNDANG_BIWON_CAFETERIA_SEQ = "21"  # 분당캠퍼스 비원만 본다.
BUNDANG_BIWON_NAME = "비원"

CAFETERIA_OPTIONS = {
    "BD": {
        "21": "분당캠퍼스 비원",
        "26": "분당캠퍼스 식당 26",
        "22": "분당캠퍼스 식당 22",
        "24": "분당캠퍼스 식당 24",
    },
    "IC": {
        "10": "이천캠퍼스 R&D",
    },
    "CJ": {
        "11": "청주캠퍼스 식당 11",
    },
}

MEAL_LABELS = {
    "BF": "아침",
    "LN": "점심",
    "DN": "저녁",
    "SN": "야식",
}


@dataclass(frozen=True)
class CafeteriaMenuItem:
    course: str
    name: str
    sides: list[str]
    kcal: str
    guide: str
    soldout: bool
    image_url: str | None = None


@dataclass(frozen=True)
class CafeteriaMenu:
    date: str
    meal_type: str
    campus: str
    restaurant_seq: str
    restaurant_name: str
    items: list[CafeteriaMenuItem]
    temperature: str | None = None


def is_cafeteria_intent(text: str) -> bool:
    normalized = text.lower()
    if any(word in normalized for word in ["메뉴", "식당", "구내식당"]):
        return True
    if any(word in normalized for word in ["요약", "정리", "얘기", "이후", "전부터", "못 본", "못본"]):
        return False
    if any(word in normalized for word in ["밥", "점심", "저녁", "아침", "야식"]) and any(
        word in normalized for word in ["뭐", "모야", "뭐야", "뭐임", "알려", "추천"]
    ):
        return True
    return False


def parse_menu_request(text: str) -> tuple[datetime, str]:
    now = datetime.now(SEOUL)
    normalized = text.lower()

    target = _parse_target_date(normalized, now)

    if "아침" in normalized or "조식" in normalized:
        meal_type = "BF"
    elif "저녁" in normalized or "석식" in normalized:
        meal_type = "DN"
    elif "야식" in normalized:
        meal_type = "SN"
    elif "점심" in normalized or "중식" in normalized:
        meal_type = "LN"
    else:
        meal_type = _current_meal_type(now)

    return target, meal_type


def fetch_bundang_menu(text: str, *, verify_ssl: bool = True) -> CafeteriaMenu:
    target, meal_type = parse_menu_request(text)
    return fetch_cafeteria_menu(
        target.strftime("%Y-%m-%d"),
        meal_type,
        campus=BUNDANG_CAMPUS_CODE,
        cafeteria_seq=BUNDANG_BIWON_CAFETERIA_SEQ,
        verify_ssl=verify_ssl,
    )


def fetch_cafeteria_menu(
    date: str,
    meal_type: str,
    *,
    campus: str = BUNDANG_CAMPUS_CODE,
    cafeteria_seq: str = BUNDANG_BIWON_CAFETERIA_SEQ,
    verify_ssl: bool = True,
) -> CafeteriaMenu:
    target = _parse_iso_date(date)
    ymd = target.strftime("%Y%m%d")

    data = _post_menu(
        campus=campus,
        cafeteria_seq=cafeteria_seq,
        meal_type=meal_type,
        ymd=ymd,
        verify_ssl=verify_ssl,
    )
    items = [_item_from_raw(item) for item in data.get("menuList", []) if item.get("MENU_NAME")]

    return CafeteriaMenu(
        date=target.strftime("%Y-%m-%d"),
        meal_type=meal_type,
        campus=campus,
        restaurant_seq=cafeteria_seq,
        restaurant_name=CAFETERIA_OPTIONS.get(campus, {}).get(cafeteria_seq, f"{campus}-{cafeteria_seq}"),
        items=items,
        temperature=_clean(data.get("TEMPERATURE")),
    )


def format_bundang_menu(menu: CafeteriaMenu) -> str:
    meal_label = MEAL_LABELS.get(menu.meal_type, menu.meal_type)
    if not menu.items:
        return (
            f"음... {menu.date} 분당캠퍼스 {meal_label} 메뉴는 안 보이네. "
            "주말이거나 아직 식단이 안 올라왔을 수도 있어."
        )

    lines = [f"음, {menu.date} 분당캠퍼스 {meal_label}은 이거야."]
    for item in menu.items:
        soldout = " (품절)" if item.soldout else ""
        lines.append(f"- {item.course}: {item.name}{soldout}")
    return "\n".join(lines)


def _post_menu(
    *,
    cafeteria_seq: str,
    meal_type: str,
    ymd: str,
    campus: str = BUNDANG_CAMPUS_CODE,
    verify_ssl: bool = True,
) -> dict:
    try:
        return _post_menu_once(
            campus=campus,
            cafeteria_seq=cafeteria_seq,
            meal_type=meal_type,
            ymd=ymd,
            verify_ssl=verify_ssl,
        )
    except httpx.ConnectError as exc:
        if verify_ssl and _is_ssl_verify_error(exc):
            return _post_menu_once(
                campus=campus,
                cafeteria_seq=cafeteria_seq,
                meal_type=meal_type,
                ymd=ymd,
                verify_ssl=False,
            )
        raise


def _post_menu_once(*, campus: str, cafeteria_seq: str, meal_type: str, ymd: str, verify_ssl: bool) -> dict:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"
        ),
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "X-Requested-With": "XMLHttpRequest",
        "Referer": "https://mc.skhystec.com/V3/menu.html",
    }
    payload = {
        "campus": campus,
        "cafeteriaSeq": cafeteria_seq,
        "mealType": meal_type,
        "ymd": ymd,
    }
    with httpx.Client(timeout=20.0, follow_redirects=True, headers=headers, verify=verify_ssl) as client:
        response = client.post(MENU_URL, data=payload)
        response.raise_for_status()
        return response.json()


def _is_ssl_verify_error(exc: BaseException) -> bool:
    current: BaseException | None = exc
    while current:
        if "CERTIFICATE_VERIFY_FAILED" in str(current):
            return True
        current = current.__cause__ or current.__context__
    return False


def _item_from_raw(raw: dict) -> CafeteriaMenuItem:
    sides = [_clean(raw.get(f"SIDE_{index}")) for index in range(1, 7)]
    return CafeteriaMenuItem(
        course=_clean(raw.get("COURSE_NAME")) or "코너",
        name=_clean(raw.get("MENU_NAME")) or "메뉴 없음",
        sides=[side for side in sides if side],
        kcal=_clean(raw.get("KCAL")),
        guide=_clean(raw.get("MENU_GUIDE")),
        soldout=_clean(raw.get("SOLDOUT_YN")) == "Y",
        image_url=_menu_image_url(_clean(raw.get("SAVE_FILE_NM"))),
    )


def _menu_image_url(save_file_name: str) -> str | None:
    if not save_file_name:
        return None
    parts = save_file_name.split("_")
    if len(parts) < 4:
        return None
    return (
        "https://mc.skhystec.com/nsf/menuImage/"
        f"{parts[0]}/{parts[1]}/{parts[2]}/{parts[3]}/{save_file_name}"
    )


def _current_meal_type(now: datetime) -> str:
    hhmm = now.strftime("%H:%M")
    if "02:40" <= hhmm < "09:30":
        return "BF"
    if "09:30" <= hhmm < "14:50":
        return "LN"
    if "14:50" <= hhmm < "20:00":
        return "DN"
    return "SN"


def _parse_iso_date(date: str) -> datetime:
    try:
        parsed = datetime.strptime(date, "%Y-%m-%d")
    except ValueError:
        return datetime.now(SEOUL)
    return parsed.replace(tzinfo=SEOUL)


def _parse_target_date(text: str, now: datetime) -> datetime:
    compact = re.sub(r"\s+", "", text)

    if "모레" in compact:
        return now + timedelta(days=2)
    if "내일" in compact:
        return now + timedelta(days=1)
    if "그제" in compact:
        return now - timedelta(days=2)
    if "어제" in compact:
        return now - timedelta(days=1)
    if "오늘" in compact:
        return now

    explicit = _parse_explicit_date(compact, now)
    if explicit:
        return explicit

    weekday = _parse_weekday(compact, now)
    if weekday:
        return weekday

    return now


def _parse_explicit_date(text: str, now: datetime) -> datetime | None:
    full_match = re.search(r"(20\d{2})[.\-/년]?(\d{1,2})[.\-/월]?(\d{1,2})일?", text)
    if full_match:
        return _safe_date(
            year=int(full_match.group(1)),
            month=int(full_match.group(2)),
            day=int(full_match.group(3)),
            now=now,
        )

    month_day_match = re.search(r"(\d{1,2})월(\d{1,2})일?", text)
    if month_day_match:
        return _safe_date(
            year=now.year,
            month=int(month_day_match.group(1)),
            day=int(month_day_match.group(2)),
            now=now,
        )

    slash_match = re.search(r"(?<!\d)(\d{1,2})[./-](\d{1,2})(?!\d)", text)
    if slash_match:
        return _safe_date(
            year=now.year,
            month=int(slash_match.group(1)),
            day=int(slash_match.group(2)),
            now=now,
        )

    day_match = re.search(r"(?<!\d)(\d{1,2})일", text)
    if day_match:
        return _safe_date(
            year=now.year,
            month=now.month,
            day=int(day_match.group(1)),
            now=now,
        )

    return None


def _parse_weekday(text: str, now: datetime) -> datetime | None:
    weekday_names = {
        "월요일": 0,
        "월욜": 0,
        "월": 0,
        "화요일": 1,
        "화욜": 1,
        "화": 1,
        "수요일": 2,
        "수욜": 2,
        "수": 2,
        "목요일": 3,
        "목욜": 3,
        "목": 3,
        "금요일": 4,
        "금욜": 4,
        "금": 4,
        "토요일": 5,
        "토욜": 5,
        "토": 5,
        "일요일": 6,
        "일욜": 6,
        "일": 6,
    }
    matched_weekday: int | None = None
    for name, value in weekday_names.items():
        if name in text:
            matched_weekday = value
            break
    if matched_weekday is None:
        return None

    week_start = now - timedelta(days=now.weekday())
    if "다음주" in text or "담주" in text:
        return week_start + timedelta(days=7 + matched_weekday)
    if "이번주" in text:
        return week_start + timedelta(days=matched_weekday)

    days_ahead = matched_weekday - now.weekday()
    if "다음" in text and days_ahead <= 0:
        days_ahead += 7
    elif days_ahead < 0:
        days_ahead += 7
    return now + timedelta(days=days_ahead)


def _safe_date(*, year: int, month: int, day: int, now: datetime) -> datetime | None:
    try:
        return now.replace(year=year, month=month, day=day)
    except ValueError:
        return None


def _clean(value: object) -> str:
    if value is None:
        return ""
    return " ".join(str(value).replace("\r", " ").replace("\n", " ").split())
