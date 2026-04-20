#!/usr/bin/env python3
# -----------------------------------------------------------------------------
# DEPRECATED — superseded by parse_recipes_json.py as of 2026-04-04
# Retained for reference only. Do not run as part of the pipeline.
# -----------------------------------------------------------------------------

"""
Ingest Vintage Story base-game grid recipes directly from JSON files into recipe_staging.

Environment variables:
  - DATABASE_URL: PostgreSQL connection string for psycopg2
  - VS_ASSETS_PATH: Path to VS assets root (e.g. C:/Games/Vintagestory/assets/survival)
"""

import os
import re
import sys
from itertools import product
from pathlib import Path
from typing import Dict, List, Sequence, Tuple

import json5
import psycopg2
from dotenv import load_dotenv


load_dotenv()


INSERT_SQL = """
INSERT INTO recipe_staging (
    source_mod,
    recipe_type,
    output_game_code,
    output_qty_raw,
    ingredients_raw
) VALUES (%s, %s, %s, %s, %s)
"""


def parse_json5_file(path: Path) -> List[dict]:
    with path.open("r", encoding="utf-8-sig") as f:
        data = json5.load(f)

    if isinstance(data, dict):
        return [data]
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]
    return []


def ingredient_qty_map(ingredient_pattern: str, ingredients: Dict[str, object]) -> Dict[str, int]:
    if not isinstance(ingredients, dict):
        return {}

    # Grid patterns are usually comma-delimited rows (e.g. "LPL,PCP").
    if isinstance(ingredient_pattern, str) and ingredient_pattern:
        return {
            key: ingredient_pattern.count(key)
            for key in ingredients.keys()
            if isinstance(key, str)
        }

    # Fallback: no pattern available, assume one of each ingredient symbol.
    return {key: 1 for key in ingredients.keys() if isinstance(key, str)}


def build_ingredients_raw(
    recipe: dict,
    variant_subs: Dict[str, str] | None = None,
    use_representative_variant: bool = False,
) -> str:
    ingredients = recipe.get("ingredients")
    if not isinstance(ingredients, dict):
        return ""

    variant_subs = variant_subs or {}

    qty_by_key = ingredient_qty_map(str(recipe.get("ingredientPattern", "")), ingredients)
    parts: List[str] = []

    for key, ingredient in ingredients.items():
        if not isinstance(ingredient, dict):
            continue

        ingredient_qty = ingredient.get("quantity")
        if ingredient_qty is not None:
            try:
                qty = int(ingredient_qty)
            except (TypeError, ValueError):
                qty = int(qty_by_key.get(key, 0))
        else:
            qty = int(qty_by_key.get(key, 0))

        if qty <= 0:
            continue

        code = ingredient.get("code")
        if not code:
            continue

        ingredient_name = ingredient.get("name")
        allowed_variants = ingredient.get("allowedVariants")

        if isinstance(ingredient_name, str) and ingredient_name in variant_subs:
            code = str(code).replace("*", variant_subs[ingredient_name])
        elif (
            use_representative_variant
            and isinstance(allowed_variants, list)
            and allowed_variants
        ):
            code = str(code).replace("*", str(allowed_variants[0]))

        ingredient_type = str(ingredient.get("type", "item")).strip().lower() or "item"
        if ingredient_type not in {"item", "block"}:
            ingredient_type = "item"

        entry = f"{qty}x {ingredient_type}:{code}"

        should_annotate_variants = not (
            isinstance(ingredient_name, str) and ingredient_name in variant_subs
        )
        if should_annotate_variants and isinstance(allowed_variants, list) and allowed_variants:
            variants = ",".join(str(v) for v in allowed_variants)
            entry = f"{entry} (variants={variants})"

        parts.append(entry)

    return "; ".join(parts)


def recipe_to_rows(recipe: dict) -> Tuple[List[Tuple[str, str, str, str, str]], Dict[str, int]]:
    diagnostics = {
        "recipes_no_output_placeholder": 0,
        "recipes_with_output_placeholder": 0,
        "recipes_with_resolvable_placeholder": 0,
        "recipes_with_unresolvable_placeholder": 0,
        "rows_from_resolvable_placeholder_expansion": 0,
    }

    output = recipe.get("output")
    if not isinstance(output, dict):
        return [], diagnostics

    output_code = output.get("code")
    if not output_code:
        return [], diagnostics

    output_qty = output.get("quantity", 1)
    output_code_str = str(output_code)

    placeholders = re.findall(r"\{(\w+)\}", output_code_str)
    if not placeholders:
        diagnostics["recipes_no_output_placeholder"] = 1
        return (
            [
                (
                    "Base Game JSON",
                    "grid",
                    output_code_str,
                    str(output_qty),
                    build_ingredients_raw(recipe, use_representative_variant=True),
                )
            ],
            diagnostics,
        )

    diagnostics["recipes_with_output_placeholder"] = 1

    ingredients = recipe.get("ingredients")
    if not isinstance(ingredients, dict):
        ingredients = {}

    variants_by_placeholder: Dict[str, List[str]] = {}
    for placeholder in placeholders:
        variant_values: List[str] = []
        for ingredient in ingredients.values():
            if not isinstance(ingredient, dict):
                continue
            if ingredient.get("name") != placeholder:
                continue

            allowed_variants = ingredient.get("allowedVariants")
            if isinstance(allowed_variants, list) and allowed_variants:
                variant_values = [str(v) for v in allowed_variants]
                break

        if variant_values:
            variants_by_placeholder[placeholder] = variant_values

    if not variants_by_placeholder:
        diagnostics["recipes_with_unresolvable_placeholder"] = 1
        return (
            [
                (
                    "Base Game JSON",
                    "grid",
                    output_code_str,
                    str(output_qty),
                    build_ingredients_raw(recipe, use_representative_variant=True),
                )
            ],
            diagnostics,
        )

    varying_keys = sorted(variants_by_placeholder.keys())
    rows: List[Tuple[str, str, str, str, str]] = []

    for variant_tuple in product(*(variants_by_placeholder[k] for k in varying_keys)):
        variant_subs = dict(zip(varying_keys, variant_tuple))
        resolved_output_code = output_code_str
        for key, value in variant_subs.items():
            resolved_output_code = resolved_output_code.replace(f"{{{key}}}", value)

        rows.append(
            (
                "Base Game JSON",
                "grid",
                resolved_output_code,
                str(output_qty),
                build_ingredients_raw(recipe, variant_subs),
            )
        )

    diagnostics["recipes_with_resolvable_placeholder"] = 1
    diagnostics["rows_from_resolvable_placeholder_expansion"] = len(rows)
    return rows, diagnostics


