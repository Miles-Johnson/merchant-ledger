#!/usr/bin/env python3
"""Compute primitive fallback price overrides from deterministic LR-derived rules.

Rules are intentionally ordered and idempotent. Existing manual overrides are
never overwritten; only missing overrides or prior computed overrides are
inserted/updated.
"""

from __future__ import annotations

import os
import sys
import traceback
from dataclasses import dataclass
from decimal import Decimal
from typing import List, Sequence, Tuple

import psycopg2
from dotenv import load_dotenv


load_dotenv()


@dataclass(frozen=True)
class Rule:
    name: str
    target_query: str
    unit_price: Decimal
    note: str
    params: Tuple[object, ...] = ()


def ensure_price_overrides_table(cur) -> None:
    cur.execute("SELECT to_regclass('public.price_overrides')")
    row = cur.fetchone()
    if row and row[0]:
        return

    cur.execute(
        """
        CREATE TABLE price_overrides (
            canonical_id TEXT PRIMARY KEY REFERENCES canonical_items(id),
            unit_price NUMERIC NOT NULL,
            note TEXT,
            created_at TIMESTAMPTZ DEFAULT NOW()
        )
        """
    )
    print("[INFO] Created missing table: price_overrides")


def _is_computed_note(note: str | None) -> bool:
    return bool(note and note.lower().startswith("computed:"))


def _select_target_ids(cur, query: str, params: Sequence[object]) -> List[str]:
    if params:
        cur.execute(query, params)
    else:
        cur.execute(query)
    return [row[0] for row in cur.fetchall() if row and row[0]]


def _upsert_computed(cur, canonical_id: str, unit_price: Decimal, note: str) -> int:
    cur.execute(
        """
        INSERT INTO price_overrides (canonical_id, unit_price, note, created_at)
        VALUES (%s, %s, %s, NOW())
        ON CONFLICT (canonical_id) DO UPDATE
        SET unit_price = EXCLUDED.unit_price,
            note = EXCLUDED.note
        WHERE price_overrides.note ILIKE 'computed:%%'
        """,
        (canonical_id, unit_price, note),
    )
    return cur.rowcount


def apply_rule(cur, rule: Rule) -> Tuple[int, int, int, int]:
    target_ids = _select_target_ids(cur, rule.target_query, rule.params)

    inserted = 0
    updated = 0
    skipped_manual = 0

    for canonical_id in target_ids:
        cur.execute(
            "SELECT note FROM price_overrides WHERE canonical_id = %s",
            (canonical_id,),
        )
        row = cur.fetchone()

        if row is None:
            changed = _upsert_computed(cur, canonical_id, rule.unit_price, rule.note)
            if changed:
                inserted += 1
            continue

        existing_note = row[0]
        if not _is_computed_note(existing_note):
            skipped_manual += 1
            continue

        changed = _upsert_computed(cur, canonical_id, rule.unit_price, rule.note)
        if changed:
            updated += 1

    total_targets = len(target_ids)
    return inserted, updated, skipped_manual, total_targets


def get_price(cur, canonical_id: str) -> Decimal | None:
    """Get the best available price for a canonical item (LR > override)."""
    cur.execute(
        """
        SELECT COALESCE(li.unit_price_current, po.unit_price)
        FROM canonical_items ci
        LEFT JOIN lr_items li ON li.id = ci.lr_item_id
        LEFT JOIN price_overrides po ON po.canonical_id = ci.id
        WHERE ci.id = %s
        """,
        (canonical_id,),
    )
    row = cur.fetchone()
    if row and row[0] is not None:
        return Decimal(str(row[0]))
    return None


