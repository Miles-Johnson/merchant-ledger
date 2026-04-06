#!/usr/bin/env python3
# -----------------------------------------------------------------------------
# DEPRECATED — superseded by parse_recipes_json.py as of 2026-04-04
# Retained for reference only. Do not run as part of the pipeline.
# -----------------------------------------------------------------------------

"""
Parse recipe_staging rows into normalized recipes + recipe_ingredients tables.

Environment variables:
  - DATABASE_URL: PostgreSQL connection string for psycopg2
"""

from __future__ import annotations

import os
import re
import sys
import json
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from fnmatch import fnmatch
from pathlib import Path
from typing import List, Optional

import psycopg2
from dotenv import load_dotenv


load_dotenv()


@dataclass
class ParsedIngredient:
    input_game_code: str
    qty: Optional[Decimal]
    ratio_min: Optional[Decimal]
    ratio_max: Optional[Decimal]
    variant_group_id: Optional[str]
    is_primary_variant: bool


QTY_PREFIX_RE = re.compile(r"^(?P<qty>\d+(?:\.\d+)?)x\s+(?P<rest>.+)$")
PARENS_RE = re.compile(r"\(([^()]*)\)")
RATIO_RE = re.compile(r"^ratio=(?P<min>\d+(?:\.\d+)?)\-(?P<max>\d+(?:\.\d+)?)$")
VARIANTS_RE = re.compile(r"^variants=(?P<values>.+)$")
NAMED_SLOT_RE = re.compile(
    r"^(?P<name>[^=]+?)\s*=\s*\{(?P<codes>[^}]+)\}\s*(?:\((?P<min>\d+(?:\.\d+)?)-(?P<max>\d+(?:\.\d+)?)\))?\s*$"
)
PLACEHOLDER_RE = re.compile(r"\{[^}]+\}")
VARIANTS_SEGMENT_RE = re.compile(r"\(\s*variants=[^()]*\)")
GRID_SLOT_PREFIX_RE = re.compile(r"^[A-Z]=")
TOOL_CHUNK_RE = re.compile(r"^tool(?:,\s*dur=\d+)?$", re.IGNORECASE)
DUR_FRAGMENT_RE = re.compile(r"^dur=\d+\)?$", re.IGNORECASE)


def load_smithing_quantity_lookup() -> dict[str, int]:
    """Load manual smithing quantity overrides from data/smithing_quantities.json."""
    lookup_path = Path(__file__).resolve().parents[1] / "data" / "smithing_quantities.json"
    if not lookup_path.exists():
        print(f"[WARN] Smithing quantity lookup missing: {lookup_path}")
        return {}

    try:
        raw = json.loads(lookup_path.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"[WARN] Failed to read smithing quantity lookup: {exc}")
        return {}

    if not isinstance(raw, dict):
        print("[WARN] smithing_quantities.json root must be an object")
        return {}

    cleaned: dict[str, int] = {}
    for key, value in raw.items():
        key_text = str(key).strip()
        if not key_text or key_text.startswith("_"):
            continue
        try:
            cleaned[key_text] = int(value)
        except (TypeError, ValueError):
            print(f"[WARN] Invalid smithing quantity for '{key_text}': {value}")
    return cleaned


def smithing_quantity_for_output(output_game_code: str, lookup: dict[str, int]) -> Optional[int]:
    """
    Match manual smithing quantity by output code prefix pattern.

    Supports lookup keys like `metalplate-*` against output forms such as:
      - item:metalplate-iron
      - item:game:metalplate-iron
      - item:metalplate-{metal}
    """
    if not lookup:
        return None

    out = (output_game_code or "").strip()
    if not out:
        return None

    candidates = {out}
    parts = out.split(":")
    if len(parts) >= 2:
        candidates.add(parts[-1])

    for candidate in list(candidates):
        candidates.add(candidate.replace("{", "").replace("}", ""))
        candidates.add(candidate.replace("{metal}", "*"))

    for pattern, qty in lookup.items():
        for candidate in candidates:
            if fnmatch(candidate, pattern):
                return qty

    return None


def normalize_game_code(game_code: str) -> str:
    """
    Keep only first and last namespace segments when 3+ segments exist.

    Examples:
      item:game:ingot-iron -> item:ingot-iron
      item:pipeleaf:smokable-pipeleaf-cured -> item:smokable-pipeleaf-cured
      item:ingot-iron -> item:ingot-iron
    """
    text = (game_code or "").strip()
    if not text:
        return text

    parts = text.split(":")
    if len(parts) >= 3:
        return f"{parts[0].lower()}:{parts[-1]}"
    if len(parts) == 2:
        left = parts[0].lower()
        if left in {"item", "block"}:
            return f"{left}:{parts[1]}"
    return text