def collect_grid_json_files(vs_assets_path: Path) -> List[Path]:
    grid_root = vs_assets_path / "recipes" / "grid"
    if not grid_root.is_dir():
        return []
    return sorted(grid_root.rglob("*.json"))


def main() -> int:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("[ERROR] DATABASE_URL environment variable is not set.", file=sys.stderr)
        return 1

    vs_assets_path_raw = os.getenv("VS_ASSETS_PATH")
    if not vs_assets_path_raw:
        print("[ERROR] VS_ASSETS_PATH environment variable is not set.", file=sys.stderr)
        return 1

    vs_assets_path = Path(vs_assets_path_raw)
    json_files = collect_grid_json_files(vs_assets_path)
    if not json_files:
        print(f"[ERROR] No grid recipe files found under: {vs_assets_path / 'recipes' / 'grid'}", file=sys.stderr)
        return 1

    rows: List[Tuple[str, str, str, str, str]] = []
    parse_failures: List[Tuple[str, str]] = []

    files_read = 0
    recipes_parsed = 0
    debug_ingredients_raw_samples: List[str] = []

    recipes_no_output_placeholder = 0
    recipes_with_output_placeholder = 0
    recipes_with_resolvable_placeholder = 0
    recipes_with_unresolvable_placeholder = 0
    rows_from_resolvable_placeholder_expansion = 0

    for path in json_files:
        files_read += 1
        try:
            recipes = parse_json5_file(path)
        except Exception as exc:
            parse_failures.append((str(path), str(exc)))
            continue

        for recipe in recipes:
            expanded_rows, diagnostics = recipe_to_rows(recipe)
            if not expanded_rows:
                continue
            rows.extend(expanded_rows)

            recipes_no_output_placeholder += diagnostics["recipes_no_output_placeholder"]
            recipes_with_output_placeholder += diagnostics["recipes_with_output_placeholder"]
            recipes_with_resolvable_placeholder += diagnostics["recipes_with_resolvable_placeholder"]
            recipes_with_unresolvable_placeholder += diagnostics["recipes_with_unresolvable_placeholder"]
            rows_from_resolvable_placeholder_expansion += diagnostics[
                "rows_from_resolvable_placeholder_expansion"
            ]

            for row in expanded_rows:
                if len(debug_ingredients_raw_samples) < 10:
                    debug_ingredients_raw_samples.append(row[4])
            recipes_parsed += 1

    debug_sample_path = Path("data") / "debug_grid_parsed_sample.txt"
    try:
        debug_sample_path.parent.mkdir(parents=True, exist_ok=True)
        with debug_sample_path.open("w", encoding="utf-8") as f:
            for i, ingredients_raw in enumerate(debug_ingredients_raw_samples, start=1):
                f.write(f"{i}. {ingredients_raw}\n")
    except Exception as exc:
        print(f"[WARN] Failed writing debug sample file {debug_sample_path}: {exc}", file=sys.stderr)

    try:
        with psycopg2.connect(database_url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    DELETE FROM recipe_staging
                    WHERE recipe_type = 'grid'
                      AND source_mod = 'Base Game'
                    """
                )

                if rows:
                    cur.executemany(INSERT_SQL, rows)
    except Exception as exc:
        print(f"[ERROR] Database ingestion failed: {exc}", file=sys.stderr)
        return 1

    print(f"Total files read: {files_read}")
    print(f"Total grid recipes parsed: {recipes_parsed}")
    print(f"Rows inserted: {len(rows)}")
    print("Placeholder diagnostics:")
    print(f"- Recipes with no output placeholder: {recipes_no_output_placeholder}")
    print(f"- Recipes with output placeholder(s): {recipes_with_output_placeholder}")
    print(f"- Placeholder recipes (resolvable): {recipes_with_resolvable_placeholder}")
    print(f"- Placeholder recipes (unresolvable): {recipes_with_unresolvable_placeholder}")
    print(
        "- Rows from resolvable placeholder expansion: "
        f"{rows_from_resolvable_placeholder_expansion}"
    )

    expected_total_rows = (
        recipes_no_output_placeholder
        + recipes_with_unresolvable_placeholder
        + rows_from_resolvable_placeholder_expansion
    )
    print(
        "Expected total rows = "
        f"{recipes_no_output_placeholder} (no placeholder recipes)"
        f" + {recipes_with_unresolvable_placeholder} (unresolvable placeholder recipes)"
        f" + {rows_from_resolvable_placeholder_expansion} (rows from resolvable placeholder expansion)"
        f" = {expected_total_rows}"
    )
    print(f"Expected total matches inserted rows: {expected_total_rows == len(rows)}")
    print(f"Files failed to parse: {len(parse_failures)}")

    if parse_failures:
        print("Failed files:")
        for file_path, error in parse_failures:
            print(f"- {file_path} :: {error}")

    print("Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
