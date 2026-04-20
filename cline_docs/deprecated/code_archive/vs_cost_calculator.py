#!/usr/bin/env python3
# DEPRECATED (Gen 2 legacy): Retained for reference/back-compat only; Gen 3 runtime is authoritative.
"""
Phase 2: Item mapping + recursive cost calculator.

Reads:
  - lr_items (imported from Lost Realm sheets)
  - vs_recipe_outputs / vs_recipe_ingredients (normalized recipe tables)

Provides:
  - optional map bootstrap table: item_name_map
  - order parsing and recursive calculated-cost walk
  - side-by-side listed price and calculated price
"""

from __future__ import annotations

import argparse
import difflib
import getpass
import json
import os
import re
from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

try:
    import psycopg2
except ImportError as exc:
    raise SystemExit("Missing dependency 'psycopg2'. Install with: pip install psycopg2-binary") from exc


SETTLEMENT_TO_COLUMN = {
    "current_price": "current_price",
    "industrial_town": "industrial_town",
    "industrial_city": "industrial_city",
    "market_town": "market_town",
    "market_city": "market_city",
    "religious_town": "religious_town",
    "temple_city": "temple_city",
}

LR_PRICE_COLUMNS = set(SETTLEMENT_TO_COLUMN.values())

LR_CATEGORY_NAME_COLUMN_CANDIDATES = {
    "agricultural_goods": ["item_name", "item", "name", "good", "resource", "product"],
    "industrial_goods": ["item_name", "item", "name", "good", "resource", "product"],
    "artisanal_goods": ["item_name", "item", "name", "good", "resource", "product"],
    "settlement_specialization": ["item_name", "item", "name", "specialization", "settlement"],
}

LR_DEFAULT_NAME_COLUMN_CANDIDATES = ["item_name", "item", "name", "good", "resource", "product"]


@dataclass
class CostNode:
    code: str
    quantity: float
    listed_unit: Optional[float]
    calculated_unit: Optional[float]
    selected_recipe_output_id: Optional[int]
    missing_reasons: List[str]
    ingredients: List[dict]


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Calculate listed + recursive crafting costs")
    p.add_argument("--host", default="localhost")
    p.add_argument("--port", type=int, default=5432)
    p.add_argument("--database", default="postgres")
    p.add_argument("--user", default="postgres")
    p.add_argument("--password", default=None)
    p.add_argument("--settlement", default="current_price", choices=sorted(SETTLEMENT_TO_COLUMN.keys()))
    p.add_argument("--order", required=True, help='Example: "4 iron plates, 1 bismuth lantern"')
    p.add_argument("--bootstrap-map", action="store_true", help="Generate/update heuristic item_name_map")
    return p.parse_args()


def resolve_password(cli_password: Optional[str]) -> str:
    if cli_password:
        return cli_password
    env_pw = os.getenv("PGPASSWORD")
    if env_pw:
        return env_pw
    return getpass.getpass("PostgreSQL password: ")


def parse_order(order: str) -> List[Tuple[float, str]]:
    parts = [p.strip() for p in order.split(",") if p.strip()]
    out: List[Tuple[float, str]] = []
    for part in parts:
        m = re.match(r"^\s*(\d+(?:\.\d+)?)\s+(.+?)\s*$", part)
        if m:
            out.append((float(m.group(1)), m.group(2).strip().lower()))
        else:
            out.append((1.0, part.lower()))
    return out


