#!/usr/bin/env python3
# DEPRECATED (Gen 2 legacy): This Flask/Jinja entrypoint is retained for reference only.
# Active runtime is Gen 3: api/app.py + scripts/resolver.py + React frontend + canonical schema.
from __future__ import annotations

import os
import sys
from typing import Dict, List, Optional
from dotenv import load_dotenv

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import psycopg2
from psycopg2 import OperationalError
from flask import Flask, jsonify, render_template, request

from vs_cost_calculator import (
    SETTLEMENT_TO_COLUMN,
    calc_unit_cost,
    ensure_map_table,
    get_lr_name_columns_by_category,
    load_game_to_lr_map,
    load_lr_price_map,
    parse_order,
    resolve_order_item,
)
from scripts.resolver import parse_order_input, process_order


load_dotenv()


app = Flask(__name__)


LEGACY_TO_RESOLVER_SETTLEMENT = {
    "current_price": "current",
    "industrial_town": "industrial_town",
    "industrial_city": "industrial_city",
    "market_town": "market_town",
    "market_city": "market_city",
    "religious_town": "religious_town",
    "temple_city": "temple_city",
}


def db_config() -> dict:
    return {
        "host": os.getenv("PGHOST", "localhost"),
        "port": int(os.getenv("PGPORT", "5432")),
        "dbname": os.getenv("PGDATABASE", "postgres"),
        "user": os.getenv("PGUSER", "postgres"),
        "password": os.getenv("PGPASSWORD", ""),
    }


def get_conn():
    cfg = db_config()
    return psycopg2.connect(**cfg)


def _db_config_error_hint() -> str:
    return (
        "Database connection failed. Ensure PostgreSQL is running and credentials are set. "
        "For Git Bash use: export PGPASSWORD='your_password' (not 'set PGPASSWORD=...')."
    )


def startup_db_check_or_exit() -> None:
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                cur.fetchone()
    except OperationalError as exc:
        print(f"[startup] {_db_config_error_hint()}")
        print(f"[startup] psycopg2 error: {exc}")
        raise SystemExit(1) from exc


def calculate_order(order: str, settlement: str) -> dict:
    settlement_col = SETTLEMENT_TO_COLUMN.get(settlement, "current_price")

    with get_conn() as conn:
        with conn.cursor() as cur:
            ensure_map_table(cur)
            lr_prices = load_lr_price_map(cur, settlement_col)
            game_to_lr = load_game_to_lr_map(cur)
            parsed = parse_order(order)

            memo = {}
            line_items = []
            listed_total = 0.0
            calculated_total = 0.0

            for qty, label in parsed:
                code = resolve_order_item(cur, label, lr_prices)
                if not code:
                    line_items.append({"input": label, "qty": qty, "error": "No recipe/output match found"})
                    continue

                node = calc_unit_cost(cur, code, game_to_lr, lr_prices, memo, [])
                line_listed = node.listed_unit * qty if node.listed_unit is not None else None
                line_calc = node.calculated_unit * qty if node.calculated_unit is not None else None

                if line_listed is not None:
                    listed_total += line_listed
                if line_calc is not None:
                    calculated_total += line_calc

                line_items.append(
                    {
                        "input": label,
                        "resolved_code": code,
                        "qty": qty,
                        "unit_listed": node.listed_unit,
                        "unit_calculated": node.calculated_unit,
                        "line_listed": line_listed,
                        "line_calculated": line_calc,
                        "selected_recipe_output_id": node.selected_recipe_output_id,
                        "ingredients": node.ingredients,
                        "missing_reasons": node.missing_reasons,
                    }
                )

            return {
                "settlement": settlement,
                "order": order,
                "line_items": line_items,
                "totals": {
                    "listed_total": listed_total,
                    "calculated_total": calculated_total,
                },
            }


