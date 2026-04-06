#!/usr/bin/env python3
"""Inject targeted manual recipe_staging rows for known parser blind spots.

These rows are deterministic and idempotent:
  - Deletes prior rows for the same outputs under source_mod='Manual Overrides'
  - Inserts curated replacements
"""

from __future__ import annotations

import os
import sys
from typing import List, Tuple

import psycopg2
from dotenv import load_dotenv


load_dotenv()


MANUAL_ROWS: List[Tuple[str, str, str, str, str]] = [
    (
        "Manual Overrides",
        "grid",
        "item:tailorsdelight:leatherbundle-nadiyan",
        "1",
        "2x item:tailorsdelight:leather-nadiyan; 1x item:game:stick",
    ),
    (
        "Manual Overrides",
        "grid",
        "item:tailorsdelight:leatherbundle-darkred",
        "1",
        "2x item:tailorsdelight:leather-darkred; 1x item:game:stick",
    ),
    (
        "Manual Overrides",
        "quern",
        "item:em:powdered-ore-magnetite",
        "2",
        "1x item:em:crushed-ore-magnetite",
    ),
]


def main() -> int:
    print("[MEMORY BANK: ACTIVE]")
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("[ERROR] DATABASE_URL environment variable is not set.", file=sys.stderr)
        return 1

    try:
        with psycopg2.connect(database_url) as conn:
            with conn.cursor() as cur:
                outputs = [row[2] for row in MANUAL_ROWS]
                cur.execute(
                    """
                    DELETE FROM recipe_staging
                    WHERE source_mod = 'Manual Overrides'
                      AND output_game_code = ANY(%s)
                    """,
                    (outputs,),
                )
                deleted = cur.rowcount

                cur.executemany(
                    """
                    INSERT INTO recipe_staging (
                        source_mod,
                        recipe_type,
                        output_game_code,
                        output_qty_raw,
                        ingredients_raw
                    ) VALUES (%s, %s, %s, %s, %s)
                    """,
                    MANUAL_ROWS,
                )

        print(f"Deleted prior manual rows: {deleted}")
        print(f"Inserted manual rows: {len(MANUAL_ROWS)}")
        print("[OK] Manual recipe staging injection complete.")
        return 0
    except Exception as exc:
        print(f"[ERROR] Failed applying manual recipe staging: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
