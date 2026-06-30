from __future__ import annotations

import json
from importlib import resources
from pathlib import Path
from typing import Any


CACHE_RESOURCE = "data/menu-cache.json"


def menu_cache_key(*, date: str, meal_type: str, campus: str, cafeteria_seq: str) -> str:
    return f"{date}|{meal_type}|{campus}|{cafeteria_seq}"


def load_menu_cache(path: str | Path | None = None) -> dict[str, Any]:
    if path:
        cache_path = Path(path)
        if not cache_path.exists():
            return {"menus": {}}
        return json.loads(cache_path.read_text(encoding="utf-8"))

    try:
        text = resources.files("jammanbot").joinpath(CACHE_RESOURCE).read_text(encoding="utf-8")
    except FileNotFoundError:
        return {"menus": {}}
    return json.loads(text)


def get_cached_menu(
    *,
    date: str,
    meal_type: str,
    campus: str,
    cafeteria_seq: str,
    path: str | Path | None = None,
) -> dict[str, Any] | None:
    cache = load_menu_cache(path)
    key = menu_cache_key(date=date, meal_type=meal_type, campus=campus, cafeteria_seq=cafeteria_seq)
    menu = (cache.get("menus") or {}).get(key)
    return menu if isinstance(menu, dict) else None


def write_menu_cache(cache: dict[str, Any], path: str | Path) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(cache, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
