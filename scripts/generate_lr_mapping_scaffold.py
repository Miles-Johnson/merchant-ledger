#!/usr/bin/env python3
"""[MEMORY BANK: ACTIVE] Generate/merge LR mapping scaffold from DB state."""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from typing import Any, Dict, List

import psycopg2
from dotenv import load_dotenv


load_dotenv()


SCAFFOLD_PATH = os.path.join("data", "lr_item_mapping_scaffold.json")


def _load_existing_scaffold() -> Dict[str, Any]:
    if not os.path.exists(SCAFFOLD_PATH):
        return {}
    try:
        with open(SCAFFOLD_PATH, "r", encoding="utf-8") as f:
            payload = json.load(f)
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def _sanitize_codes(codes: List[str]) -> List[str]:
    cleaned = sorted({(code or "").strip().lower() for code in codes if (code or "").strip()})
    return cleaned


def main() -> int:
    print("[MEMORY BANK: ACTIVE]")
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("[ERROR] DATABASE_URL environment variable is not set.", file=sys.stderr)
        return 1

    existing = _load_existing_scaffold()

    scaffold: Dict[str, Any] = {
        "_schema": "LR item_id -> list of authoritative game_code targets",
        "_version": 1,
        "_status": "scaffold",
        "_generated_at": datetime.now().isoformat(timespec="seconds"),
        "_notes": [
            "This is a scaffold file. Review and promote curated entries to data/lr_item_mapping.json with _status='active'.",
            "Re-running this script preserves existing scaffold entries and appends missing LR item_id keys.",
        ],
        "_force_unlinked": existing.get("_force_unlinked", []),
    }

    preserved_entries = 0
    appended_entries = 0

    with psycopg2.connect(database_url) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT li.item_id,
                       li.id,
                       li.display_name,
                       li.lr_sub_category,
                       array_remove(array_agg(DISTINCT ci.game_code), NULL) AS linked_codes
                FROM lr_items li
                LEFT JOIN canonical_items ci ON ci.lr_item_id = li.id
                WHERE li.item_id IS NOT NULL
                  AND btrim(li.item_id) <> ''
                GROUP BY li.item_id, li.id, li.display_name, li.lr_sub_category
                ORDER BY li.item_id
                """
            )
            rows = cur.fetchall()

    for item_id, _lr_id, _name, _subcat, linked_codes in rows:
        item_id = (item_id or "").strip().upper()
        if not item_id:
            continue

        if item_id in existing and not str(item_id).startswith("_"):
            scaffold[item_id] = existing[item_id]
            preserved_entries += 1
            continue

        scaffold[item_id] = _sanitize_codes(list(linked_codes or []))
        appended_entries += 1

    # Preserve any existing non-metadata keys not currently present in DB.
    for key, value in existing.items():
        if str(key).startswith("_"):
            continue
        if key not in scaffold:
            scaffold[key] = value
            preserved_entries += 1

    os.makedirs(os.path.dirname(SCAFFOLD_PATH), exist_ok=True)
    with open(SCAFFOLD_PATH, "w", encoding="utf-8") as f:
        json.dump(scaffold, f, indent=2, ensure_ascii=False)
        f.write("\n")

    print(f"Scaffold written: {SCAFFOLD_PATH}")
    print(f"Scaffold updated: {appended_entries} new entries added, {preserved_entries} existing entries preserved")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
