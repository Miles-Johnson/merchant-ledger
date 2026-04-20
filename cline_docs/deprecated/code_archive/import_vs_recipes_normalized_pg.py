#!/usr/bin/env python3
# DEPRECATED (Gen 2 legacy): Normalized vs_recipe_* importer retained for legacy reference only.
"""
Import Vintage Story recipes (base game + unpacked mods) into normalized PostgreSQL tables
with ingredient quantities preserved.

Tables created:
  - vs_recipe_outputs
  - vs_recipe_ingredients

This importer expands placeholder outputs when possible, e.g.
  item:metalplate-{metal} -> item:metalplate-iron, ...
using ingredient definitions that declare allowedVariants + name.
"""

from __future__ import annotations

import argparse
import getpass
import itertools
import os
import re
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import json5

try:
    import psycopg2
    from psycopg2.extras import Json, execute_values
except ImportError as exc:
    raise SystemExit("Missing dependency 'psycopg2'. Install with: pip install psycopg2-binary") from exc


BASE_GAME_DIR = r"C:\Games\Vintagestory"
UNPACK_DIR = r"C:\Users\Kjol\AppData\Roaming\VintagestoryData\Cache\unpack"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Import normalized VS recipes into PostgreSQL")
    p.add_argument("--host", default="localhost")
    p.add_argument("--port", type=int, default=5432)
    p.add_argument("--database", default="postgres")
    p.add_argument("--user", default="postgres")
    p.add_argument("--password", default=None)
    p.add_argument("--base-game-dir", default=BASE_GAME_DIR)
    p.add_argument("--unpack-dir", default=UNPACK_DIR)
    p.add_argument("--truncate", action="store_true", help="TRUNCATE destination tables before import")
    p.add_argument("--batch-size", type=int, default=1000)
    return p.parse_args()


def resolve_password(cli_password: Optional[str]) -> str:
    if cli_password:
        return cli_password
    env_pw = os.getenv("PGPASSWORD")
    if env_pw:
        return env_pw
    return getpass.getpass("PostgreSQL password: ")


def parse_recipe_file(path: str) -> List[dict]:
    with open(path, "r", encoding="utf-8-sig") as f:
        data = json5.load(f)
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]
    if isinstance(data, dict):
        return [data]
    return []


def collect_files_from_base(base_game_dir: str) -> List[Tuple[str, str]]:
    out: List[Tuple[str, str]] = []
    for rel in [r"assets\survival\recipes", r"assets\game\recipes"]:
        root = os.path.join(base_game_dir, rel)
        if not os.path.isdir(root):
            continue
        for dirpath, _, filenames in os.walk(root):
            if "recipes" not in dirpath.lower():
                continue
            for fn in filenames:
                if fn.lower().endswith(".json"):
                    out.append(("Base Game", os.path.join(dirpath, fn)))
    return out


def collect_files_from_mods(unpack_dir: str) -> List[Tuple[str, str]]:
    out: List[Tuple[str, str]] = []
    if not os.path.isdir(unpack_dir):
        return out
    for mod_folder in os.listdir(unpack_dir):
        mod_path = os.path.join(unpack_dir, mod_folder)
        if not os.path.isdir(mod_path):
            continue
        for dirpath, _, filenames in os.walk(mod_path):
            lower = dirpath.lower().replace("/", "\\")
            if "\\recipes" not in lower:
                continue
            for fn in filenames:
                if fn.lower().endswith(".json"):
                    out.append((mod_folder, os.path.join(dirpath, fn)))
    return out


def infer_recipe_type(path: str, recipe: dict) -> str:
    parts = [p.lower() for p in path.replace("/", "\\").split("\\")]
    if "recipes" in parts:
        i = parts.index("recipes")
        if i + 1 < len(parts):
            nxt = parts[i + 1]
            if not nxt.endswith(".json"):
                return nxt
    if "ingredientPattern" in recipe:
        return "grid"
    if "cooksInto" in recipe:
        return "cooking"
    if "pattern" in recipe and "ingredient" in recipe:
        return "smithing"
    return "unknown"


def read_qty(value: object, default: float = 1.0) -> float:
    if not isinstance(value, dict):
        return default
    for k in ("quantity", "stacksize", "litres", "amount", "minQuantity"):
        if k in value:
            try:
                return float(value.get(k))
            except Exception:
                return default
    return default


