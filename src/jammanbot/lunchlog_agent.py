from __future__ import annotations

from dataclasses import asdict
from datetime import date, datetime
import random
import re
from typing import Any

from .cafeteria import CAFETERIA_OPTIONS, CafeteriaMenu, fetch_cafeteria_menu
from .gemini_client import GeminiClient


DEFAULT_ROULETTE = [
    {"name": "국밥", "tags": ["든든하게", "빠르게", "따뜻하게"]},
    {"name": "라멘", "tags": ["든든하게", "일식", "국물"]},
    {"name": "돈까스", "tags": ["든든하게", "무난하게"]},
    {"name": "샐러드", "tags": ["가볍게", "건강하게"]},
    {"name": "분식", "tags": ["빠르게", "가볍게"]},
    {"name": "중식", "tags": ["든든하게", "매콤하게"]},
    {"name": "백반", "tags": ["집밥", "무난하게"]},
    {"name": "카레", "tags": ["빠르게", "든든하게"]},
    {"name": "햄버거", "tags": ["빠르게", "간편하게"]},
    {"name": "편의점 간편식", "tags": ["아주 빠르게", "가볍게"]},
]

RATING_WORDS = {
    "good": ["맛있", "좋", "괜찮", "만족", "최고"],
    "bad": ["별로", "맛없", "싫", "아쉬", "실패"],
}