def main() -> int:
    print("[MEMORY BANK: ACTIVE]")

    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("[ERROR] DATABASE_URL environment variable is not set.", file=sys.stderr)
        return 1

    # Shared filter: primitive gap candidates only (no direct LR price and no recipe output).
    primitive_gap_filter = """
        AND NOT (
            ci.lr_item_id IS NOT NULL
            AND COALESCE(ci.match_tier, '') != 'unmatched'
            AND li.unit_price_current IS NOT NULL
        )
        AND NOT EXISTS (
            SELECT 1
            FROM recipes r
            WHERE r.output_canonical_id = ci.id
        )
    """

    # Shared filter for Rules 1-6: preserve manual overrides.
    non_manual_override_filter = """
        AND ci.id NOT IN (
            SELECT canonical_id
            FROM price_overrides
            WHERE note NOT ILIKE 'computed:%'
        )
    """

    primitive_harvest_price = Decimal("1") / Decimal("64")

    try:
        with psycopg2.connect(database_url) as conn:
            with conn.cursor() as cur:
                ensure_price_overrides_table(cur)

                cur.execute(
                    """
                    SELECT display_name, unit_price_current
                    FROM lr_items
                    WHERE item_id = 'IN043'
                    ORDER BY id
                    LIMIT 1
                    """
                )
                slab_row = cur.fetchone()
                if slab_row is None:
                    print("[WARN] No LR slab row found for item_id='IN043'.", file=sys.stderr)
                    return 1

                slab_name, slab_unit_price = slab_row
                if slab_unit_price is None:
                    print("[WARN] LR slab row IN043 has NULL unit_price_current.", file=sys.stderr)
                    return 1

                slab_unit_price_dec = Decimal(str(slab_unit_price))
                rock_price = slab_unit_price_dec / Decimal("216")
                stone_price = rock_price / Decimal("10")

                # Dynamic prices derived from other items
                iron_ingot_price = get_price(cur, "ingot_iron") or Decimal("8")
                hoop_price = (iron_ingot_price * Decimal("1.4")).quantize(Decimal("0.000001"))

                cattail_price = get_price(cur, "cattailtops") or Decimal("0.015625")
                papyrus_price = get_price(cur, "papyrustops") or cattail_price
                parchment_price = (min(cattail_price, papyrus_price) * Decimal("2")).quantize(
                    Decimal("0.000001")
                )

                # Clay price: cheapest non-zero clay variant
                cur.execute(
                    """
                    SELECT MIN(COALESCE(li.unit_price_current, po.unit_price))
                    FROM canonical_items ci
                    LEFT JOIN lr_items li ON li.id = ci.lr_item_id
                    LEFT JOIN price_overrides po ON po.canonical_id = ci.id
                    WHERE ci.id ILIKE '%clay%'
                      AND ci.id NOT ILIKE '%clayforming%'
                      AND ci.id NOT ILIKE '%claystone%'
                      AND COALESCE(li.unit_price_current, po.unit_price) > 0
                    """
                )
                clay_row = cur.fetchone()
                clay_price = Decimal(str(clay_row[0])) if clay_row and clay_row[0] else Decimal("0.5")
                bowl_price = clay_price  # 1 clay per bowl

                # Log price (Logs LR item)
                log_price = get_price(cur, "log_placed_oak_ud") or Decimal("1")
                debarkedlog_price = (log_price / Decimal("4")).quantize(Decimal("0.000001"))
                copper_ingot_price = get_price(cur, "ingot_copper") or Decimal("4")
                supportbeam_price = debarkedlog_price
                bone_base_price = get_price(cur, "bone") or (Decimal("1") / Decimal("64"))

                print(
                    "[INFO] Slab source: "
                    f"display_name='{slab_name}', "
                    f"unit_price_current={slab_unit_price_dec}, "
                    f"computed_rock_price={rock_price}, "
                    f"computed_stone_price={stone_price}"
                )
                print(f"[INFO] Dynamic prices: iron_ingot={iron_ingot_price}, hoop={hoop_price}")
                print(f"[INFO] Dynamic prices: cattail={cattail_price}, parchment={parchment_price}")
                print(f"[INFO] Dynamic prices: clay={clay_price}, bowl={bowl_price}")
                print(f"[INFO] Dynamic prices: log={log_price}, debarkedlog={debarkedlog_price}")
                print(
                    f"[INFO] Dynamic prices: copper_ingot={copper_ingot_price}, "
                    f"supportbeam={supportbeam_price}, bone_base={bone_base_price}"
                )

                rules = [
                    Rule(
                        name="Rule 1 — Rock from LR slab price",
                        target_query=f"""
                            SELECT ci.id
                            FROM canonical_items ci
                            LEFT JOIN lr_items li ON li.id = ci.lr_item_id
                            WHERE ci.game_code ILIKE '%rock%'
                              AND (ci.lr_item_id IS NULL OR li.unit_price_current IS NULL)
                              {non_manual_override_filter}
                            ORDER BY ci.id
                        """,
                        unit_price=rock_price,
                        note="computed: rock = LR_slab_price / 216",
                    ),
                    Rule(
                        name="Rule 2 — Stone from rock",
                        target_query=f"""
                            SELECT ci.id
                            FROM canonical_items ci
                            LEFT JOIN lr_items li ON li.id = ci.lr_item_id
                            WHERE ci.game_code ILIKE '%stone%'
                              AND (ci.lr_item_id IS NULL OR li.unit_price_current IS NULL)
                              {non_manual_override_filter}
                            ORDER BY ci.id
                        """,
                        unit_price=stone_price,
                        note="computed: stone = rock_price / 10",
                    ),
                    Rule(
                        name="Rule 3 — Sand and soil from stone",
                        target_query=f"""
                            SELECT ci.id
                            FROM canonical_items ci
                            LEFT JOIN lr_items li ON li.id = ci.lr_item_id
                            WHERE (ci.game_code ILIKE '%sand%' OR ci.game_code ILIKE '%soil%')
                              AND (ci.lr_item_id IS NULL OR li.unit_price_current IS NULL)
                              {non_manual_override_filter}
                            ORDER BY ci.id
                        """,
                        unit_price=stone_price,
                        note="computed: sand/soil = stone_price",
                    ),
                    Rule(
                        name="Rule 4 — Flint from stone",
                        target_query=f"""
                            SELECT ci.id
                            FROM canonical_items ci
                            LEFT JOIN lr_items li ON li.id = ci.lr_item_id
                            WHERE ci.game_code ILIKE '%flint%'
                              AND (ci.lr_item_id IS NULL OR li.unit_price_current IS NULL)
                              {non_manual_override_filter}
                            ORDER BY ci.id
                        """,
                        unit_price=stone_price,
                        note="computed: flint = stone_price",
                    ),
                    Rule(
                        name="Rule 5 — Drygrass (primitive harvest)",
                        target_query=f"""
                            SELECT ci.id
                            FROM canonical_items ci
                            LEFT JOIN lr_items li ON li.id = ci.lr_item_id
                            WHERE ci.id ILIKE '%drygrass%'
                              AND (ci.lr_item_id IS NULL OR li.unit_price_current IS NULL)
                              {non_manual_override_filter}
                            ORDER BY ci.id
                        """,
                        unit_price=primitive_harvest_price,
                        note="computed: drygrass = 1/64 primitive harvest",
                    ),
                    Rule(
                        name="Rule 6 — Brineportion (primitive harvest)",
                        target_query=f"""
                            SELECT ci.id
                            FROM canonical_items ci
                            LEFT JOIN lr_items li ON li.id = ci.lr_item_id
                            WHERE ci.id ILIKE '%brineportion%'
                              AND (ci.lr_item_id IS NULL OR li.unit_price_current IS NULL)
                              {non_manual_override_filter}
                            ORDER BY ci.id
                        """,
                        unit_price=primitive_harvest_price,
                        note="computed: brineportion = 1/64 primitive harvest",
                    ),
                    Rule(
                        name="Rule 6b — Salt (= stone price, rock family)",
                        target_query="""
                            SELECT ci.id
                            FROM canonical_items ci
                            LEFT JOIN lr_items li ON li.id = ci.lr_item_id
                            WHERE ci.game_code ILIKE '%salt%'
                              AND (ci.lr_item_id IS NULL OR li.unit_price_current IS NULL)
                              AND ci.id NOT IN (
                                  SELECT canonical_id FROM price_overrides
                                  WHERE note NOT ILIKE 'computed:%'
                              )
                            ORDER BY ci.id
                        """,
                        unit_price=stone_price,
                        note="computed: salt = stone_price (rock family)",
                    ),
                    Rule(
                        name="Rule 6c — Needle (primitive, 1/64 CS)",
                        target_query="""
                            SELECT ci.id
                            FROM canonical_items ci
                            LEFT JOIN lr_items li ON li.id = ci.lr_item_id
                            WHERE ci.game_code ILIKE '%needle%'
                              AND (ci.lr_item_id IS NULL OR li.unit_price_current IS NULL)
                              AND ci.id NOT IN (
                                  SELECT canonical_id FROM price_overrides
                                  WHERE note NOT ILIKE 'computed:%'
                              )
                            ORDER BY ci.id
                        """,
                        unit_price=Decimal("1") / Decimal("64"),
                        note="computed: needle = 1/64 primitive",
                    ),
                    Rule(
                        name="Rule 6d — Iron hoop (1.4x iron ingot)",
                        target_query="""
                            SELECT ci.id FROM canonical_items ci
                            LEFT JOIN lr_items li ON li.id = ci.lr_item_id
                            WHERE ci.game_code ILIKE '%hoop%iron%'
                              AND (ci.lr_item_id IS NULL OR li.unit_price_current IS NULL)
                              AND ci.id NOT IN (SELECT canonical_id FROM price_overrides WHERE note NOT ILIKE 'computed:%')
                            ORDER BY ci.id
                        """,
                        unit_price=hoop_price,
                        note="computed: hoop_iron = 1.4 x iron_ingot_price",
                    ),
                    Rule(
                        name="Rule 6e — Parchment (2x cheapest cattail/papyrus)",
                        target_query="""
                            SELECT ci.id FROM canonical_items ci
                            LEFT JOIN lr_items li ON li.id = ci.lr_item_id
                            WHERE (ci.game_code ILIKE '%parchment%' OR ci.id ILIKE '%parchment%')
                              AND (ci.lr_item_id IS NULL OR li.unit_price_current IS NULL)
                              AND ci.id NOT IN (SELECT canonical_id FROM price_overrides WHERE note NOT ILIKE 'computed:%')
                            ORDER BY ci.id
                        """,
                        unit_price=parchment_price,
                        note="computed: parchment = 2 x min(cattail, papyrus) price",
                    ),
                    Rule(
                        name="Rule 6f — Bowl fired (1x clay)",
                        target_query="""
                            SELECT ci.id FROM canonical_items ci
                            LEFT JOIN lr_items li ON li.id = ci.lr_item_id
                            WHERE (ci.game_code ILIKE '%bowl%fired%' OR ci.game_code ILIKE '%bowl%raw%')
                              AND (ci.lr_item_id IS NULL OR li.unit_price_current IS NULL)
                              AND ci.id NOT IN (SELECT canonical_id FROM price_overrides WHERE note NOT ILIKE 'computed:%')
                            ORDER BY ci.id
                        """,
                        unit_price=bowl_price,
                        note="computed: bowl_fired = 1 x clay_price",
                    ),
                    Rule(
                        name="Rule 6g — Debarked log (1/4 log price)",
                        target_query="""
                            SELECT ci.id FROM canonical_items ci
                            LEFT JOIN lr_items li ON li.id = ci.lr_item_id
                            WHERE ci.game_code ILIKE '%debarkedlog%'
                              AND (ci.lr_item_id IS NULL OR li.unit_price_current IS NULL)
                              AND ci.id NOT IN (SELECT canonical_id FROM price_overrides WHERE note NOT ILIKE 'computed:%')
                            ORDER BY ci.id
                        """,
                        unit_price=debarkedlog_price,
                        note="computed: debarkedlog = log_price / 4",
                    ),
                    Rule(
                        name="Rule 6k — Copper anvil (= copper ingot price)",
                        target_query="""
                            SELECT ci.id FROM canonical_items ci
                            LEFT JOIN lr_items li ON li.id = ci.lr_item_id
                            WHERE ci.id ILIKE '%anvil%copper%'
                              AND (ci.lr_item_id IS NULL OR li.unit_price_current IS NULL)
                              AND ci.id NOT IN (SELECT canonical_id FROM price_overrides WHERE note NOT ILIKE 'computed:%')
                            ORDER BY ci.id
                        """,
                        unit_price=copper_ingot_price,
                        note="computed: anvil_copper = copper ingot price",
                    ),
                    Rule(
                        name="Rule 6l — Driftwood/flotsam (foraged primitive = stick price)",
                        target_query="""
                            SELECT ci.id FROM canonical_items ci
                            LEFT JOIN lr_items li ON li.id = ci.lr_item_id
                            WHERE (ci.id ILIKE '%flotsam%' OR ci.id ILIKE '%driftwood%')
                              AND (ci.lr_item_id IS NULL OR li.unit_price_current IS NULL)
                              AND ci.id NOT IN (SELECT canonical_id FROM price_overrides WHERE note NOT ILIKE 'computed:%')
                            ORDER BY ci.id
                        """,
                        unit_price=Decimal("0.03125"),
                        note="computed: driftwood = foraged primitive",
                    ),
                    Rule(
                        name="Rule 6m — Slush (zero-price world resource)",
                        target_query="""
                            SELECT ci.id FROM canonical_items ci
                            LEFT JOIN lr_items li ON li.id = ci.lr_item_id
                            WHERE ci.id ILIKE '%slush%'
                              AND (ci.lr_item_id IS NULL OR li.unit_price_current IS NULL)
                              AND ci.id NOT IN (SELECT canonical_id FROM price_overrides WHERE note NOT ILIKE 'computed:%')
                            ORDER BY ci.id
                        """,
                        unit_price=Decimal("0"),
                        note="computed: slush = zero-price world resource",
                    ),
                    Rule(
                        name="Rule 6n — Support beams (component wood cost)",
                        target_query="""
                            SELECT ci.id FROM canonical_items ci
                            LEFT JOIN lr_items li ON li.id = ci.lr_item_id
                            WHERE ci.id ILIKE 'supportbeam%'
                              AND (ci.lr_item_id IS NULL OR li.unit_price_current IS NULL)
                              AND ci.id NOT IN (SELECT canonical_id FROM price_overrides WHERE note NOT ILIKE 'computed:%')
                            ORDER BY ci.id
                        """,
                        unit_price=supportbeam_price,
                        note="computed: supportbeam = component wood cost",
                    ),
                    Rule(
                        name="Rule 6o — Primitive bones fallback",
                        target_query="""
                            SELECT ci.id FROM canonical_items ci
                            LEFT JOIN lr_items li ON li.id = ci.lr_item_id
                            WHERE ci.id IN ('bone', 'bone_tiny', 'strongbone', 'burnedbone')
                              AND (ci.lr_item_id IS NULL OR li.unit_price_current IS NULL)
                              AND ci.id NOT IN (SELECT canonical_id FROM price_overrides WHERE note NOT ILIKE 'computed:%')
                            ORDER BY ci.id
                        """,
                        unit_price=bone_base_price,
                        note="computed: primitive bones = base bone price or 1/64 CS fallback",
                    ),
                    Rule(
                        name="Rule 7 — metalnailsandstrips generic",
                        target_query=f"""
                            SELECT ci.id
                            FROM canonical_items ci
                            LEFT JOIN lr_items li ON li.id = ci.lr_item_id
                            WHERE ci.id = 'metalnailsandstrips'
                              {primitive_gap_filter}
                            ORDER BY ci.id
                        """,
                        unit_price=Decimal("2.00"),
                        note="computed: metalnailsandstrips = iron ingot baseline / 4",
                    ),
                    Rule(
                        name="Rule 8 — metalnailsandstrips_cupronickel",
                        target_query=f"""
                            SELECT ci.id
                            FROM canonical_items ci
                            LEFT JOIN lr_items li ON li.id = ci.lr_item_id
                            WHERE ci.id = 'metalnailsandstrips_cupronickel'
                              {primitive_gap_filter}
                            ORDER BY ci.id
                        """,
                        unit_price=Decimal("2.25"),
                        note="computed: metalnailsandstrips_cupronickel = cupronickel ingot / 4",
                    ),
                ]

                print("\nPrimitive computed override run summary")
                print("-" * 72)
                for rule in rules:
                    inserted, updated, skipped_manual, targets = apply_rule(cur, rule)
                    print(
                        f"{rule.name}: targets={targets}, inserted={inserted}, "
                        f"updated={updated}, skipped_manual={skipped_manual}"
                    )

            conn.commit()

        return 0
    except Exception as exc:  # pragma: no cover - operational script
        print(f"[ERROR] compute_primitive_prices failed: {exc}", file=sys.stderr)
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
