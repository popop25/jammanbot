from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import httpx


SEOUL = ZoneInfo("Asia/Seoul")
MENU_URL = "https://mc.skhystec.com/V3/prc/selectMenuList.prc"

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
    if any(word in normalized for word in ["요약", "정리", "얘기", "이후", "전부터", "못 본", "못본"]):
        return False
    if any(word in normalized for word in ["메뉴", "식당", "구내식당"]):
        return True
    if any(word in normalized for word in ["밥", "점심", "저녁", "아침", "야식"]) and any(
        word in normalized for word in ["뭐", "모야", "뭐야", "뭐임", "알려", "추천"]
    ):
        return True
    return False


def parse_menu_request(text: str) -> tuple[datetime, str]:
    now = datetime.now(SEOUL)
    normalized = text.lower()

    if "내일" in normalized:
        target = now + timedelta(days=1)
    elif "어제" in normalized:
        target = now - timedelta(days=1)
    else:
        target = now

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


def fetch_bundang_menu(text: str) -> CafeteriaMenu:
    target, meal_type = parse_menu_request(text)
    ymd = target.strftime("%Y%m%d")

    data = _post_menu(cafeteria_seq="21", meal_type=meal_type, ymd=ymd)
    items = [_item_from_raw(item) for item in data.get("menuList", []) if item.get("MENU_NAME")]

    return CafeteriaMenu(
        date=target.strftime("%Y-%m-%d"),
        meal_type=meal_type,
        campus="분당캠퍼스",
        restaurant_seq="21",
        restaurant_name="비원",
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

    weather = f" 참고로 기온은 {menu.temperature}℃래." if menu.temperature else ""
    lines = [f"음, {menu.date} 분당캠퍼스 {meal_label}은 대충 이래.{weather}"]
    for item in menu.items:
        soldout = " SOLD OUT" if item.soldout else ""
        kcal = f" ({item.kcal}kcal)" if item.kcal else ""
        guide = f" / {item.guide}" if item.guide else ""
        sides = f" - {', '.join(item.sides)}" if item.sides else ""
        lines.append(f"- {item.course}: {item.name}{kcal}{guide}{soldout}{sides}")
    return "\n".join(lines)


def _post_menu(*, cafeteria_seq: str, meal_type: str, ymd: str) -> dict:
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
        "campus": "BD",
        "cafeteriaSeq": cafeteria_seq,
        "mealType": meal_type,
        "ymd": ymd,
    }
    with httpx.Client(timeout=20.0, follow_redirects=True, headers=headers) as client:
        response = client.post(MENU_URL, data=payload)
        response.raise_for_status()
        return response.json()


def _item_from_raw(raw: dict) -> CafeteriaMenuItem:
    sides = [_clean(raw.get(f"SIDE_{index}")) for index in range(1, 7)]
    return CafeteriaMenuItem(
        course=_clean(raw.get("COURSE_NAME")) or "코너",
        name=_clean(raw.get("MENU_NAME")) or "메뉴 없음",
        sides=[side for side in sides if side],
        kcal=_clean(raw.get("KCAL")),
        guide=_clean(raw.get("MENU_GUIDE")),
        soldout=_clean(raw.get("SOLDOUT_YN")) == "Y",
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


def _clean(value: object) -> str:
    if value is None:
        return ""
    return " ".join(str(value).replace("\r", " ").replace("\n", " ").split())
