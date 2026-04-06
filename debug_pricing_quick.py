#!/usr/bin/env python3
# DEPRECATED: Legacy ad-hoc debug script retained for reference only. Not part of Gen 3 pipeline/runtime.
"""[MEMORY BANK: ACTIVE] Quick non-recursive verification checks."""

import psycopg2

from scripts.resolver import calculate_cost, resolve_canonical_id


def main() -> int:
    conn = psycopg2.connect("postgresql://postgres:FatCatTinHat@localhost:5432/postgres")
    try:
        print("=== RESOLUTION CHECKS ===")
        for text in ["Iron (Anvil)", "Lantern Up"]:
            print(text, "->", resolve_canonical_id(text, conn))

        with conn.cursor() as cur:
            print("\n=== LANTERN METALPLATE VARIANTS (recipe 17057) ===")
            cur.execute(
                """
                SELECT COUNT(*)
                FROM recipe_ingredients
                WHERE recipe_id = 17057
                  AND input_game_code LIKE 'item:metalplate-%'
                """
            )
            print("metalplate_rows:", cur.fetchone()[0])

            print("\n=== LANTERN SPLIT-CANONICAL SHAPE ===")
            cur.execute(
                """
                SELECT ci.id, ci.lr_item_id,
                       EXISTS(SELECT 1 FROM recipes r WHERE r.output_canonical_id = ci.id) AS has_recipes
                FROM canonical_items ci
                WHERE ci.display_name = 'Lantern Up'
                ORDER BY ci.id
                """
            )
            for row in cur.fetchall():
                print(row)

        print("\n=== LANTERN LR + RECIPE ALTERNATIVE CHECK ===")
        lantern_result = calculate_cost("lantern_up_2", "current", conn, 1)
        alt = lantern_result.get("recipe_alternative") or {}
        print("source:", lantern_result.get("source"))
        print("unit_cost:", lantern_result.get("unit_cost"))
        print("has_recipe_alternative:", bool(lantern_result.get("recipe_alternative")))
        print("recipe_alt_unit_cost:", alt.get("unit_cost"))
        print("recipe_alt_ingredient_count:", len(alt.get("ingredients") or []))

        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