class LunchLogAgent:
    def __init__(self, *, gemini: GeminiClient | None = None, verify_ssl: bool = True) -> None:
        self.gemini = gemini or GeminiClient()
        self.verify_ssl = verify_ssl

    def get_menu(
        self,
        *,
        target_date: str,
        meal_type: str,
        campus: str = "BD",
        cafeteria_seq: str = "21",
    ) -> dict[str, Any]:
        menu = fetch_cafeteria_menu(
            target_date,
            meal_type,
            campus=campus,
            cafeteria_seq=cafeteria_seq,
            verify_ssl=self.verify_ssl,
        )
        return serialize_menu(menu)

    def parse_meal(self, *, text: str, menu: dict[str, Any] | None = None) -> dict[str, Any]:
        if self.gemini.enabled:
            try:
                return self._parse_meal_with_gemini(text=text, menu=menu or {})
            except Exception:
                pass
        return parse_meal_rule_based(text=text, menu=menu or {})

    def summarize_pattern(self, *, records: list[dict[str, Any]]) -> dict[str, Any]:
        stats = summarize_records(records)
        if self.gemini.enabled:
            try:
                stats["agentSummary"] = self._summarize_with_gemini(records=records, stats=stats)
            except Exception:
                stats["agentSummary"] = build_rule_based_summary(stats)
        else:
            stats["agentSummary"] = build_rule_based_summary(stats)
        return stats

    def chat(self, *, text: str, records: list[dict[str, Any]] | None = None) -> str:
        if self.gemini.enabled:
            try:
                return self.gemini.generate_text(_chat_prompt(text=text, records=records or []))
            except Exception:
                pass
        return "음... 밥 얘기면 내가 잘 듣지. 먹은 메뉴를 말해주면 기록해둘게."

    def roulette(
        self,
        *,
        candidates: list[dict[str, Any]] | None = None,
        mood: str = "",
        records: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        pool = candidates or DEFAULT_ROULETTE
        filtered = _filter_candidates(pool, mood)
        choice = random.choice(filtered or pool)
        return {
            "choice": choice,
            "reason": build_roulette_reason(choice, mood=mood, records=records or []),
            "pool": pool,
        }

    def _parse_meal_with_gemini(self, *, text: str, menu: dict[str, Any]) -> dict[str, Any]:
        prompt = f"""
너는 식사 기록 Agent '잠만봇'이다.
사용자의 자연어 식사 기록을 JSON으로 구조화한다.

규칙:
- JSON object만 출력한다.
- date가 명확하지 않으면 오늘 날짜({date.today().isoformat()})를 사용한다.
- mealType은 BF, LN, DN, SN 중 하나다. 기본은 LN이다.
- rating은 good, neutral, bad 중 하나다.
- menuName은 사용자가 말한 메뉴명 또는 가장 가까운 메뉴명을 쓴다.
- place는 cafeteria, outside, convenience, skipped, unknown 중 하나다.

오늘 메뉴:
{menu}

사용자 말:
{text}

출력 예:
{{"date":"2026-06-30","mealType":"LN","place":"cafeteria","menuName":"A코너","rating":"good"}}
""".strip()
        parsed = self.gemini.generate_json(prompt)
        return normalize_record(parsed)

    def _summarize_with_gemini(self, *, records: list[dict[str, Any]], stats: dict[str, Any]) -> str:
        prompt = f"""
너는 '잠만봇'이다. 먹고 자는 일에 진심인 느긋한 식사 기록 Agent다.
아래 식사 기록 통계를 보고 2~3문장으로 한국어 요약을 작성한다.
과장하지 말고, 다음 식사 선택에 도움이 되는 말만 한다.

통계:
{stats}

기록:
{records[-20:]}
""".strip()
        return self.gemini.generate_text(prompt)


def serialize_menu(menu: CafeteriaMenu) -> dict[str, Any]:
    return {
        "date": menu.date,
        "mealType": menu.meal_type,
        "campus": menu.campus,
        "restaurantSeq": menu.restaurant_seq,
        "restaurantName": menu.restaurant_name,
        "temperature": menu.temperature,
        "items": [asdict(item) for item in menu.items],
    }


def cafeteria_options() -> dict[str, Any]:
    return CAFETERIA_OPTIONS


def parse_meal_rule_based(*, text: str, menu: dict[str, Any]) -> dict[str, Any]:
    normalized = text.strip()
    rating = "neutral"
    for key, words in RATING_WORDS.items():
        if any(word in normalized for word in words):
            rating = key
            break

    meal_type = "LN"
    if "아침" in normalized or "조식" in normalized:
        meal_type = "BF"
    elif "저녁" in normalized or "석식" in normalized:
        meal_type = "DN"
    elif "야식" in normalized:
        meal_type = "SN"

    place = "cafeteria"
    if any(word in normalized for word in ["밖", "외식", "식당", "가게"]):
        place = "outside"
    if "편의점" in normalized:
        place = "convenience"
    if any(word in normalized for word in ["안 먹", "굶"]):
        place = "skipped"

    menu_name = _pick_menu_name(normalized, menu)
    return normalize_record(
        {
            "date": date.today().isoformat(),
            "mealType": meal_type,
            "place": place,
            "menuName": menu_name,
            "rating": rating,
        }
    )


def normalize_record(raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(raw.get("id") or int(datetime.now().timestamp() * 1000)),
        "date": str(raw.get("date") or date.today().isoformat()),
        "mealType": _normalize_meal_type(str(raw.get("mealType") or "LN")),
        "place": str(raw.get("place") or "cafeteria"),
        "menuName": str(raw.get("menuName") or raw.get("menu") or "기록 없음"),
        "rating": _normalize_rating(str(raw.get("rating") or "neutral")),
        "createdAt": str(raw.get("createdAt") or datetime.now().isoformat(timespec="seconds")),
    }


def summarize_records(records: list[dict[str, Any]]) -> dict[str, Any]:
    normalized = [normalize_record(record) for record in records]
    cafeteria_count = sum(1 for record in normalized if record["place"] == "cafeteria")
    outside_count = sum(1 for record in normalized if record["place"] == "outside")
    good_count = sum(1 for record in normalized if record["rating"] == "good")
    menu_counts: dict[str, int] = {}
    for record in normalized:
        menu_counts[record["menuName"]] = menu_counts.get(record["menuName"], 0) + 1
    top_menus = sorted(menu_counts.items(), key=lambda item: item[1], reverse=True)[:5]
    return {
        "total": len(normalized),
        "cafeteriaCount": cafeteria_count,
        "outsideCount": outside_count,
        "goodCount": good_count,
        "topMenus": [{"name": name, "count": count} for name, count in top_menus],
    }


def build_rule_based_summary(stats: dict[str, Any]) -> str:
    total = stats.get("total", 0)
    if not total:
        return "음... 아직 기록이 없어. 한 끼만 기록해도 내가 패턴을 보기 시작할 수 있어."
    cafeteria_count = stats.get("cafeteriaCount", 0)
    outside_count = stats.get("outsideCount", 0)
    top_menus = stats.get("topMenus") or []
    top = top_menus[0]["name"] if top_menus else "특정 메뉴"
    return (
        f"음... 지금까지 {total}끼를 기록했어. 구내식당은 {cafeteria_count}번, "
        f"외식은 {outside_count}번이고, 자주 보이는 메뉴는 {top} 쪽이야."
    )


def build_roulette_reason(choice: dict[str, Any], *, mood: str, records: list[dict[str, Any]]) -> str:
    name = choice.get("name", "오늘의 메뉴")
    if mood:
        return f"음... 오늘은 '{mood}' 느낌이라면 {name} 쪽이 무난해. 일단 먹고 나서 생각하자."
    if records:
        return f"최근 기록도 있으니 오늘은 {name}으로 방향을 바꿔보자. 배고프면 결정은 빨라야 해."
    return f"음... 룰렛은 {name}. 큰 고민 없이 가기 좋은 선택이야."


def _pick_menu_name(text: str, menu: dict[str, Any]) -> str:
    for item in menu.get("items") or []:
        course = str(item.get("course") or "")
        name = str(item.get("name") or "")
        if course and course in text:
            return f"{course}: {name}" if name else course
        if name and name in text:
            return name
    match = re.search(r"([A-E])\s*코너", text, flags=re.IGNORECASE)
    if match:
        return f"{match.group(1).upper()}코너"
    compact = text.replace("먹었어", "").replace("먹음", "").strip()
    return compact[:80] or "기록 없음"


def _filter_candidates(pool: list[dict[str, Any]], mood: str) -> list[dict[str, Any]]:
    if not mood:
        return pool
    return [
        candidate
        for candidate in pool
        if mood in candidate.get("name", "") or any(mood in tag for tag in candidate.get("tags", []))
    ]


def _normalize_meal_type(value: str) -> str:
    upper = value.upper()
    if upper in {"BF", "LN", "DN", "SN"}:
        return upper
    return "LN"


def _normalize_rating(value: str) -> str:
    lowered = value.lower()
    if lowered in {"good", "neutral", "bad"}:
        return lowered
    if lowered in {"좋음", "좋아", "맛있음"}:
        return "good"
    if lowered in {"별로", "나쁨"}:
        return "bad"
    return "neutral"


def _chat_prompt(*, text: str, records: list[dict[str, Any]]) -> str:
    return f"""
너는 식사 Agent '잠만봇'이다.
먹고 자는 것에 정체성이 집중된 느긋하고 든든한 마스코트다.
사용자의 식사 선택, 식사 기록, 구내식당 메뉴와 관련된 질문에 짧게 답한다.
답변은 한국어 1~3문장으로 한다.

최근 기록:
{records[-10:]}

사용자 말:
{text}
""".strip()
