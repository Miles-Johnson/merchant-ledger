#!/usr/bin/env python3
"""[MEMORY BANK: ACTIVE] Diagnose alias-resolution collisions (plate/material vs armor)."""

from __future__ import annotations

import os
import sys
import json
from collections import defaultdict
from pathlib import Path

import psycopg2
from dotenv import load_dotenv


sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from scripts.resolver import calculate_cost, resolve_canonical_id


MAPPING_FILE = Path("data/lr_item_mapping.json")
MAPPING_WARNINGS_FILE = Path("data/lr_mapping_warnings.json")


def _load_mapping_game_codes() -> set[str]:
    if not MAPPING_FILE.exists():
        return set()
    try:
        payload = json.loads(MAPPING_FILE.read_text(encoding="utf-8"))
    except Exception:
        return set()

    if not isinstance(payload, dict):
        return set()

    codes: set[str] = set()
    for key, value in payload.items():
        if str(key).startswith("_"):
            continue
        if not isinstance(value, list):
            continue
        for code in value:
            if isinstance(code, str) and code.strip():
                normalized = code.strip().lower()
                if ":" not in normalized:
                    normalized = f"item:{normalized}"
                codes.add(normalized)
    return codes


def _load_mapping_warnings() -> dict:
    if not MAPPING_WARNINGS_FILE.exists():
        return {}
    try:
        payload = json.loads(MAPPING_WARNINGS_FILE.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def _canonical_family_from_game_code(game_code: str | None) -> str:
    code = (game_code or "").lower()
    if code.startswith("item:ingot-"):
        return "ingot"
    if code.startswith("item:metalplate-"):
        return "metalplate"
    if "-plate-" in code and code.startswith("item:armor-"):
        return "armor_plate"
    if "-chain-" in code and code.startswith("item:armor-"):
        return "armor_chain"
    if code.startswith("item:metalchain-") or code.startswith("item:chain-"):
        return "chain_material"
    if code.startswith("item:metalbit-"):
        return "metalbit"
    if code.startswith("item:nugget-"):
        return "nugget"
    if code.startswith("item:ore-"):
        return "ore"
    if code.startswith("item:crushed-") or code.startswith("item:powdered-"):
        return "ore_derivative"
    return "other"


def _print_resolution(conn, query_text: str) -> None:
    canonical_id = resolve_canonical_id(query_text, conn)
    if canonical_id is None:
        print(f"{query_text!r} -> NOT FOUND")
        return

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, display_name, game_code, lr_item_id
            FROM canonical_items
            WHERE id = %s
            """,
            (canonical_id,),
        )
        row = cur.fetchone()

    result = calculate_cost(canonical_id, "current", conn, 1)
    source = result.get("source")
    total = result.get("total_cost")
    crafting = result.get("crafting_cost")

    print(
        f"{query_text!r} -> {row[0]} | name={row[1]!r} game={row[2]!r} lr_id={row[3]} "
        f"| source={source} total={total} crafting={crafting}"
    )


def _print_exact_alias_rows(conn, alias_text: str) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT ia.alias, ia.canonical_id, ci.display_name, ci.game_code, ci.lr_item_id
            FROM item_aliases ia
            JOIN canonical_items ci ON ci.id = ia.canonical_id
            WHERE ia.alias = %s
            ORDER BY ci.id
            """,
            (alias_text,),
        )
        rows = cur.fetchall()

    print(f"\nAlias {alias_text!r}: {len(rows)} canonical match(es)")
    for row in rows:
        print("  ", row)


def _print_ranked_candidates(conn, query_text: str, limit: int = 12) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT ia.canonical_id, ia.alias, ci.display_name, ci.game_code, ci.lr_item_id,
                   similarity(ia.alias, %s) AS sim
            FROM item_aliases ia
            JOIN canonical_items ci ON ci.id = ia.canonical_id
            WHERE similarity(ia.alias, %s) > 0.3
            ORDER BY
                CASE WHEN ia.alias = %s THEN 0 ELSE 1 END,
                similarity(ia.alias, %s) DESC,
                CASE WHEN ci.lr_item_id IS NOT NULL THEN 0 ELSE 1 END,
                ci.id
            LIMIT %s
            """,
            (query_text, query_text, query_text, query_text, limit),
        )
        rows = cur.fetchall()

    print(f"\nTop candidates for {query_text!r}:")
    for row in rows:
        print("  ", row)


def _print_match_tier_distribution(conn) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT coalesce(match_tier, 'none') AS tier, COUNT(*)
            FROM canonical_items
            GROUP BY coalesce(match_tier, 'none')
            ORDER BY tier
            """
        )
        rows = cur.fetchall()

    print("\nMatch-tier distribution:")
    for tier, count in rows:
        print(f"  {tier}: {count}")