def _search_lr_names(cur, q: str, limit: int = 20) -> List[str]:
    category_name_cols = get_lr_name_columns_by_category(cur)

    found: List[str] = []
    for category, cols in category_name_cols.items():
        for col in cols:
            cur.execute(
                f'SELECT DISTINCT "{col}" FROM lr_items WHERE category = %s AND "{col}" ILIKE %s LIMIT %s',
                (category, f"%{q}%", limit),
            )
            found.extend([str(r[0]).strip().lower() for r in cur.fetchall() if r[0]])
            if len(found) >= limit:
                break
        if len(found) >= limit:
            break

    deduped = []
    seen = set()
    for x in found:
        if x and x not in seen:
            seen.add(x)
            deduped.append(x)
    return deduped[:limit]


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/api/settlements")
def settlements():
    return jsonify({"settlements": list(SETTLEMENT_TO_COLUMN.keys())})


@app.get("/api/search")
def search():
    q = (request.args.get("q") or "").strip().lower()
    if len(q) < 2:
        return jsonify({"results": []})

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT DISTINCT output_code
                FROM vs_recipe_outputs
                WHERE output_code ILIKE %s
                ORDER BY output_code ASC
                LIMIT 20
                """,
                (f"%{q}%",),
            )
            recipe_hits = [r[0] for r in cur.fetchall()]
            lr_hits = _search_lr_names(cur, q, limit=20)

    merged = []
    seen = set()
    for x in lr_hits + recipe_hits:
        s = str(x).strip().lower()
        if not s or s in seen:
            continue
        seen.add(s)
        merged.append(s)

    return jsonify({"results": merged[:20]})


@app.post("/api/calculate")
def api_calculate():
    data = request.get_json(silent=True) or {}
    order = (data.get("order") or "").strip()
    settlement = (data.get("settlement") or "current_price").strip()

    if not order:
        return jsonify({"error": "Order is required"}), 400
    if settlement not in SETTLEMENT_TO_COLUMN:
        return jsonify({"error": "Invalid settlement mode"}), 400

    try:
        database_url = os.getenv("DATABASE_URL")

        # Prefer canonical resolver path when DATABASE_URL is available.
        # This includes LR quality-tier prices (common/uncommon/rare/epic/legendary).
        if database_url:
            resolver_settlement = LEGACY_TO_RESOLVER_SETTLEMENT.get(settlement, "current")

            with psycopg2.connect(database_url) as conn:
                resolver_items = parse_order_input(order)
                resolver_payload = process_order(resolver_items, resolver_settlement, conn)

            # Back-compat shape expected by the legacy webapp/static/app.js UI.
            line_items = []
            for item in resolver_payload.get("items", []):
                unit_cost = item.get("unit_cost")
                total_cost = item.get("total_cost")
                line_items.append(
                    {
                        "input": item.get("display_name") or item.get("canonical_id"),
                        "resolved_code": item.get("canonical_id"),
                        "qty": item.get("quantity"),
                        "unit_listed": unit_cost,
                        "unit_calculated": unit_cost,
                        "line_listed": total_cost,
                        "line_calculated": total_cost,
                        "selected_recipe_output_id": None,
                        "ingredients": item.get("ingredients"),
                        "missing_reasons": [],
                        "quality_prices": item.get("quality_prices"),
                        "source": item.get("source"),
                    }
                )

            payload = {
                "settlement": settlement,
                "order": order,
                "line_items": line_items,
                "totals": {
                    "listed_total": resolver_payload.get("totals", {}).get("total_combined", 0.0),
                    "calculated_total": resolver_payload.get("totals", {}).get("total_combined", 0.0),
                },
            }
            return jsonify(payload)

        payload = calculate_order(order, settlement)
        return jsonify(payload)
    except OperationalError as exc:
        return jsonify({"error": _db_config_error_hint(), "details": str(exc)}), 503
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


if __name__ == "__main__":
    startup_db_check_or_exit()
    app.run(host="127.0.0.1", port=8000, debug=True)
