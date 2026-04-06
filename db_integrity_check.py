#!/usr/bin/env python3
"""Database integrity and data-quality checks for canonical/LR/FTA pipeline."""

from __future__ import annotations

import os
import sys
from typing import Iterable, Sequence

import psycopg2
from dotenv import load_dotenv


MAX_EXAMPLES = 10


def print_header(title: str) -> None:
    print("\n" + "=" * 78)
    print(title)
    print("-" * 78)


def verdict_line(label: str, count: int, verdict: str) -> None:
    icon = {"PASS": "[PASS]", "WARN": "[WARN]", "FAIL": "[FAIL]"}.get(verdict, "[INFO]")
    print(f"{label:<62} {count:>8}  {icon} {verdict}")


def print_examples(columns: Sequence[str], rows: Iterable[Sequence], title: str = "Examples") -> None:
    rows = list(rows)
    if not rows:
        return
    print(f"\n{title} (up to {MAX_EXAMPLES}):")
    print("  " + " | ".join(columns))
    for row in rows:
        print("  " + " | ".join("NULL" if v is None else str(v) for v in row))


def main() -> int:
    load_dotenv()
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        print("[ERROR] DATABASE_URL not found in environment/.env", file=sys.stderr)
        return 1

    print("Live PostgreSQL Integrity & Data Quality Report")

    try:
        with psycopg2.connect(db_url) as conn:
            with conn.cursor() as cur:
                # 1) FK integrity
                print_header("CHECK 1: FK integrity")

                cur.execute(
                    """
                    SELECT ci.id, ci.display_name, ci.fta_item_id
                    FROM canonical_items ci
                    LEFT JOIN fta_items fi ON fi.id = ci.fta_item_id
                    WHERE ci.fta_item_id IS NOT NULL
                      AND fi.id IS NULL
                    ORDER BY ci.id
                    LIMIT %s
                    """,
                    (MAX_EXAMPLES,),
                )
                bad_fta_examples = cur.fetchall()
                cur.execute(
                    """
                    SELECT COUNT(*)
                    FROM canonical_items ci
                    LEFT JOIN fta_items fi ON fi.id = ci.fta_item_id
                    WHERE ci.fta_item_id IS NOT NULL
                      AND fi.id IS NULL
                    """
                )
                bad_fta_count = cur.fetchone()[0]

                cur.execute(
                    """
                    SELECT ci.id, ci.display_name, ci.lr_item_id
                    FROM canonical_items ci
                    LEFT JOIN lr_items li ON li.id = ci.lr_item_id
                    WHERE ci.lr_item_id IS NOT NULL
                      AND li.id IS NULL
                    ORDER BY ci.id
                    LIMIT %s
                    """,
                    (MAX_EXAMPLES,),
                )
                bad_lr_examples = cur.fetchall()
                cur.execute(
                    """
                    SELECT COUNT(*)
                    FROM canonical_items ci
                    LEFT JOIN lr_items li ON li.id = ci.lr_item_id
                    WHERE ci.lr_item_id IS NOT NULL
                      AND li.id IS NULL
                    """
                )
                bad_lr_count = cur.fetchone()[0]

                verdict_line("Dangling canonical_items.fta_item_id refs", bad_fta_count, "PASS" if bad_fta_count == 0 else "FAIL")
                verdict_line("Dangling canonical_items.lr_item_id refs", bad_lr_count, "PASS" if bad_lr_count == 0 else "FAIL")
                print_examples(["canonical_id", "display_name", "fta_item_id"], bad_fta_examples)
                print_examples(["canonical_id", "display_name", "lr_item_id"], bad_lr_examples)

                # 2) Orphaned FTA items
                print_header("CHECK 2: Orphaned FTA items")
                cur.execute(
                    """
                    SELECT fi.id, fi.item_id, fi.display_name, fi.fta_category
                    FROM fta_items fi
                    LEFT JOIN canonical_items ci ON ci.fta_item_id = fi.id
                    WHERE ci.id IS NULL
                    ORDER BY fi.id
                    LIMIT %s
                    """,
                    (MAX_EXAMPLES,),
                )
                orphan_fta_examples = cur.fetchall()
                cur.execute(
                    """
                    SELECT COUNT(*)
                    FROM fta_items fi
                    LEFT JOIN canonical_items ci ON ci.fta_item_id = fi.id
                    WHERE ci.id IS NULL
                    """
                )
                orphan_fta_count = cur.fetchone()[0]
                verdict_line("FTA items not linked from any canonical", orphan_fta_count, "PASS" if orphan_fta_count == 0 else "WARN")
                print_examples(["fta_id", "item_id", "display_name", "fta_category"], orphan_fta_examples)

                # 3) Duplicate canonical names
                print_header("CHECK 3: Duplicate canonical display names")
                cur.execute(
                    """
                    SELECT display_name, COUNT(*)
                    FROM canonical_items
                    WHERE display_name IS NOT NULL
                      AND btrim(display_name) <> ''
                    GROUP BY display_name
                    HAVING COUNT(*) > 1
                    ORDER BY COUNT(*) DESC, display_name
                    LIMIT %s
                    """,
                    (MAX_EXAMPLES,),
                )
                duplicate_name_examples = cur.fetchall()
                cur.execute(
                    """
                    SELECT COUNT(*)
                    FROM (
                        SELECT display_name
                        FROM canonical_items
                        WHERE display_name IS NOT NULL
                          AND btrim(display_name) <> ''
                        GROUP BY display_name
                        HAVING COUNT(*) > 1
                    ) d
                    """
                )
                duplicate_name_groups = cur.fetchone()[0]

                verdict_line("Duplicate display_name groups in canonical_items", duplicate_name_groups, "PASS" if duplicate_name_groups == 0 else "WARN")
                print_examples(["display_name", "count"], duplicate_name_examples)

                # 4) Pricing coverage
                print_header("CHECK 4: Pricing coverage")
                cur.execute(
                    """
                    SELECT
                      SUM(CASE WHEN lr_item_id IS NOT NULL AND fta_item_id IS NULL THEN 1 ELSE 0 END) AS lr_only,
                      SUM(CASE WHEN lr_item_id IS NULL AND fta_item_id IS NOT NULL THEN 1 ELSE 0 END) AS fta_only,
                      SUM(CASE WHEN lr_item_id IS NOT NULL AND fta_item_id IS NOT NULL THEN 1 ELSE 0 END) AS both,
                      SUM(CASE WHEN lr_item_id IS NULL AND fta_item_id IS NULL THEN 1 ELSE 0 END) AS neither
                    FROM canonical_items
                    """
                )
                lr_only, fta_only, both, neither = cur.fetchone()

                verdict_line("Canonicals with LR only", lr_only or 0, "PASS")
                verdict_line("Canonicals with FTA only", fta_only or 0, "PASS")
                verdict_line("Canonicals with both LR and FTA", both or 0, "PASS")
                verdict_line("Canonicals with neither LR nor FTA", neither or 0, "WARN" if (neither or 0) > 0 else "PASS")

                cur.execute(
                    """
                    SELECT ci.id, ci.display_name, ci.game_code
                    FROM canonical_items ci
                    WHERE ci.lr_item_id IS NULL
                      AND ci.fta_item_id IS NULL
                      AND NOT EXISTS (
                        SELECT 1 FROM recipes r
                        WHERE r.output_canonical_id = ci.id
                      )
                    ORDER BY ci.display_name NULLS LAST, ci.id
                    LIMIT %s
                    """,
                    (MAX_EXAMPLES,),
                )
                dead_end_examples = cur.fetchall()
                cur.execute(
                    """
                    SELECT COUNT(*)
                    FROM canonical_items ci
                    WHERE ci.lr_item_id IS NULL
                      AND ci.fta_item_id IS NULL
                      AND NOT EXISTS (
                        SELECT 1 FROM recipes r
                        WHERE r.output_canonical_id = ci.id
                      )
                    """
                )
                dead_end_count = cur.fetchone()[0]

                verdict_line(
                    "Dead-end canonicals (no LR/FTA and no recipe fallback)",
                    dead_end_count,
                    "PASS" if dead_end_count == 0 else "FAIL",
                )
                print_examples(["canonical_id", "display_name", "game_code"], dead_end_examples)

                # 5) Suspicious trigram links
                print_header("CHECK 5: Suspicious trigram FTA links (< 0.7 similarity)")
                cur.execute(
                    """
                    SELECT ci.id,
                           ci.display_name,
                           fi.id,
                           fi.display_name,
                           similarity(lower(ci.display_name), lower(fi.display_name)) AS sim
                    FROM canonical_items ci
                    JOIN fta_items fi ON fi.id = ci.fta_item_id
                    WHERE ci.fta_item_id IS NOT NULL
                      AND similarity(lower(ci.display_name), lower(fi.display_name)) < 0.7
                    ORDER BY sim ASC, ci.id
                    LIMIT %s
                    """,
                    (MAX_EXAMPLES,),
                )
                suspicious_examples = cur.fetchall()
                cur.execute(
                    """
                    SELECT COUNT(*)
                    FROM canonical_items ci
                    JOIN fta_items fi ON fi.id = ci.fta_item_id
                    WHERE ci.fta_item_id IS NOT NULL
                      AND similarity(lower(ci.display_name), lower(fi.display_name)) < 0.7
                    """
                )
                suspicious_count = cur.fetchone()[0]
                verdict_line("FTA-linked canonicals below 0.7 trigram similarity", suspicious_count, "PASS" if suspicious_count == 0 else "WARN")
                print_examples(
                    ["canonical_id", "canonical_name", "fta_id", "fta_name", "similarity"],
                    [(a, b, c, d, f"{e:.3f}") for a, b, c, d, e in suspicious_examples],
                )

                # 6) Labor markup scope check
                print_header("CHECK 6: Labor markup scope (FTA artisan category sanity)")
                cur.execute(
                    """
                    SELECT COALESCE(fta_category, '<NULL>') AS fta_category, COUNT(*)
                    FROM fta_items
                    GROUP BY COALESCE(fta_category, '<NULL>')
                    ORDER BY COUNT(*) DESC, fta_category
                    """
                )
                category_counts = cur.fetchall()
                artisan_count = 0
                total_fta = 0
                for category, count in category_counts:
                    total_fta += count
                    if str(category).lower() == "artisan":
                        artisan_count = count

                non_artisan_count = total_fta - artisan_count
                verdict_line("FTA items with category = 'artisan'", artisan_count, "PASS")
                verdict_line("FTA items in all other categories", non_artisan_count, "PASS")
                print_examples(["fta_category", "count"], category_counts[:MAX_EXAMPLES], title="Category distribution")

                # 7) Recipe coverage: all ingredients unpriced
                print_header("CHECK 7: Recipes where all ingredients are unpriced")
                cur.execute(
                    """
                    WITH ingredient_flags AS (
                        SELECT
                            r.id AS recipe_id,
                            r.output_canonical_id,
                            r.output_game_code,
                            r.recipe_type,
                            COUNT(ri.id) AS ingredient_count,
                            SUM(
                                CASE
                                    WHEN ri.input_canonical_id IS NULL THEN 1
                                    WHEN ci.lr_item_id IS NULL AND ci.fta_item_id IS NULL THEN 1
                                    ELSE 0
                                END
                            ) AS unpriced_count
                        FROM recipes r
                        JOIN recipe_ingredients ri ON ri.recipe_id = r.id
                        LEFT JOIN canonical_items ci ON ci.id = ri.input_canonical_id
                        GROUP BY r.id, r.output_canonical_id, r.output_game_code, r.recipe_type
                    )
                    SELECT recipe_id, output_canonical_id, output_game_code, recipe_type, ingredient_count
                    FROM ingredient_flags
                    WHERE ingredient_count > 0
                      AND ingredient_count = unpriced_count
                    ORDER BY recipe_id
                    LIMIT %s
                    """,
                    (MAX_EXAMPLES,),
                )
                zero_price_recipe_examples = cur.fetchall()
                cur.execute(
                    """
                    WITH ingredient_flags AS (
                        SELECT
                            r.id AS recipe_id,
                            COUNT(ri.id) AS ingredient_count,
                            SUM(
                                CASE
                                    WHEN ri.input_canonical_id IS NULL THEN 1
                                    WHEN ci.lr_item_id IS NULL AND ci.fta_item_id IS NULL THEN 1
                                    ELSE 0
                                END
                            ) AS unpriced_count
                        FROM recipes r
                        JOIN recipe_ingredients ri ON ri.recipe_id = r.id
                        LEFT JOIN canonical_items ci ON ci.id = ri.input_canonical_id
                        GROUP BY r.id
                    )
                    SELECT COUNT(*)
                    FROM ingredient_flags
                    WHERE ingredient_count > 0
                      AND ingredient_count = unpriced_count
                    """
                )
                zero_price_recipe_count = cur.fetchone()[0]

                verdict_line(
                    "Recipes with all ingredients unpriced",
                    zero_price_recipe_count,
                    "PASS" if zero_price_recipe_count == 0 else "WARN",
                )
                print_examples(
                    ["recipe_id", "output_canonical_id", "output_game_code", "recipe_type", "ingredient_count"],
                    zero_price_recipe_examples,
                )

        print("\n" + "=" * 78)
        print("Report complete.")
        print("=" * 78)
        return 0
    except Exception as exc:
        print(f"[ERROR] Failed to run checks: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
