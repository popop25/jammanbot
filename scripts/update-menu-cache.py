from __future__ import annotations

import argparse
from datetime import date, timedelta
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from jammanbot.cafeteria import fetch_cafeteria_menu  # noqa: E402
from jammanbot.lunchlog_agent import serialize_menu  # noqa: E402
from jammanbot.menu_cache import load_menu_cache, menu_cache_key, write_menu_cache  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Update bundled cafeteria menu cache.")
    parser.add_argument("--days", type=int, default=14)
    parser.add_argument("--start", default=date.today().isoformat())
    parser.add_argument("--campus", default="BD")
    parser.add_argument("--cafeteria", default="21")
    parser.add_argument("--meals", default="LN")
    parser.add_argument("--out", default=str(ROOT / "src" / "jammanbot" / "data" / "menu-cache.json"))
    parser.add_argument("--no-verify-ssl", action="store_true")
    args = parser.parse_args()

    start = date.fromisoformat(args.start)
    meals = [meal.strip().upper() for meal in args.meals.split(",") if meal.strip()]
    cache = load_menu_cache(args.out)
    menus = cache.setdefault("menus", {})

    ok = 0
    failed = 0
    for offset in range(args.days):
        target = start + timedelta(days=offset)
        for meal in meals:
            key = menu_cache_key(
                date=target.isoformat(),
                meal_type=meal,
                campus=args.campus,
                cafeteria_seq=args.cafeteria,
            )
            try:
                menu = fetch_cafeteria_menu(
                    target.isoformat(),
                    meal,
                    campus=args.campus,
                    cafeteria_seq=args.cafeteria,
                    verify_ssl=not args.no_verify_ssl,
                )
            except Exception as exc:
                failed += 1
                print(f"skip {key}: {type(exc).__name__}: {exc}")
                continue
            serialized = serialize_menu(menu)
            if serialized.get("items"):
                menus[key] = serialized
                ok += 1
                print(f"cached {key}: {len(serialized['items'])} items")
            else:
                print(f"empty {key}")

    cache["updatedAt"] = date.today().isoformat()
    write_menu_cache(cache, args.out)
    print(f"done: cached={ok} failed={failed} out={args.out}")


if __name__ == "__main__":
    main()