INSERT_RECIPE_SQL = """
INSERT INTO recipes (
    output_canonical_id,
    output_game_code,
    output_qty,
    recipe_type,
    source_mod
) VALUES (NULL, %s, %s, %s, %s)
RETURNING id
"""


INSERT_INGREDIENT_SQL = """
INSERT INTO recipe_ingredients (
    recipe_id,
    input_canonical_id,
    input_game_code,
    qty,
    ratio_min,
    ratio_max,
    variant_group_id,
    is_primary_variant
) VALUES (%s, NULL, %s, %s, %s, %s, %s, %s)
"""


def parse_decimal_or_default(raw: object, default: Decimal) -> Decimal:
    if raw is None:
        return default

    text = str(raw).strip()
    if text == "":
        return default

    try:
        return Decimal(text)
    except (InvalidOperation, ValueError):
        return default


def _split_ingredient_tokens(raw_ingredients_text: str) -> List[str]:
    return [t.strip() for t in raw_ingredients_text.split(";") if t.strip()]


def expand_output_variants(output_game_code: str, ingredients_raw: str) -> Optional[List[tuple[str, str]]]:
    """
    Expand templated output rows when output contains {...} and ingredients include variants.

    Uses the *first* ingredient token containing `(variants=...)` as the driver.
    For each variant:
      - output placeholder(s) are replaced with that variant
      - driving ingredient token replaces `*` with the variant and removes `(variants=...)`
    """
    output_text = (output_game_code or "").strip()
    ingredients_text = (ingredients_raw or "").strip()

    if not PLACEHOLDER_RE.search(output_text) or not ingredients_text:
        return None

    tokens = _split_ingredient_tokens(ingredients_text)
    if not tokens:
        return None

    driver_index: Optional[int] = None
    driver_variants: Optional[List[str]] = None

    for idx, token in enumerate(tokens):
        paren_chunks = PARENS_RE.findall(token)
        for chunk in paren_chunks:
            match = VARIANTS_RE.match(chunk.strip())
            if not match:
                continue

            values = [v.strip() for v in match.group("values").split(",") if v.strip()]
            if values:
                driver_index = idx
                driver_variants = values
                break
        if driver_variants:
            break

    if driver_index is None or not driver_variants:
        return None

    expanded_rows: List[tuple[str, str]] = []
    for variant in driver_variants:
        expanded_output = PLACEHOLDER_RE.sub(variant, output_text)

        expanded_tokens: List[str] = []
        for idx, token in enumerate(tokens):
            updated = token
            if idx == driver_index:
                updated = updated.replace("*", variant)
                updated = VARIANTS_SEGMENT_RE.sub("", updated)
                updated = re.sub(r"\s+", " ", updated).strip()
            expanded_tokens.append(updated)

        expanded_rows.append((expanded_output, "; ".join(expanded_tokens)))

    return expanded_rows


