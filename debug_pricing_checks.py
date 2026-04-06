#!/usr/bin/env python3
# DEPRECATED: Legacy ad-hoc debug script retained for reference only. Not part of Gen 3 pipeline/runtime.
"""[MEMORY BANK: ACTIVE]
Quick verification script for resolver/pricing behavior.
"""

from __future__ import annotations

import psycopg2

from scripts.resolver import calculate_cost, resolve_canonical_id


DB_URL = "postgresql://postgres:FatCatTinHat@localhost:5432/postgres"


def print_item_check(name: str, conn) -> None:
    cid = resolve_canonical_id(name, conn)
    result = calculate_cost(cid, "current", conn, 1) if cid else None

    print(f"\n{name}")
    print(f"  canonical_id: {cid}")
    if not result:
        print("  result: not found")
        return

    alt = result.get("recipe_alternative") or {}
    print(f"  source: {result.get('source')}")
    print(f"  unit_cost: {result.get('unit_cost')}")
    print(f"  has_recipe_alternative: {bool(result.get('recipe_alternative'))}")
    if alt:
        print(f"  recipe_alt_source: {alt.get('source')}")
        print(f"  recipe_alt_unit_cost: {alt.get('unit_cost')}")
        ingredients = alt.get("ingredients") or []
        print("  recipe_alt_ingredients:")
        for ing in ingredients[:8]:
            print(
                f"    - {ing.get('display_name')} | qty={ing.get('quantity')}"
                f" | unit={ing.get('unit_cost')} | total={ing.get('total_cost')}"
            )


def main() -> int:
    with psycopg2.connect(DB_URL) as conn:
        with conn.cursor() as cur:
            print("=== Lantern variant ingredient rows (recipe 17057) ===")
            cur.execute(
                """
                SELECT ri.input_game_code, ri.input_canonical_id, ri.qty, ri.variant_group_id, ri.is_primary_variant
                FROM recipe_ingredients ri
                WHERE ri.recipe_id = 17057
                ORDER BY ri.variant_group_id NULLS LAST, ri.input_game_code
                """
            )
            rows = cur.fetchall()
            print(f"rows: {len(rows)}")
            for row in rows[:20]:
                print(row)

        print("\n=== Resolver + cost checks ===")
        print_item_check("Iron (Anvil)", conn)
        print_item_check("Lantern Up", conn)
        print_item_check("Clothes Nadiya Waist Miner Accessories", conn)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