def _print_mapped_vs_fallback_summary(conn) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
                COUNT(*) FILTER (WHERE ci.lr_item_id IS NOT NULL AND ci.match_tier = 'mapped') AS mapped,
                COUNT(*) FILTER (WHERE ci.lr_item_id IS NOT NULL AND coalesce(ci.match_tier, '') <> 'mapped') AS fallback,
                COUNT(*) FILTER (WHERE ci.lr_item_id IS NULL) AS unlinked
            FROM canonical_items ci
            """
        )
        row = cur.fetchone() or (0, 0, 0)

    print("\nMapped vs fallback-linked canonical summary:")
    print(f"  mapped-linked: {row[0]}")
    print(f"  fallback-linked: {row[1]}")
    print(f"  lr-unlinked: {row[2]}")


def _print_unresolved_lr_item_ids(conn) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT li.item_id, li.id, li.display_name, li.lr_sub_category
            FROM lr_items li
            LEFT JOIN canonical_items ci ON ci.lr_item_id = li.id
            WHERE ci.id IS NULL
            ORDER BY li.item_id
            """
        )
        rows = cur.fetchall()

    print(f"\nUnresolved LR item IDs (no canonical link): {len(rows)}")
    for row in rows[:100]:
        print("  ", row)
    if len(rows) > 100:
        print(f"  ... ({len(rows)-100} more)")


def _print_lr_cross_family_collisions(conn) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT li.item_id, li.id, li.display_name, li.lr_sub_category,
                   ci.id, ci.game_code, ci.match_tier
            FROM lr_items li
            JOIN canonical_items ci ON ci.lr_item_id = li.id
            ORDER BY li.item_id, ci.id
            """
        )
        rows = cur.fetchall()

    bucket: dict[tuple, list[tuple]] = defaultdict(list)
    for lr_item_id, lr_id, lr_name, lr_subcat, canonical_id, game_code, match_tier in rows:
        fam = _canonical_family_from_game_code(game_code)
        bucket[(lr_item_id, lr_id, lr_name, lr_subcat)].append((canonical_id, game_code, match_tier, fam))

    collisions: list[tuple] = []
    for lr_key, linked in bucket.items():
        families = {entry[3] for entry in linked}
        if len(families) > 1:
            collisions.append((lr_key, families, linked))

    print(f"\nCross-family LR collisions: {len(collisions)}")
    for lr_key, families, linked in collisions[:50]:
        print(f"  LR {lr_key} families={sorted(families)}")
        for entry in linked:
            print("    ", entry)
    if len(collisions) > 50:
        print(f"  ... ({len(collisions)-50} more)")


def _print_fuzzy_survivor_candidates(conn) -> None:
    mapped_codes = _load_mapping_game_codes()
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, game_code, display_name, lr_item_id, match_tier
            FROM canonical_items
            WHERE lr_item_id IS NOT NULL
              AND match_tier = 'exact'
              AND game_code IS NOT NULL
            ORDER BY id
            """
        )
        rows = cur.fetchall()

    survivors = [row for row in rows if (row[1] or "").lower() not in mapped_codes]
    print(f"\nFuzzy-survivor curation candidates (exact tier without mapping): {len(survivors)}")
    for row in survivors[:100]:
        print("  ", row)
    if len(survivors) > 100:
        print(f"  ... ({len(survivors)-100} more)")


def _print_mapping_warning_snapshot() -> None:
    payload = _load_mapping_warnings()
    print("\nMapping warning snapshot (data/lr_mapping_warnings.json):")
    if not payload:
        print("  none")
        return
    print(json.dumps(payload, indent=2, ensure_ascii=False))


def main() -> int:
    load_dotenv()
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("[ERROR] DATABASE_URL is not set")
        return 1

    queries = [
        "iron plate",
        "iron metalplate",
        "meteoriciron plate",
        "meteoric iron plate",
        "meteoric plate armor",
        "iron plate armor",
        "copper plate",
        "steel plate",
        "tinbronze plate",
    ]

    with psycopg2.connect(database_url) as conn:
        print("=" * 80)
        print("0) Tier + mapping diagnostics")
        print("=" * 80)
        _print_match_tier_distribution(conn)
        _print_mapped_vs_fallback_summary(conn)
        _print_mapping_warning_snapshot()

        print("=" * 80)
        print("1) Resolution behavior")
        print("=" * 80)
        for q in queries:
            _print_resolution(conn, q)

        print("\n" + "=" * 80)
        print("2) Exact alias collisions")
        print("=" * 80)
        for alias in [
            "iron plate",
            "copper plate",
            "steel plate",
            "tinbronze plate",
            "meteoriciron plate",
            "meteoric iron plate",
        ]:
            _print_exact_alias_rows(conn, alias)

        print("\n" + "=" * 80)
        print("3) Ranked candidates under current resolver ordering")
        print("=" * 80)
        for q in ["iron plate", "meteoriciron plate", "meteoric iron plate"]:
            _print_ranked_candidates(conn, q)

        print("\n" + "=" * 80)
        print("4) LR linkage hygiene")
        print("=" * 80)
        _print_unresolved_lr_item_ids(conn)
        _print_lr_cross_family_collisions(conn)
        _print_fuzzy_survivor_candidates(conn)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