def parse_ingredient_token(token: str, recipe_id: int, position: int) -> tuple[List[ParsedIngredient], bool, bool]:
    """
    Returns (rows, is_alloy, is_wildcard_group).

    Raises ValueError when token cannot be parsed.
    """
    original = token
    token = token.strip()
    if not token:
        raise ValueError("empty ingredient")

    # Grid recipe slots may prefix ingredients as e.g. "P=item:ingot-iron".
    token = GRID_SLOT_PREFIX_RE.sub("", token)

    # Cooking/barrel style named slot format, e.g.
    # mordant={item:game:a | item:game:b} (1-1)
    # lead={item:em:powdered-metal-lead} (1-1)
    named_slot_match = NAMED_SLOT_RE.match(token)
    if named_slot_match:
        raw_codes = named_slot_match.group("codes") or ""
        codes = [normalize_game_code(c.strip()) for c in raw_codes.split("|") if c.strip()]
        if not codes:
            raise ValueError("named slot has no codes inside braces")

        qty_min_text = named_slot_match.group("min")
        if qty_min_text:
            try:
                qty = Decimal(qty_min_text)
            except (InvalidOperation, ValueError):
                raise ValueError(f"invalid named slot quantity range: {qty_min_text}")
        else:
            qty = Decimal("1")

        if len(codes) == 1:
            return (
                [
                    ParsedIngredient(
                        input_game_code=codes[0],
                        qty=qty,
                        ratio_min=None,
                        ratio_max=None,
                        variant_group_id=None,
                        is_primary_variant=False,
                    )
                ],
                False,
                False,
            )

        group_id = f"{recipe_id}_{position}"
        rows = []
        for idx, code in enumerate(codes):
            rows.append(
                ParsedIngredient(
                    input_game_code=code,
                    qty=qty,
                    ratio_min=None,
                    ratio_max=None,
                    variant_group_id=group_id,
                    is_primary_variant=(idx == 0),
                )
            )
        return (rows, False, True)

    # Skip orphan durability fragments (e.g. "dur=150)"), which have no item code.
    if DUR_FRAGMENT_RE.match(token):
        return ([], False, False)

    qty: Optional[Decimal] = Decimal("1")
    ratio_min: Optional[Decimal] = None
    ratio_max: Optional[Decimal] = None
    variants: Optional[List[str]] = None
    is_tool = False

    qty_match = QTY_PREFIX_RE.match(token)
    if qty_match:
        qty_text = qty_match.group("qty")
        try:
            qty = Decimal(qty_text)
        except (InvalidOperation, ValueError):
            raise ValueError(f"invalid quantity prefix: {qty_text}")
        token = qty_match.group("rest").strip()

    paren_chunks = PARENS_RE.findall(token)
    code = normalize_game_code(PARENS_RE.sub("", token).strip())

    if not code:
        raise ValueError("missing input game code")

    for chunk in paren_chunks:
        inner = chunk.strip()

        if TOOL_CHUNK_RE.match(inner):
            is_tool = True
            continue

        ratio_match = RATIO_RE.match(inner)
        if ratio_match:
            try:
                ratio_min = Decimal(ratio_match.group("min"))
                ratio_max = Decimal(ratio_match.group("max"))
            except (InvalidOperation, ValueError):
                raise ValueError(f"invalid ratio values: {inner}")
            continue

        variants_match = VARIANTS_RE.match(inner)
        if variants_match:
            raw_values = variants_match.group("values")
            split_values = [v.strip() for v in raw_values.split(",")]
            variants = [v for v in split_values if v]
            if not variants:
                raise ValueError("variants list is empty")
            continue

        raise ValueError(f"unrecognized parenthetical segment: ({inner})")

    # Tool ingredients are non-consumable and should not be inserted.
    if is_tool:
        return ([], False, False)

    is_alloy = ratio_min is not None or ratio_max is not None
    if is_alloy and (ratio_min is None or ratio_max is None):
        raise ValueError("incomplete ratio definition")

    # Alloy rows use ratio fields and no quantity.
    if is_alloy:
        return (
            [
                ParsedIngredient(
                    input_game_code=code,
                    qty=None,
                    ratio_min=ratio_min,
                    ratio_max=ratio_max,
                    variant_group_id=None,
                    is_primary_variant=False,
                )
            ],
            True,
            False,
        )

    has_wildcard = "*" in code
    if has_wildcard:
        if not variants:
            raise ValueError("wildcard ingredient is missing variants list")

        group_id = f"{recipe_id}_{position}"
        rows = []
        for idx, variant in enumerate(variants):
            resolved_code = code.replace("*", variant)
            rows.append(
                ParsedIngredient(
                    input_game_code=resolved_code,
                    qty=qty,
                    ratio_min=None,
                    ratio_max=None,
                    variant_group_id=group_id,
                    is_primary_variant=(idx == 0),
                )
            )

        return (rows, False, True)

    # Some staging rows encode wildcard variants as a concrete sample code plus
    # `(variants=...)`, e.g. `item:metalplate-copper (variants=copper,brass,...)`.
    # Expand these into a variant group by replacing the trailing `-<sample>` with
    # each listed variant.
    if variants and not has_wildcard:
        base_code = code
        sample_variant = None

        right = base_code.split(":", 1)[-1]
        if "-" in right:
            candidate = right.rsplit("-", 1)[-1]
            if candidate in variants:
                sample_variant = candidate

        if sample_variant is None:
            # Fallback: keep the concrete code as a single ingredient instead of
            # dropping it. This preserves parser robustness for odd mod inputs.
            return (
                [
                    ParsedIngredient(
                        input_game_code=code,
                        qty=qty,
                        ratio_min=None,
                        ratio_max=None,
                        variant_group_id=None,
                        is_primary_variant=False,
                    )
                ],
                False,
                False,
            )

        group_id = f"{recipe_id}_{position}"
        rows = []
        for idx, variant in enumerate(variants):
            resolved_code = base_code.rsplit(sample_variant, 1)[0] + variant
            rows.append(
                ParsedIngredient(
                    input_game_code=resolved_code,
                    qty=qty,
                    ratio_min=None,
                    ratio_max=None,
                    variant_group_id=group_id,
                    is_primary_variant=(idx == 0),
                )
            )

        return (rows, False, True)

    return (
        [
            ParsedIngredient(
                input_game_code=code,
                qty=qty,
                ratio_min=None,
                ratio_max=None,
                variant_group_id=None,
                is_primary_variant=False,
            )
        ],
        False,
        False,
    )