def code_from_stack(value: object) -> str:
    if isinstance(value, str):
        return value
    if not isinstance(value, dict):
        return ""
    code = value.get("code") or value.get("name") or ""
    stack_type = value.get("type")
    if stack_type and code and ":" not in str(code):
        return f"{stack_type}:{code}"
    return str(code)


_PH_RE = re.compile(r"\{([^}]+)\}")


def placeholder_names(text: str) -> List[str]:
    return _PH_RE.findall(text or "")


def apply_context(text: str, ctx: Dict[str, str]) -> str:
    out = text
    for k, v in ctx.items():
        out = out.replace("{" + k + "}", v)
    return out


def expand_output_contexts(recipe: dict, output_code: str) -> List[Dict[str, str]]:
    names = set(placeholder_names(output_code))
    if not names:
        return [{}]

    ingredients = recipe.get("ingredients")
    if not isinstance(ingredients, dict):
        return [{}]

    options: Dict[str, List[str]] = {}
    for stack in ingredients.values():
        if not isinstance(stack, dict):
            continue
        var_name = stack.get("name")
        allowed = stack.get("allowedVariants")
        if var_name in names and isinstance(allowed, list) and allowed:
            options[var_name] = [str(x) for x in allowed]

    if not options:
        return [{}]

    keys = sorted(options.keys())
    vals = [options[k] for k in keys]
    return [dict(zip(keys, combo)) for combo in itertools.product(*vals)]


def pattern_symbol_counts(pattern: str) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for ch in str(pattern or ""):
        if ch in "_ \t\r\n":
            continue
        counts[ch] = counts.get(ch, 0) + 1
    return counts


def extract_outputs(recipe: dict) -> List[Tuple[str, float]]:
    out = recipe.get("output")
    if out is None:
        out = recipe.get("cooksInto")

    if out is None:
        return []
    if isinstance(out, list):
        results: List[Tuple[str, float]] = []
        for x in out:
            if isinstance(x, dict):
                results.append((code_from_stack(x), read_qty(x, 1.0)))
            elif isinstance(x, str):
                results.append((x, 1.0))
        return [r for r in results if r[0]]

    if isinstance(out, dict):
        code = code_from_stack(out)
        if code:
            return [(code, read_qty(out, 1.0))]
        return []

    if isinstance(out, str):
        return [(out, 1.0)]

    return []


def extract_ingredients(recipe: dict, variant_ctx: Dict[str, str]) -> List[dict]:
    rows: List[dict] = []
    pattern_counts = pattern_symbol_counts(recipe.get("ingredientPattern", ""))

    def add_row(group: int, option_index: int, slot_key: str, stack: object, qty_override: Optional[float] = None):
        if isinstance(stack, dict):
            is_tool = bool(stack.get("isTool"))
            raw_code = code_from_stack(stack)
            raw_code = apply_context(raw_code, variant_ctx)
            allowed = stack.get("allowedVariants") if isinstance(stack.get("allowedVariants"), list) else None
            stack_name = stack.get("name")

            if qty_override is not None:
                qty = qty_override
            else:
                qty = read_qty(stack, 1.0)

            if allowed and "*" in raw_code:
                allowed_values = [str(v) for v in allowed]
                # If this stack maps to an output placeholder, pin to that variant.
                if stack_name in variant_ctx and variant_ctx[stack_name] in allowed_values:
                    allowed_values = [variant_ctx[stack_name]]

                for i, v in enumerate(allowed_values):
                    rows.append(
                        {
                            "ingredient_group": group,
                            "option_index": i,
                            "slot_key": slot_key,
                            "ingredient_code": raw_code.replace("*", v),
                            "quantity": qty,
                            "is_tool": is_tool,
                            "notes": None,
                        }
                    )
                return

            rows.append(
                {
                    "ingredient_group": group,
                    "option_index": option_index,
                    "slot_key": slot_key,
                    "ingredient_code": raw_code,
                    "quantity": qty,
                    "is_tool": is_tool,
                    "notes": None,
                }
            )
            return

        # string/other
        rows.append(
            {
                "ingredient_group": group,
                "option_index": option_index,
                "slot_key": slot_key,
                "ingredient_code": apply_context(str(stack), variant_ctx),
                "quantity": qty_override if qty_override is not None else 1.0,
                "is_tool": False,
                "notes": None,
            }
        )

    ingredients = recipe.get("ingredients")

    if isinstance(ingredients, dict):
        for idx, (slot, stack) in enumerate(ingredients.items(), start=1):
            qty = float(pattern_counts.get(str(slot), 0)) if pattern_counts else None
            if qty is None or qty <= 0:
                qty = read_qty(stack, 1.0)
            add_row(idx, 0, str(slot), stack, qty_override=qty)

    elif isinstance(ingredients, list):
        for idx, ing in enumerate(ingredients, start=1):
            if isinstance(ing, dict) and isinstance(ing.get("validStacks"), list):
                qty = read_qty(ing, 1.0)
                for opt_i, stack in enumerate(ing.get("validStacks", [])):
                    add_row(idx, opt_i, str(ing.get("code", f"slot{idx}")), stack, qty_override=qty)
            else:
                qty = read_qty(ing, 1.0)
                add_row(idx, 0, f"slot{idx}", ing, qty_override=qty)

    # smithing/knapping/clayforming often use singular 'ingredient'
    if recipe.get("ingredient") is not None:
        add_row(9999, 0, "ingredient", recipe.get("ingredient"), qty_override=read_qty(recipe.get("ingredient"), 1.0))

    # prune empties
    return [r for r in rows if r.get("ingredient_code")]


