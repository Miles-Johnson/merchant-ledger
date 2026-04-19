#!/usr/bin/env python3
"""Read-only audit for canonicals that lack a native LR/recipe pricing path.

Writes report: data/pricing_gaps.json
"""

from __future__ import annotations

import json
import os
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional, Set, Tuple

import psycopg2
from dotenv import load_dotenv


load_dotenv()

REPORT_PATH = os.path.join("data", "pricing_gaps.json")
MAX_RECURSION_DEPTH = 6
UNPRICED_MATCH_TIERS = {"unmatched", "none", ""}
NON_CONSUMABLE_TOOL_ROOTS = (
    "sewingkit",
    "sewing",
    "pickaxe",
    "shovel",
    "scythe",
    "hammer",
    "chisel",
    "knife",
    "axe",
    "awl",
    "saw",
    "sew",
)


@dataclass(frozen=True)
class CanonicalItem:
    canonical_id: str
    game_code: Optional[str]
    display_name: str
    lr_item_id: Optional[int]
    match_tier: Optional[str]


def _normalize_tier(value: Optional[str]) -> str:
    return (value or "").strip().lower()


def _normalize_tool_match_text(value: Optional[str]) -> str:
    text = (value or "").strip().lower()
    if not text:
        return ""

    if ":" in text:
        return text.split(":")[-1]

    return text


def _matches_non_consumable_tool_root(value: Optional[str]) -> bool:
    text = _normalize_tool_match_text(value)
    if not text:
        return False

    for root in NON_CONSUMABLE_TOOL_ROOTS:
        if text == root or text.startswith(f"{root}-") or text.startswith(f"{root}_"):
            return True

    return False