def main() -> int:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("[ERROR] DATABASE_URL environment variable is not set.", file=sys.stderr)
        return 1

    recipes_inserted = 0
    ingredients_inserted = 0
    alloy_ingredients = 0
    wildcard_groups = 0
    smithing_lookup = load_smithing_quantity_lookup()

    try:
        with psycopg2.connect(database_url) as conn:
            with conn.cursor() as cur:
                cur.execute("TRUNCATE TABLE recipe_ingredients, recipes RESTART IDENTITY")

                cur.execute(
                    """
                    SELECT id, source_mod, recipe_type, output_game_code, output_qty_raw, ingredients_raw
                    FROM recipe_staging
                    ORDER BY id
                    """
                )
                staging_rows = cur.fetchall()

                for _staging_id, source_mod, recipe_type, output_game_code, output_qty_raw, ingredients_raw in staging_rows:
                    output_qty = parse_decimal_or_default(output_qty_raw, Decimal("1"))

                    expanded_rows = expand_output_variants(output_game_code or "", ingredients_raw or "")
                    rows_to_insert = expanded_rows if expanded_rows else [((output_game_code or ""), (ingredients_raw or ""))]

                    for expanded_output_code, expanded_ingredients_raw in rows_to_insert:
                        normalized_output_code = normalize_game_code(expanded_output_code)

                        cur.execute(
                            INSERT_RECIPE_SQL,
                            (
                                normalized_output_code,
                                output_qty,
                                recipe_type,
                                source_mod,
                            ),
                        )
                        recipe_id = cur.fetchone()[0]
                        recipes_inserted += 1

                        raw_ingredients_text = (expanded_ingredients_raw or "").strip()
                        if not raw_ingredients_text:
                            continue

                        ingredient_tokens = _split_ingredient_tokens(raw_ingredients_text)
                        is_smithing_recipe = "smithing" in str(recipe_type or "").lower()

                        smithing_qty_override: Optional[Decimal] = None
                        if is_smithing_recipe and len(ingredient_tokens) == 1:
                            matched_qty = smithing_quantity_for_output(normalized_output_code, smithing_lookup)
                            if matched_qty is None:
                                print(
                                    f"[WARN] Smithing quantity missing in lookup for output '{normalized_output_code}'"
                                )
                            else:
                                smithing_qty_override = Decimal(str(matched_qty))

                        for position, token in enumerate(ingredient_tokens, start=1):
                            token_without_slot = GRID_SLOT_PREFIX_RE.sub("", token.strip())
                            has_explicit_qty_prefix = bool(QTY_PREFIX_RE.match(token_without_slot))

                            try:
                                parsed_rows, is_alloy, is_wildcard_group = parse_ingredient_token(
                                    token=token,
                                    recipe_id=recipe_id,
                                    position=position,
                                )
                            except ValueError as exc:
                                print(f"[WARN] Skipping unparseable ingredient: '{token}' ({exc})")
                                continue

                            if is_alloy:
                                alloy_ingredients += len(parsed_rows)
                            if is_wildcard_group:
                                wildcard_groups += 1

                            if (
                                smithing_qty_override is not None
                                and not has_explicit_qty_prefix
                                and not is_alloy
                                and len(ingredient_tokens) == 1
                            ):
                                parsed_rows = [
                                    ParsedIngredient(
                                        input_game_code=row.input_game_code,
                                        qty=smithing_qty_override,
                                        ratio_min=row.ratio_min,
                                        ratio_max=row.ratio_max,
                                        variant_group_id=row.variant_group_id,
                                        is_primary_variant=row.is_primary_variant,
                                    )
                                    for row in parsed_rows
                                ]

                            insert_values = [
                                (
                                    recipe_id,
                                    row.input_game_code,
                                    row.qty,
                                    row.ratio_min,
                                    row.ratio_max,
                                    row.variant_group_id,
                                    row.is_primary_variant,
                                )
                                for row in parsed_rows
                            ]

                            cur.executemany(INSERT_INGREDIENT_SQL, insert_values)
                            ingredients_inserted += len(insert_values)

    except Exception as exc:
        print(f"[ERROR] Failed to parse recipes: {exc}", file=sys.stderr)
        return 1

    print(f"Total recipes inserted: {recipes_inserted}")
    print(f"Total ingredients inserted: {ingredients_inserted}")
    print(f"Alloy ingredients: {alloy_ingredients}")
    print(f"Wildcard groups expanded: {wildcard_groups}")
    print("[OK] Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