def ensure_schema(cur) -> None:
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS vs_recipe_outputs (
            id BIGSERIAL PRIMARY KEY,
            source_mod TEXT NOT NULL,
            source_path TEXT NOT NULL,
            recipe_index INT NOT NULL,
            recipe_type TEXT NOT NULL,
            output_code TEXT NOT NULL,
            output_variant_key TEXT NOT NULL DEFAULT '',
            output_variant JSONB,
            output_qty NUMERIC NOT NULL DEFAULT 1,
            raw_recipe JSONB NOT NULL,
            inserted_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (source_mod, source_path, recipe_index, output_code, output_variant_key)
        );
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS vs_recipe_ingredients (
            id BIGSERIAL PRIMARY KEY,
            recipe_output_id BIGINT NOT NULL REFERENCES vs_recipe_outputs(id) ON DELETE CASCADE,
            ingredient_group INT NOT NULL,
            option_index INT NOT NULL DEFAULT 0,
            slot_key TEXT,
            ingredient_code TEXT NOT NULL,
            quantity NUMERIC NOT NULL DEFAULT 1,
            is_tool BOOLEAN NOT NULL DEFAULT FALSE,
            notes TEXT,
            inserted_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        """
    )
    cur.execute("CREATE INDEX IF NOT EXISTS idx_vs_recipe_outputs_output_code ON vs_recipe_outputs (output_code);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_vs_recipe_outputs_type ON vs_recipe_outputs (recipe_type);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_vs_recipe_ing_code ON vs_recipe_ingredients (ingredient_code);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_vs_recipe_ing_recipe ON vs_recipe_ingredients (recipe_output_id);")


def truncate_schema(cur) -> None:
    cur.execute("TRUNCATE TABLE vs_recipe_ingredients, vs_recipe_outputs RESTART IDENTITY;")


def ctx_to_key(ctx: Dict[str, str]) -> Optional[str]:
    if not ctx:
        return ""
    pairs = [f"{k}={ctx[k]}" for k in sorted(ctx.keys())]
    return "|".join(pairs)


def import_data(conn, files: Sequence[Tuple[str, str]], batch_size: int) -> Tuple[int, int, int]:
    output_rows: List[Tuple] = []
    ingredient_rows_pending: List[Tuple[int, int, str, str, float, bool, Optional[str], int]] = []
    parse_errors = 0

    for source_mod, path in files:
        try:
            recipes = parse_recipe_file(path)
        except Exception:
            parse_errors += 1
            continue

        for ridx, recipe in enumerate(recipes):
            recipe_type = infer_recipe_type(path, recipe)
            outputs = extract_outputs(recipe)
            if not outputs:
                continue

            for out_code_raw, out_qty in outputs:
                contexts = expand_output_contexts(recipe, out_code_raw)
                for ctx in contexts:
                    out_code = apply_context(out_code_raw, ctx)
                    if not out_code:
                        continue

                    ingredients = extract_ingredients(recipe, ctx)
                    output_rows.append(
                        (
                            source_mod,
                            path,
                            ridx,
                            recipe_type,
                            out_code,
                            ctx_to_key(ctx),
                            Json(ctx) if ctx else None,
                            float(out_qty) if out_qty else 1.0,
                            Json(recipe),
                        )
                    )

                    # stash ingredient payload tied to insertion order index
                    output_idx = len(output_rows) - 1
                    for ing in ingredients:
                        ingredient_rows_pending.append(
                            (
                                ing["ingredient_group"],
                                ing["option_index"],
                                ing.get("slot_key") or "",
                                ing["ingredient_code"],
                                float(ing.get("quantity") or 1.0),
                                bool(ing.get("is_tool")),
                                ing.get("notes"),
                                output_idx,
                            )
                        )

    inserted_outputs = 0
    inserted_ingredients = 0

    with conn.cursor() as cur:
        # Insert outputs in chunks and fetch IDs in same order using RETURNING
        for i in range(0, len(output_rows), batch_size):
            chunk = output_rows[i : i + batch_size]
            execute_values(
                cur,
                """
                INSERT INTO vs_recipe_outputs
                    (source_mod, source_path, recipe_index, recipe_type, output_code, output_variant_key, output_variant, output_qty, raw_recipe)
                VALUES %s
                ON CONFLICT (source_mod, source_path, recipe_index, output_code, output_variant_key)
                DO UPDATE SET
                    recipe_type = EXCLUDED.recipe_type,
                    output_variant = EXCLUDED.output_variant,
                    output_qty = EXCLUDED.output_qty,
                    raw_recipe = EXCLUDED.raw_recipe
                RETURNING id
                """,
                chunk,
                page_size=batch_size,
            )
            ids = [r[0] for r in cur.fetchall()]
            inserted_outputs += len(ids)

            # map local output index -> db id for this chunk
            local_map: Dict[int, int] = {}
            for local_offset, dbid in enumerate(ids):
                local_map[i + local_offset] = dbid

            if ids:
                cur.execute("DELETE FROM vs_recipe_ingredients WHERE recipe_output_id = ANY(%s);", (ids,))

            ing_chunk = [x for x in ingredient_rows_pending if x[7] in local_map]
            if ing_chunk:
                payload = [
                    (local_map[idx], grp, opt, slot, code, qty, is_tool, notes)
                    for (grp, opt, slot, code, qty, is_tool, notes, idx) in ing_chunk
                ]
                execute_values(
                    cur,
                    """
                    INSERT INTO vs_recipe_ingredients
                        (recipe_output_id, ingredient_group, option_index, slot_key, ingredient_code, quantity, is_tool, notes)
                    VALUES %s
                    """,
                    payload,
                    page_size=batch_size,
                )
                inserted_ingredients += len(payload)

    return inserted_outputs, inserted_ingredients, parse_errors


def main() -> None:
    args = parse_args()
    password = resolve_password(args.password)

    files = collect_files_from_base(args.base_game_dir) + collect_files_from_mods(args.unpack_dir)
    print(f"Discovered {len(files)} recipe files.")

    conn = psycopg2.connect(
        host=args.host,
        port=args.port,
        dbname=args.database,
        user=args.user,
        password=password,
    )
    try:
        with conn:
            with conn.cursor() as cur:
                ensure_schema(cur)
                if args.truncate:
                    print("Truncating vs_recipe_outputs / vs_recipe_ingredients...")
                    truncate_schema(cur)

            inserted_outputs, inserted_ingredients, parse_errors = import_data(conn, files, args.batch_size)
            print(f"Inserted/updated outputs: {inserted_outputs}")
            print(f"Inserted ingredients: {inserted_ingredients}")
            print(f"Parse errors skipped: {parse_errors}")

            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM vs_recipe_outputs;")
                total_out = cur.fetchone()[0]
                cur.execute("SELECT COUNT(*) FROM vs_recipe_ingredients;")
                total_ing = cur.fetchone()[0]
                cur.execute(
                    """
                    SELECT recipe_type, COUNT(*)
                    FROM vs_recipe_outputs
                    GROUP BY recipe_type
                    ORDER BY COUNT(*) DESC, recipe_type ASC
                    """
                )
                by_type = cur.fetchall()

            print(f"Total outputs in table: {total_out}")
            print(f"Total ingredients in table: {total_ing}")
            print("Recipe outputs by type:")
            for rtype, cnt in by_type:
                print(f"  {rtype}: {cnt}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