def _load_snapshot(conn) -> Tuple[
    Dict[str, CanonicalItem],
    Set[str],
    Set[int],
    Dict[str, List[int]],
    Dict[int, List[str]],
]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, game_code, display_name, lr_item_id, match_tier
            FROM canonical_items
            ORDER BY id
            """
        )
        canonicals = {
            row[0]: CanonicalItem(
                canonical_id=row[0],
                game_code=row[1],
                display_name=row[2] or row[0],
                lr_item_id=row[3],
                match_tier=row[4],
            )
            for row in cur.fetchall()
        }

        cur.execute(
            """
            SELECT canonical_id
            FROM price_overrides
            WHERE unit_price IS NOT NULL
            """
        )
        override_ids = {row[0] for row in cur.fetchall() if row and row[0]}

        cur.execute(
            """
            SELECT id
            FROM lr_items
            WHERE unit_price_current IS NOT NULL
            """
        )
        priced_lr_ids = {row[0] for row in cur.fetchall() if row and row[0] is not None}

        cur.execute(
            """
            SELECT id, output_canonical_id
            FROM recipes
            WHERE output_canonical_id IS NOT NULL
            ORDER BY id
            """
        )
        recipes_by_output: Dict[str, List[int]] = defaultdict(list)
        for recipe_id, output_canonical_id in cur.fetchall():
            recipes_by_output[output_canonical_id].append(recipe_id)

        cur.execute(
            """
            SELECT recipe_id, input_canonical_id, variant_group_id, is_primary_variant
            FROM recipe_ingredients
            ORDER BY recipe_id, id
            """
        )
        ingredients_by_recipe: Dict[int, List[str]] = defaultdict(list)
        for recipe_id, input_canonical_id, variant_group_id, is_primary_variant in cur.fetchall():
            if input_canonical_id is None:
                continue
            if variant_group_id is not None and not is_primary_variant:
                continue
            ingredients_by_recipe[recipe_id].append(input_canonical_id)

    return canonicals, override_ids, priced_lr_ids, recipes_by_output, ingredients_by_recipe


def _direct_lr_priced(item: CanonicalItem, priced_lr_ids: Set[int]) -> bool:
    tier = _normalize_tier(item.match_tier)
    if item.lr_item_id is None:
        return False
    if tier in UNPRICED_MATCH_TIERS:
        return False
    return item.lr_item_id in priced_lr_ids


def main() -> int:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("[ERROR] DATABASE_URL environment variable is not set.")
        return 1

    try:
        with psycopg2.connect(database_url) as conn:
            (
                canonicals,
                override_ids,
                priced_lr_ids,
                recipes_by_output,
                ingredients_by_recipe,
            ) = _load_snapshot(conn)

            tool_match_memo: Dict[str, bool] = {}

            def is_non_consumable_tool_id(canonical_id: str) -> bool:
                cached = tool_match_memo.get(canonical_id)
                if cached is not None:
                    return cached

                item = canonicals.get(canonical_id)
                matched = _matches_non_consumable_tool_root(canonical_id)
                if item is not None:
                    matched = matched or _matches_non_consumable_tool_root(item.game_code)
                    matched = matched or _matches_non_consumable_tool_root(item.display_name)

                tool_match_memo[canonical_id] = matched
                return matched

            ignored_tool_edges_total = 0
            ignored_tool_edges_by_output: Counter[str] = Counter()
            ignored_tool_edges_by_ingredient: Counter[str] = Counter()

            for output_id, recipe_ids in recipes_by_output.items():
                for recipe_id in recipe_ids:
                    for ing_id in ingredients_by_recipe.get(recipe_id, []):
                        if is_non_consumable_tool_id(ing_id):
                            ignored_tool_edges_total += 1
                            ignored_tool_edges_by_output[output_id] += 1
                            ignored_tool_edges_by_ingredient[ing_id] += 1

            priced_memo: Dict[str, bool] = {}

            def is_priced_full(canonical_id: str, depth: int = 0, _visited: Optional[Set[str]] = None) -> bool:
                if canonical_id in priced_memo:
                    return priced_memo[canonical_id]

                if depth > MAX_RECURSION_DEPTH:
                    return False

                if _visited is None:
                    _visited = set()
                if canonical_id in _visited:
                    return False

                item = canonicals.get(canonical_id)
                if item is None:
                    return False

                visited_next = set(_visited)
                visited_next.add(canonical_id)

                if _direct_lr_priced(item, priced_lr_ids):
                    priced_memo[canonical_id] = True
                    return True

                if canonical_id in override_ids:
                    priced_memo[canonical_id] = True
                    return True

                for recipe_id in recipes_by_output.get(canonical_id, []):
                    ingredient_ids = [
                        ing_id
                        for ing_id in ingredients_by_recipe.get(recipe_id, [])
                        if not is_non_consumable_tool_id(ing_id)
                    ]
                    if all(
                        is_priced_full(ing_id, depth + 1, visited_next)
                        for ing_id in ingredient_ids
                    ):
                        priced_memo[canonical_id] = True
                        return True

                priced_memo[canonical_id] = False
                return False

            def find_native_recipe_viability(
                canonical_id: str,
            ) -> Tuple[bool, bool, Optional[str]]:
                recipe_ids = recipes_by_output.get(canonical_id, [])
                if not recipe_ids:
                    return False, False, None

                first_blocking: Optional[str] = None
                for recipe_id in recipe_ids:
                    ingredient_ids = [
                        ing_id
                        for ing_id in ingredients_by_recipe.get(recipe_id, [])
                        if not is_non_consumable_tool_id(ing_id)
                    ]
                    recipe_ok = True
                    for ing_id in ingredient_ids:
                        if not is_priced_full(ing_id, depth=1, _visited={canonical_id}):
                            recipe_ok = False
                            if first_blocking is None:
                                first_blocking = ing_id
                            break
                    if recipe_ok:
                        return True, True, None

                return False, True, first_blocking

            gaps: List[Dict[str, object]] = []
            reason_counts: Counter[str] = Counter()
            total_priced = 0

            for canonical_id, item in canonicals.items():
                fully_priced = is_priced_full(canonical_id)
                if fully_priced:
                    total_priced += 1

                has_direct_lr = _direct_lr_priced(item, priced_lr_ids)
                has_recipe_path, has_recipe, blocking_id = find_native_recipe_viability(canonical_id)

                # Gap candidate = no direct LR and no viable recipe path.
                if has_direct_lr or has_recipe_path:
                    continue

                if canonical_id in override_ids:
                    gap_reason = "no_lr_no_price_override"
                elif not has_recipe:
                    gap_reason = "no_lr_no_recipe"
                else:
                    gap_reason = "no_lr_recipe_incomplete"

                reason_counts[gap_reason] += 1
                blocking_game_code = canonicals.get(blocking_id).game_code if blocking_id in canonicals else None
                gaps.append(
                    {
                        "canonical_id": canonical_id,
                        "game_code": item.game_code,
                        "display_name": item.display_name,
                        "match_tier": item.match_tier,
                        "has_recipe": has_recipe,
                        "gap_reason": gap_reason,
                        "blocking_ingredient_id": blocking_id,
                        "blocking_ingredient_game_code": blocking_game_code,
                    }
                )

            gaps.sort(
                key=lambda row: (
                    str(row.get("gap_reason") or ""),
                    str(row.get("game_code") or ""),
                )
            )

            total_canonicals = len(canonicals)
            total_gaps = len(gaps)
            priced_pct = (total_priced / total_canonicals * 100.0) if total_canonicals else 0.0
            gap_pct = (total_gaps / total_canonicals * 100.0) if total_canonicals else 0.0

            payload = {
                "timestamp": datetime.now().isoformat(timespec="seconds"),
                "total_canonicals": total_canonicals,
                "priced": int(total_priced),
                "gaps": int(total_gaps),
                "no_lr_no_recipe": int(reason_counts.get("no_lr_no_recipe", 0)),
                "no_lr_recipe_incomplete": int(reason_counts.get("no_lr_recipe_incomplete", 0)),
                "no_lr_no_price_override": int(reason_counts.get("no_lr_no_price_override", 0)),
                "ignored_edges_total": int(ignored_tool_edges_total),
                "gap_details": gaps,
                "gap_pct": round(gap_pct, 2),
                "non_consumable_tool_policy": {
                    "ignored_edges_total": ignored_tool_edges_total,
                    "top_impacted_outputs": [
                        {"canonical_id": canonical_id, "ignored_tool_edges": count}
                        for canonical_id, count in ignored_tool_edges_by_output.most_common(25)
                    ],
                    "top_ignored_tool_ingredients": [
                        {"canonical_id": canonical_id, "ignored_as_tool_count": count}
                        for canonical_id, count in ignored_tool_edges_by_ingredient.most_common(25)
                    ],
                },
            }

            os.makedirs(os.path.dirname(REPORT_PATH), exist_ok=True)
            with open(REPORT_PATH, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2, ensure_ascii=False)

            print("--- Pricing Gap Audit ---")
            print(f"Total canonicals   : {total_canonicals}")
            print(f"Priced             : {total_priced} ({priced_pct:.1f}%)")
            print(f"Gaps               : {total_gaps} ({gap_pct:.1f}%)")
            print(f"  no_lr_no_recipe          : {reason_counts.get('no_lr_no_recipe', 0)}")
            print(f"  no_lr_recipe_incomplete  : {reason_counts.get('no_lr_recipe_incomplete', 0)}")
            print(f"  no_lr_no_price_override  : {reason_counts.get('no_lr_no_price_override', 0)}")
            print(f"Ignored tool edges : {ignored_tool_edges_total}")
            print(f"Written to: {REPORT_PATH}")

    except Exception as exc:
        print(f"[ERROR] pricing gap audit failed: {exc}")
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
