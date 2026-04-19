#!/usr/bin/env python3
"""[MEMORY BANK: ACTIVE]
Handoff diagnostics for:
1) none/null unmapped scaffold LR sub-category distribution
2) global unmatched canonical distribution spot-check
3) low-tier unmapped scaffold collision-risk candidates
"""

from __future__ import annotations

import json
import os
from collections import defaultdict

import psycopg2
from dotenv import load_dotenv


def _load_scaffold_ids() -> list[str]:
    with open("data/lr_item_mapping_scaffold.json", "r", encoding="utf-8") as f:
        payload = json.load(f)
    return sorted(str(k).upper() for k in payload.keys() if not str(k).startswith("_"))


def _load_active_mapped_ids() -> list[str]:
    with open("data/lr_item_mapping.json", "r", encoding="utf-8") as f:
        payload = json.load(f)
    ids: list[str] = []
    for key, value in payload.items():
        if str(key).startswith("_"):
            continue
        if isinstance(value, list) and len(value) > 0:
            ids.append(str(key).upper())
    return sorted(ids)


def main() -> int:
    load_dotenv()
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("[ERROR] DATABASE_URL is not set")
        return 1

    scaffold_ids = _load_scaffold_ids()
    mapped_ids = _load_active_mapped_ids()
    unmapped_scaffold_ids = sorted(set(scaffold_ids) - set(mapped_ids))

    print("=== Handoff Snapshot ===")
    print(f"scaffold_total={len(scaffold_ids)}")
    print(f"mapped_active={len(mapped_ids)}")
    print(f"unmapped_scaffold={len(unmapped_scaffold_ids)}")

    with psycopg2.connect(database_url) as conn:
        with conn.cursor() as cur:
            # Task 1: none/null across unmapped scaffold IDs (per-LR-item best-tier view)
            cur.execute(
                """
                WITH unmapped(item_id) AS (
                  SELECT UNNEST(%s::text[])
                ), linked AS (
                  SELECT li.item_id, li.id, li.display_name, li.lr_category, li.lr_sub_category,
                         ci.id AS canonical_id,
                         COALESCE(ci.match_tier, 'none') AS tier,
                         CASE COALESCE(ci.match_tier, 'none')
                           WHEN 'mapped' THEN 1
                           WHEN 'manual' THEN 2
                           WHEN 'exact' THEN 3
                           WHEN 'high' THEN 4
                           WHEN 'low' THEN 5
                           WHEN 'unmatched' THEN 6
                           ELSE 7
                         END AS tier_rank
                  FROM lr_items li
                  JOIN unmapped u ON u.item_id = li.item_id
                  LEFT JOIN canonical_items ci ON ci.lr_item_id = li.id
                ), ranked AS (
                  SELECT *,
                         ROW_NUMBER() OVER (
                           PARTITION BY item_id
                           ORDER BY tier_rank ASC, canonical_id NULLS LAST
                         ) AS rn
                  FROM linked
                )
                SELECT
                  COUNT(*) FILTER (WHERE rn = 1 AND tier = 'none') AS none_or_null_lr_items,
                  COUNT(*) FILTER (WHERE rn = 1) AS total_unmapped_ids
                FROM ranked
                """,
                (unmapped_scaffold_ids,),
            )
            none_or_null_count, total_unmapped = cur.fetchone() or (0, 0)
            print("\n=== Task 1: none/null unmapped scaffold IDs ===")
            print(f"none_or_null={none_or_null_count} of total_unmapped={total_unmapped}")

            cur.execute(
                """
                WITH unmapped(item_id) AS (
                  SELECT UNNEST(%s::text[])
                ), linked AS (
                  SELECT li.item_id, li.id, li.display_name, li.lr_category, li.lr_sub_category,
                         ci.id AS canonical_id,
                         COALESCE(ci.match_tier, 'none') AS tier,
                         CASE COALESCE(ci.match_tier, 'none')
                           WHEN 'mapped' THEN 1
                           WHEN 'manual' THEN 2
                           WHEN 'exact' THEN 3
                           WHEN 'high' THEN 4
                           WHEN 'low' THEN 5
                           WHEN 'unmatched' THEN 6
                           ELSE 7
                         END AS tier_rank
                  FROM lr_items li
                  JOIN unmapped u ON u.item_id = li.item_id
                  LEFT JOIN canonical_items ci ON ci.lr_item_id = li.id
                ), ranked AS (
                  SELECT *,
                         ROW_NUMBER() OVER (
                           PARTITION BY item_id
                           ORDER BY tier_rank ASC, canonical_id NULLS LAST
                         ) AS rn
                  FROM linked
                )
                SELECT COALESCE(NULLIF(TRIM(lr_sub_category), ''), '(null)') AS lr_sub_category,
                       COUNT(DISTINCT item_id) AS item_count
                FROM ranked
                WHERE rn = 1
                  AND tier = 'none'
                GROUP BY 1
                ORDER BY item_count DESC, lr_sub_category ASC
                """,
                (unmapped_scaffold_ids,),
            )
            subcat_rows = cur.fetchall()
            print("\nBy lr_sub_category:")
            for subcat, count in subcat_rows:
                print(f"  {subcat}: {count}")

            cur.execute(
                """
                WITH unmapped(item_id) AS (
                  SELECT UNNEST(%s::text[])
                ), linked AS (
                  SELECT li.item_id,
                         li.display_name,
                         li.lr_sub_category,
                         ci.id AS canonical_id,
                         COALESCE(ci.match_tier, 'none') AS tier,
                         CASE COALESCE(ci.match_tier, 'none')
                           WHEN 'mapped' THEN 1
                           WHEN 'manual' THEN 2
                           WHEN 'exact' THEN 3
                           WHEN 'high' THEN 4
                           WHEN 'low' THEN 5
                           WHEN 'unmatched' THEN 6
                           ELSE 7
                         END AS tier_rank
                  FROM lr_items li
                  JOIN unmapped u ON u.item_id = li.item_id
                  LEFT JOIN canonical_items ci ON ci.lr_item_id = li.id
                ), ranked AS (
                  SELECT *,
                         ROW_NUMBER() OVER (
                           PARTITION BY item_id
                           ORDER BY tier_rank ASC, canonical_id NULLS LAST
                         ) AS rn
                  FROM linked
                )
                SELECT COALESCE(NULLIF(TRIM(lr_sub_category), ''), '(null)') AS lr_sub_category,
                       item_id,
                       display_name
                FROM ranked
                WHERE rn = 1
                  AND tier = 'none'
                ORDER BY lr_sub_category, item_id
                """,
                (unmapped_scaffold_ids,),
            )
            examples: dict[str, list[tuple[str, str]]] = defaultdict(list)
            for subcat, item_id, display_name in cur.fetchall():
                if len(examples[subcat]) < 5:
                    examples[subcat].append((item_id, display_name))

            print("\nExamples (first 5 per lr_sub_category):")
            for subcat in sorted(examples.keys()):
                print(f"  {subcat}: {examples[subcat]}")

            # Task 2: unmatched global spot-check
            cur.execute(
                """
                SELECT
                  CASE
                    WHEN game_code IS NULL THEN '(null)'
                    WHEN game_code LIKE 'item:%' THEN split_part(split_part(game_code, ':', 2), '-', 1)
                    WHEN game_code LIKE 'block:%' THEN 'block:' || split_part(split_part(game_code, ':', 2), '-', 1)
                    ELSE split_part(game_code, ':', 1)
                  END AS family,
                  COUNT(*)
                FROM canonical_items
                WHERE match_tier = 'unmatched'
                GROUP BY 1
                ORDER BY 2 DESC, 1
                """
            )
            print("\n=== Task 2: unmatched family distribution ===")
            for family, count in cur.fetchall():
                print(f"  {family}: {count}")

            watchlist = [
                "item:ingot-iron",
                "item:ingot-copper",
                "item:metalplate-iron",
                "item:metalplate-copper",
                "item:plank-oak",
                "item:plank-pine",
                "item:log-placed-oak-ud",
                "item:leather",
                "item:candle",
                "item:pickaxehead-iron",
                "item:axehead-iron",
                "item:shovelhead-iron",
                "item:sawblade-iron",
                "item:nailsandstrips-iron",
            ]
            cur.execute(
                """
                SELECT game_code, id, display_name
                FROM canonical_items
                WHERE match_tier = 'unmatched'
                  AND game_code = ANY(%s::text[])
                ORDER BY game_code
                """,
                (watchlist,),
            )
            watch_hits = cur.fetchall()
            print(f"\nWatchlist unmatched hits: {len(watch_hits)}")
            for hit in watch_hits:
                print(f"  {hit}")

            # Task 3: low-tier collision risk among unmapped scaffold
            cur.execute(
                """
                WITH unmapped(item_id) AS (
                  SELECT UNNEST(%s::text[])
                ), linked AS (
                  SELECT li.item_id,
                         li.id AS lr_id,
                         li.display_name AS lr_display_name,
                         li.lr_sub_category,
                         ci.id AS canonical_id,
                         ci.game_code,
                         ci.display_name AS canonical_display_name,
                         ci.match_tier,
                         ci.match_score
                  FROM lr_items li
                  JOIN unmapped u ON u.item_id = li.item_id
                  JOIN canonical_items ci ON ci.lr_item_id = li.id
                ), ranked AS (
                  SELECT *,
                    ROW_NUMBER() OVER (
                      PARTITION BY item_id
                      ORDER BY
                        CASE match_tier
                          WHEN 'mapped' THEN 1
                          WHEN 'manual' THEN 2
                          WHEN 'exact' THEN 3
                          WHEN 'high' THEN 4
                          WHEN 'low' THEN 5
                          WHEN 'unmatched' THEN 6
                          ELSE 7
                        END,
                        COALESCE(match_score, 0) DESC,
                        canonical_id
                    ) AS rn
                  FROM linked
                )
                SELECT item_id,
                       lr_id,
                       lr_display_name,
                       lr_sub_category,
                       canonical_id,
                       game_code,
                       canonical_display_name,
                       match_tier,
                       match_score
                FROM ranked
                WHERE rn = 1
                  AND match_tier = 'low'
                ORDER BY item_id
                """,
                (unmapped_scaffold_ids,),
            )
            low_rows = cur.fetchall()
            print("\n=== Task 3: low-tier per LR-item best candidates ===")
            print(f"count={len(low_rows)}")
            for row in low_rows:
                print(f"  {row}")

            if low_rows:
                lr_ids = [int(row[1]) for row in low_rows]
                cur.execute(
                    """
                    SELECT li.item_id,
                           li.display_name,
                           ci.id,
                           ci.game_code,
                           ci.display_name,
                           ci.match_tier,
                           ci.match_score
                    FROM lr_items li
                    JOIN canonical_items ci ON ci.lr_item_id = li.id
                    WHERE li.id = ANY(%s::int[])
                    ORDER BY li.item_id, ci.id
                    """,
                    (lr_ids,),
                )
                print("\nAll linked canonical rows for those low-tier LR items:")
                for row in cur.fetchall():
                    print(f"  {row}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
