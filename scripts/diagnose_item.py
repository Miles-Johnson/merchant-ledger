#!/usr/bin/env python3
"""Diagnose pricing and recipe resolution for a canonical item tree.

Usage:
    python scripts/diagnose_item.py <canonical_id>
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Dict, List, Optional, Set, Tuple

import psycopg2
from dotenv import load_dotenv


load_dotenv()

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")


@dataclass(frozen=True)
class ItemRow:
    canonical_id: str
    display_name: str
    match_tier: Optional[str]
    lr_price: Optional[Decimal]
    override_price: Optional[Decimal]


@dataclass(frozen=True)
class RecipeIngredient:
    input_canonical_id: str
    qty: Decimal


@dataclass(frozen=True)
class RecipeRow:
    recipe_id: int
    output_qty: Decimal
    ingredients: List[RecipeIngredient]


def _to_decimal(value) -> Optional[Decimal]:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _fmt_price(value: Optional[Decimal]) -> str:
    if value is None:
        return "none"
    return f"{value.normalize()}"


def _fmt_qty(value: Decimal) -> str:
    return f"{value.normalize()}"


def _fetch_item(conn, canonical_id: str) -> Optional[ItemRow]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT ci.id, ci.display_name, ci.match_tier, lr.unit_price_current, po.unit_price
            FROM canonical_items ci
            LEFT JOIN lr_items lr
              ON ci.lr_item_id = lr.id
            LEFT JOIN price_overrides po
              ON ci.id = po.canonical_id
            WHERE ci.id = %s
            LIMIT 1
            """,
            (canonical_id,),
        )
        row = cur.fetchone()
    if not row:
        return None
    return ItemRow(
        canonical_id=row[0],
        display_name=row[1] or row[0],
        match_tier=row[2],
        lr_price=_to_decimal(row[3]),
        override_price=_to_decimal(row[4]),
    )


def _fetch_recipe(conn, canonical_id: str) -> Optional[RecipeRow]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, output_qty
            FROM recipes
            WHERE output_canonical_id = %s
            ORDER BY id
            LIMIT 1
            """,
            (canonical_id,),
        )
        recipe_row = cur.fetchone()

        if not recipe_row:
            return None

        recipe_id = recipe_row[0]
        output_qty = _to_decimal(recipe_row[1]) or Decimal("1")

        cur.execute(
            """
            SELECT input_canonical_id, qty
            FROM recipe_ingredients
            WHERE recipe_id = %s
            ORDER BY id
            """,
            (recipe_id,),
        )
        ingredients = []
        for input_canonical_id, qty in cur.fetchall():
            if not input_canonical_id:
                continue
            ingredients.append(
                RecipeIngredient(
                    input_canonical_id=input_canonical_id,
                    qty=_to_decimal(qty) or Decimal("0"),
                )
            )

    return RecipeRow(recipe_id=recipe_id, output_qty=output_qty, ingredients=ingredients)


def diagnose(conn, canonical_id: str) -> int:
    blockers: Set[str] = set()

    def walk(node_id: str, depth: int, visited: Set[str]) -> Tuple[Optional[Decimal], bool]:
        indent = "  " * depth
        print(f"{indent}canonical_id: {node_id}")

        if node_id in visited:
            print(f"{indent}  → CYCLE DETECTED")
            return None, False

        item = _fetch_item(conn, node_id)
        if item is None:
            print(f"{indent}  display_name: <missing>")
            print(f"{indent}  match_tier: <missing>")
            print(f"{indent}  lr_price: none")
            print(f"{indent}  override: none")
            print(f"{indent}  has_recipe: no")
            print(f"{indent}  → UNPRICED BASE")
            blockers.add(node_id)
            return None, False

        print(f"{indent}  display_name: {item.display_name}")
        print(f"{indent}  match_tier: {item.match_tier}")
        print(f"{indent}  lr_price: {_fmt_price(item.lr_price)}")
        print(f"{indent}  override: {_fmt_price(item.override_price)}")

        recipe = _fetch_recipe(conn, node_id)
        has_recipe = recipe is not None
        print(f"{indent}  has_recipe: {'yes' if has_recipe else 'no'}")

        if has_recipe and recipe is not None:
            print(f"{indent}  ingredients (x{_fmt_qty(recipe.output_qty)} output):")
            all_ok = True
            total_cost = Decimal("0")
            next_visited = set(visited)
            next_visited.add(node_id)

            for ing in recipe.ingredients:
                print(f"{indent}    - {ing.input_canonical_id} x{_fmt_qty(ing.qty)}")
                ing_cost, ing_ok = walk(ing.input_canonical_id, depth + 3, next_visited)
                if not ing_ok or ing_cost is None:
                    all_ok = False
                    continue
                total_cost += ing_cost * ing.qty

            if not all_ok:
                return None, False

            if recipe.output_qty == 0:
                return None, False

            return total_cost / recipe.output_qty, True

        if item.override_price is not None:
            print(f"{indent}  → BASE MATERIAL (override: {item.override_price.normalize()})")
            return item.override_price, True

        if item.lr_price is not None:
            print(f"{indent}  → BASE MATERIAL (lr_price: {item.lr_price.normalize()})")
            return item.lr_price, True

        print(f"{indent}  → UNPRICED BASE")
        blockers.add(node_id)
        return None, False

    estimated_cost, ok = walk(canonical_id, 0, set())

    print("=== SUMMARY ===")
    print(f"Fully resolvable: {'yes' if ok else 'no'}")
    print(f"Unpriced blockers: {sorted(blockers)}")
    if ok and estimated_cost is not None:
        print(f"Estimated unit cost: {estimated_cost.normalize()} CS")
    else:
        print("Estimated unit cost: incomplete")

    return 0


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python scripts/diagnose_item.py <canonical_id>")
        return 1

    canonical_id = sys.argv[1]
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("[ERROR] DATABASE_URL environment variable is not set.")
        return 1

    try:
        with psycopg2.connect(database_url) as conn:
            item = _fetch_item(conn, canonical_id)
            if item is None:
                print(f"[ERROR] canonical_items.id not found: {canonical_id}")
                return 1
            return diagnose(conn, canonical_id)
    except Exception as exc:
        print(f"[ERROR] diagnose_item failed: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