def ensure_map_table(cur) -> None:
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS item_name_map (
            game_code TEXT PRIMARY KEY,
            lr_name TEXT,
            confidence NUMERIC,
            source TEXT,
            notes TEXT,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        """
    )


def normalize_tail(code: str) -> str:
    c = code.split(":", 1)[-1].lower()
    c = c.replace("{", "").replace("}", "")
    return c


def humanize_tail(tail: str) -> str:
    s = tail.replace("_", " ").replace("-", " ").strip().lower()
    s = re.sub(r"\b(up|down|north|south|east|west|ud)\b", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def code_aliases(code: str) -> List[str]:
    tail = normalize_tail(code)
    aliases = {humanize_tail(tail)}

    m = re.match(r"^ingot-([a-z0-9]+)$", tail)
    if m:
        metal = m.group(1)
        aliases.add(metal)
        aliases.add(f"{metal} ingot")
        aliases.add(f"{metal} ingots")

    m = re.match(r"^metalplate-([a-z0-9]+)$", tail)
    if m:
        metal = m.group(1)
        aliases.add(f"{metal} plate")
        aliases.add(f"{metal} plates")
        aliases.add(f"metal plate {metal}")

    if "lantern" in tail:
        pieces = tail.split("-")
        if len(pieces) >= 2 and pieces[0] == "lantern":
            mat = pieces[1]
            aliases.add(f"{mat} lantern")
            aliases.add(f"{mat} lanterns")
        aliases.add("lantern")
        aliases.add("lanterns")

    return [a for a in aliases if a]


def _parse_numeric(value: object) -> Optional[float]:
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    s = s.replace(",", "")
    try:
        return float(s)
    except Exception:
        return None


def _is_plausible_item_name(name: str) -> bool:
    s = str(name or "").strip()
    if not s:
        return False

    lo = s.lower()
    blocked_exact = {
        "item id",
        "current price",
        "agricultural goods",
        "industrial goods",
        "artisanal goods",
        "settlement specialization",
        "metal ingots",
    }
    if lo in blocked_exact:
        return False

    if len(s) > 100:
        return False

    if re.match(r"^[a-z]{2}\d+$", lo):
        return False

    if not re.search(r"[a-z]", lo):
        return False

    return True


def load_lr_price_map(cur, settlement_column: str) -> Dict[str, float]:
    cur.execute(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_name = 'lr_items'
        ORDER BY ordinal_position
        """
    )
    cols = [r[0] for r in cur.fetchall()]

    if settlement_column not in cols:
        settlement_column = "current_price" if "current_price" in cols else settlement_column

    if settlement_column not in cols:
        return {}

    category_name_cols = get_lr_name_columns_by_category(cur)

    rows = []
    for category, name_cols in category_name_cols.items():
        for name_col in name_cols:
            cur.execute(
                f'SELECT "{settlement_column}", "{name_col}" FROM lr_items WHERE category = %s',
                (category,),
            )
            rows.extend(cur.fetchall())

    out: Dict[str, float] = {}
    for row in rows:
        price = _parse_numeric(row[0])
        if price is None:
            continue

        name = row[1] if len(row) > 1 else None
        if not name:
            continue
        s = str(name).strip()
        if not _is_plausible_item_name(s):
            continue
        lo = s.lower()
        if lo not in out:
            out[lo] = price

    return out


