#!/usr/bin/env python3
# DEPRECATED: Legacy one-off investigation script retained for reference only. Not part of Gen 3 pipeline/runtime.
import os

import psycopg2
from dotenv import load_dotenv


def main() -> int:
    load_dotenv()
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("DATABASE_URL is not set")
        return 1

    with psycopg2.connect(database_url) as conn:
        with conn.cursor() as cur:
            print("=== Candle canonical items ===")
            cur.execute(
                """
                SELECT id, game_code, display_name, lr_item_id, match_tier
                FROM canonical_items
                WHERE display_name ILIKE '%candle%'
                   OR game_code ILIKE '%candle%'
                ORDER BY id
                LIMIT 30
                """
            )
            for row in cur.fetchall():
                print(row)

            print("\n=== Candle recipe outputs ===")
            cur.execute(
                """
                SELECT output_game_code, output_canonical_id, recipe_type, source_mod
                FROM recipes
                WHERE lower(output_game_code) = 'item:candle'
                ORDER BY id
                LIMIT 20
                """
            )
            for row in cur.fetchall():
                print(row)

            print("\n=== Remaining case-mismatch duplicate canonical game_codes ===")
            cur.execute(
                """
                WITH c AS (
                  SELECT id, game_code, lower(game_code) AS code_l
                  FROM canonical_items
                  WHERE game_code IS NOT NULL
                )
                SELECT COUNT(*)
                FROM (
                  SELECT code_l
                  FROM c
                  GROUP BY code_l
                  HAVING COUNT(*) > 1
                ) t
                """
            )
            print(cur.fetchone()[0])

            print("\n=== Remaining uppercase-prefixed recipe outputs ===")
            cur.execute(
                """
                SELECT COUNT(DISTINCT output_game_code)
                FROM recipes
                WHERE output_game_code ~ '^[A-Z]'
                """
            )
            print(cur.fetchone()[0])

            print("\n=== Beeswax/flaxfibers canonical + LR linkage ===")
            cur.execute(
                """
                SELECT ci.id, ci.game_code, ci.display_name, ci.lr_item_id, li.unit_price_current
                FROM canonical_items ci
                LEFT JOIN lr_items li ON li.id = ci.lr_item_id
                WHERE ci.game_code IN ('item:beeswax','item:flaxfibers')
                ORDER BY ci.game_code
                """
            )
            for row in cur.fetchall():
                print(row)

            print("\n=== Beeswax/flaxfibers as recipe outputs ===")
            cur.execute(
                """
                SELECT r.output_game_code, r.output_canonical_id, r.recipe_type, r.source_mod
                FROM recipes r
                WHERE r.output_game_code IN ('item:beeswax','item:flaxfibers')
                ORDER BY r.output_game_code, r.id
                LIMIT 20
                """
            )
            for row in cur.fetchall():
                print(row)

            print("\n=== Beeswax/flaxfibers as ingredients ===")
            cur.execute(
                """
                SELECT ri.input_game_code, COUNT(*)
                FROM recipe_ingredients ri
                WHERE ri.input_game_code IN ('item:beeswax','item:flaxfibers')
                GROUP BY ri.input_game_code
                ORDER BY ri.input_game_code
                """
            )
            for row in cur.fetchall():
                print(row)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())