def get_lr_name_columns_by_category(cur) -> Dict[str, List[str]]:
    cur.execute(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_name = 'lr_items'
        ORDER BY ordinal_position
        """
    )
    cols = [r[0] for r in cur.fetchall()]

    blocked = {"id", "category", "inserted_at"}.union(LR_PRICE_COLUMNS)
    usable_cols = [c for c in cols if c not in blocked]

    cur.execute("SELECT DISTINCT category FROM lr_items WHERE category IS NOT NULL")
    categories = [str(r[0]).strip().lower() for r in cur.fetchall() if r[0]]

    out: Dict[str, List[str]] = {}
    for category in categories:
        preferred = LR_CATEGORY_NAME_COLUMN_CANDIDATES.get(category, []) + LR_DEFAULT_NAME_COLUMN_CANDIDATES

        chosen: List[str] = []
        for col in preferred:
            if col in usable_cols and col not in chosen:
                chosen.append(col)

        if not chosen and usable_cols:
            # Deterministic fallback: pick the highest-filled text column for this category.
            best_col = None
            best_count = -1
            for col in usable_cols:
                cur.execute(
                    f'SELECT COUNT(*) FROM lr_items WHERE category = %s AND "{col}" IS NOT NULL AND BTRIM("{col}") <> %s',
                    (category, ""),
                )
                n = int(cur.fetchone()[0])
                if n > best_count:
                    best_count = n
                    best_col = col
            if best_col:
                chosen = [best_col]

        if chosen:
            out[category] = chosen

    return out


def bootstrap_item_name_map(cur, lr_map: Dict[str, float]) -> int:
    cur.execute("SELECT DISTINCT output_code FROM vs_recipe_outputs")
    codes = [r[0] for r in cur.fetchall()]

    inserted = 0
    for code in codes:
        aliases = code_aliases(code)
        best_name = None
        best_score = 0.0
        for a in aliases:
            if a in lr_map:
                best_name = a
                best_score = 1.0
                break
            candidates = difflib.get_close_matches(a, list(lr_map.keys()), n=1, cutoff=0.9)
            if candidates:
                cand = candidates[0]
                score = difflib.SequenceMatcher(None, a, cand).ratio()
                if score > best_score:
                    best_name = cand
                    best_score = score

        cur.execute(
            """
            INSERT INTO item_name_map (game_code, lr_name, confidence, source, notes)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (game_code) DO UPDATE SET
                lr_name = EXCLUDED.lr_name,
                confidence = EXCLUDED.confidence,
                source = EXCLUDED.source,
                notes = EXCLUDED.notes,
                updated_at = NOW()
            """,
            (code, best_name, best_score if best_name else 0.0, "heuristic", None),
        )
        inserted += 1

    return inserted


def load_game_to_lr_map(cur) -> Dict[str, Optional[str]]:
    cur.execute("SELECT game_code, lr_name FROM item_name_map")
    return {r[0]: r[1] for r in cur.fetchall()}


def get_listed_price(code: str, game_to_lr: Dict[str, Optional[str]], lr_prices: Dict[str, float]) -> Optional[float]:
    mapped = game_to_lr.get(code)
    if mapped:
        p = lr_prices.get(mapped.lower())
        if p is not None:
            return p

    for a in code_aliases(code):
        if a in lr_prices:
            return lr_prices[a]

    tail = normalize_tail(code)
    if "-" in tail:
        metal = tail.split("-")[-1]
        if metal in lr_prices:
            return lr_prices[metal]
    return None


def resolve_order_item(cur, label: str, lr_prices: Dict[str, float]) -> Optional[str]:
    label = str(label or "").strip().lower()
    if not label:
        return None

    m = re.match(r"^([a-z0-9]+)\s+plates?$", label)
    if m:
        return f"item:metalplate-{m.group(1)}"

    cur.execute("SELECT DISTINCT output_code FROM vs_recipe_outputs")
    codes = [r[0] for r in cur.fetchall()]

    alias_to_code: Dict[str, str] = {}
    for c in codes:
        for a in code_aliases(c):
            alias_to_code.setdefault(a, c)

    if label in alias_to_code:
        return alias_to_code[label]

    candidates = difflib.get_close_matches(label, list(alias_to_code.keys()), n=1, cutoff=0.85)
    if candidates:
        return alias_to_code[candidates[0]]

    if label in lr_prices:
        return f"lr:{label}"

    lr_candidates = difflib.get_close_matches(label, list(lr_prices.keys()), n=1, cutoff=0.85)
    if lr_candidates:
        return f"lr:{lr_candidates[0]}"

    return None


def _template_match_ctx(template_code: str, concrete_code: str) -> Optional[Dict[str, str]]:
    t = re.escape(template_code)
    t = re.sub(r"\\\{([a-zA-Z0-9_]+)\\\}", r"(?P<\1>[a-z0-9]+)", t)
    m = re.match(rf"^{t}$", concrete_code)
    if not m:
        return None
    return {k: v for k, v in m.groupdict().items() if v is not None}


def _find_recipe_rows(cur, code: str) -> Tuple[List[tuple], Dict[str, str]]:
    cur.execute(
        """
        SELECT id, output_qty, output_code
        FROM vs_recipe_outputs
        WHERE output_code = %s
        ORDER BY id ASC
        """,
        (code,),
    )
    rows = cur.fetchall()
    if rows:
        return rows, {}

    cur.execute(
        """
        SELECT id, output_qty, output_code
        FROM vs_recipe_outputs
        WHERE output_code LIKE %s
        ORDER BY id ASC
        """,
        ("%{%}%",),
    )
    for rid, out_qty, templ in cur.fetchall():
        ctx = _template_match_ctx(str(templ), code)
        if ctx is not None:
            return [(rid, out_qty, templ)], ctx

    return [], {}


def _matches_variant_ctx(code: str, ctx: Dict[str, str]) -> bool:
    if not ctx:
        return True
    tail_tokens = re.split(r"[^a-z0-9]+", normalize_tail(code))
    tail_set = {t for t in tail_tokens if t}
    for v in ctx.values():
        if v.lower() in tail_set:
            return True
    return False


def calc_unit_cost(
    cur,
    code: str,
    game_to_lr: Dict[str, Optional[str]],
    lr_prices: Dict[str, float],
    memo: Dict[str, CostNode],
    stack: List[str],
) -> CostNode:
    if code in memo:
        return memo[code]

    if code.startswith("lr:"):
        lr_name = code[3:].strip().lower()
        listed = lr_prices.get(lr_name)
        if listed is None:
            node = CostNode(code, 1.0, None, None, None, [f"LR item not priced: {lr_name}"], [])
            memo[code] = node
            return node
        node = CostNode(code, 1.0, listed, listed, None, [], [])
        memo[code] = node
        return node

    listed = get_listed_price(code, game_to_lr, lr_prices)

    # Priority rule: if an LR listed price exists, treat item as a leaf node.
    # Do not decompose via recipes, as LR market pricing is authoritative.
    if listed is not None:
        node = CostNode(code, 1.0, listed, listed, None, [], [])
        memo[code] = node
        return node

    if code in stack:
        node = CostNode(code, 1.0, listed, None, None, ["cycle detected"], [])
        memo[code] = node
        return node

    recipe_rows, variant_ctx = _find_recipe_rows(cur, code)

    best_calc = None
    best_recipe_id = None
    best_breakdown = []
    missing_reasons: List[str] = []

    for rid, output_qty, _resolved_output in recipe_rows:
        cur.execute(
            """
            SELECT ingredient_group, option_index, ingredient_code, quantity, is_tool
            FROM vs_recipe_ingredients
            WHERE recipe_output_id = %s
            ORDER BY ingredient_group, option_index
            """,
            (rid,),
        )
        ing_rows = cur.fetchall()
        if not ing_rows:
            continue

        groups: Dict[int, List[tuple]] = defaultdict(list)
        for g, opt, ic, qty, is_tool in ing_rows:
            groups[g].append((opt, ic, float(qty), bool(is_tool)))

        total = 0.0
        breakdown = []
        unresolved = False

        for g in sorted(groups.keys()):
            options = groups[g]
            if variant_ctx:
                preferred = [opt for opt in options if _matches_variant_ctx(str(opt[1]), variant_ctx)]
                if preferred:
                    options = preferred

            opt_costs = []
            opt_nodes = []
            for _, ic, qty, is_tool in options:
                if is_tool:
                    opt_costs.append(0.0)
                    opt_nodes.append({"code": ic, "qty": qty, "unit": 0.0, "subtotal": 0.0, "tool": True})
                    continue

                child = calc_unit_cost(cur, ic, game_to_lr, lr_prices, memo, stack + [code])
                unit = child.calculated_unit if child.calculated_unit is not None else child.listed_unit
                if unit is None:
                    continue
                subtotal = unit * qty
                opt_costs.append(subtotal)
                opt_nodes.append({"code": ic, "qty": qty, "unit": unit, "subtotal": subtotal, "tool": False})

            if not opt_costs:
                unresolved = True
                missing_reasons.append(f"no priced option in ingredient group {g}")
                continue

            min_i = min(range(len(opt_costs)), key=lambda i: opt_costs[i])
            total += opt_costs[min_i]
            breakdown.append(opt_nodes[min_i])

        if unresolved:
            continue

        out_qty = float(output_qty) if output_qty else 1.0
        calc_unit = total / out_qty
        if best_calc is None or calc_unit < best_calc:
            best_calc = calc_unit
            best_recipe_id = rid
            best_breakdown = breakdown

    node = CostNode(
        code=code,
        quantity=1.0,
        listed_unit=listed,
        calculated_unit=best_calc,
        selected_recipe_output_id=best_recipe_id,
        missing_reasons=missing_reasons,
        ingredients=best_breakdown,
    )
    memo[code] = node
    return node


def main() -> None:
    args = parse_args()
    password = resolve_password(args.password)
    settlement_col = SETTLEMENT_TO_COLUMN[args.settlement]

    conn = psycopg2.connect(
        host=args.host,
        port=args.port,
        dbname=args.database,
        user=args.user,
        password=password,
    )
    try:
        with conn, conn.cursor() as cur:
            ensure_map_table(cur)
            lr_prices = load_lr_price_map(cur, settlement_col)

            if args.bootstrap_map:
                n = bootstrap_item_name_map(cur, lr_prices)
                print(f"Bootstrapped item_name_map rows: {n}")

            game_to_lr = load_game_to_lr_map(cur)
            order = parse_order(args.order)

            memo: Dict[str, CostNode] = {}
            order_results = []
            listed_total = 0.0
            calc_total = 0.0

            for qty, label in order:
                code = resolve_order_item(cur, label, lr_prices)
                if not code:
                    order_results.append({"input": label, "qty": qty, "error": "No recipe/output match found"})
                    continue

                node = calc_unit_cost(cur, code, game_to_lr, lr_prices, memo, [])
                item_listed = node.listed_unit * qty if node.listed_unit is not None else None
                item_calc = node.calculated_unit * qty if node.calculated_unit is not None else None
                if item_listed is not None:
                    listed_total += item_listed
                if item_calc is not None:
                    calc_total += item_calc

                order_results.append(
                    {
                        "input": label,
                        "resolved_code": code,
                        "qty": qty,
                        "unit_listed": node.listed_unit,
                        "unit_calculated": node.calculated_unit,
                        "line_listed": item_listed,
                        "line_calculated": item_calc,
                        "selected_recipe_output_id": node.selected_recipe_output_id,
                        "ingredients": node.ingredients,
                        "missing_reasons": node.missing_reasons,
                    }
                )

            payload = {
                "settlement": args.settlement,
                "order": args.order,
                "line_items": order_results,
                "totals": {
                    "listed_total": listed_total,
                    "calculated_total": calc_total,
                },
            }
            print(json.dumps(payload, indent=2))
    finally:
        conn.close()


if __name__ == "__main__":
    main()
