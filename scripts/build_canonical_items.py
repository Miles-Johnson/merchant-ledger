#!/usr/bin/env python3
"""
Build canonical_items from recipe outputs and Lost Realm items.

Behavior:
  - Reads DATABASE_URL from environment.
  - Truncates canonical_items on each run.
  - Collects candidates from:
      A) distinct recipes.output_game_code
      B) lr_items (id, display_name, lr_category)
      C) distinct recipe_ingredients.input_game_code
  - Cross-matches game codes to LR items with exact/high/low priority.
  - Inserts one row per unique slug (disambiguating with _2, _3, ...).
"""

from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass
import json
from difflib import SequenceMatcher
from typing import Dict, List, Optional, Sequence, Set, Tuple

import psycopg2
from dotenv import load_dotenv


load_dotenv()


@dataclass(frozen=True)
class LRItem:
    id: int
    display_name: str
    lr_category: Optional[str]


@dataclass(frozen=True)
class FTAItem:
    id: int
    display_name: str


@dataclass
class CanonicalRow:
    slug: str
    display_name: str
    game_code: Optional[str]
    lr_item_id: Optional[int]
    fta_item_id: Optional[int]
    match_tier: Optional[str]
    match_score: Optional[float]


NORMALIZE_COMPARE_RE = re.compile(r"[-_\s]+")
NON_SLUG_CHAR_RE = re.compile(r"[^a-z0-9_]+")
MULTI_UNDERSCORE_RE = re.compile(r"_+")
PLACEHOLDER_RE = re.compile(r"\{[^}]+\}")
PAREN_SUFFIX_RE = re.compile(r"\s*\([^)]*\)\s*$")
PAREN_CONTENT_RE = re.compile(r"\(([^)]*)\)")
UPPERCASE_PAREN_CONTENT_RE = re.compile(r"^[A-Z0-9\s'&/\-]+$")
ADMIN_NOTE_CONTENT_RE = re.compile(
    r"^(?:"
    r"havent\s+changed"
    r"|not\s+buying"
    r"|limit\b.*"
    r"|per\s+barrel\b.*"
    r")$",
    re.IGNORECASE,
)
NON_ALNUM_SPACE_RE = re.compile(r"[^a-z0-9\s]+")
MULTI_SPACE_RE = re.compile(r"\s+")
SUFFIX_MATCH_PREFIXES = frozenset(
    {
        "ingot",
        "ore",
        "nugget",
        "dust",
        "powder",
        "plate",
        "sheet",
        "log",
        "plank",
        "block",
        "grain",
        "seed",
        "flower",
        "crop",
    }
)

METAL_VARIANT_MATERIALS = {
    "copper",
    "iron",
    "tinbronze",
    "bismuthbronze",
    "blackbronze",
    "gold",
    "silver",
    "steel",
    "meteoriciron",
    "lead",
    "tin",
    "zinc",
    "nickel",
    "brass",
    "chromium",
    "cupronickel",
    "electrum",
    "molybdochalkos",
    "platinum",
    "titanium",
}


def normalize_game_code(game_code: str) -> str:
    """
    Normalize codes to a canonical stored form that always retains a type domain
    prefix (`item:`/`block:`).

    Examples:
      item:game:ingot-iron -> item:ingot-iron
      item:pipeleaf:smokable-pipeleaf-cured -> item:smokable-pipeleaf-cured
      item:ingot-iron -> item:ingot-iron
      ingot-iron -> item:ingot-iron
    """
    text = (game_code or "").strip()
    if not text:
        return text

    parts = text.split(":")
    if len(parts) >= 3:
        return f"{parts[0].lower()}:{parts[-1]}"
    if len(parts) == 2:
        domain = parts[0].lower()
        if domain in {"item", "block"}:
            return f"{domain}:{parts[-1]}"
        return f"item:{parts[-1]}"
    if len(parts) == 1:
        return f"item:{parts[0]}"
    return text


def game_code_tail(game_code: str) -> str:
    """Return the segment after the last namespace colon."""
    return (game_code or "").strip().split(":")[-1]


def slug_from_game_code(game_code: str) -> str:
    tail = game_code_tail(game_code)
    slug = tail.lower().replace("-", "_").replace(":", "_")
    slug = NON_SLUG_CHAR_RE.sub("", slug)
    slug = MULTI_UNDERSCORE_RE.sub("_", slug).strip("_")
    return slug or "item"


def slug_from_display_name(display_name: str) -> str:
    text = (display_name or "").strip().lower()
    text = text.replace(" ", "_")
    text = NON_SLUG_CHAR_RE.sub("", text)
    text = MULTI_UNDERSCORE_RE.sub("_", text).strip("_")
    return text or "item"


def normalize_for_compare(value: str) -> str:
    return NORMALIZE_COMPARE_RE.sub("", (value or "").lower())


def normalize_name_for_linking(value: str) -> str:
    text = (value or "").lower()
    text = NON_ALNUM_SPACE_RE.sub(" ", text)
    text = MULTI_SPACE_RE.sub(" ", text).strip()
    return text


def trigram_set(value: str) -> Set[str]:
    text = normalize_name_for_linking(value)
    if not text:
        return set()
    padded = f"  {text}  "
    return {padded[i : i + 3] for i in range(len(padded) - 2)}


def trigram_similarity(a: str, b: str) -> float:
    """Dice coefficient over trigram sets."""
    ta = trigram_set(a)
    tb = trigram_set(b)
    if not ta or not tb:
        return 0.0
    overlap = len(ta.intersection(tb))
    return (2.0 * overlap) / (len(ta) + len(tb))


def trigram_similarity_sets(ta: Set[str], tb: Set[str]) -> float:
    if not ta or not tb:
        return 0.0
    overlap = len(ta.intersection(tb))
    return (2.0 * overlap) / (len(ta) + len(tb))


def normalize_lr_name_for_match(display_name: str) -> str:
    """
    Normalize LR display names for matching only.

    Parenthetical suffixes (sub-category hints) are stripped first:
      "Iron Brigandine (Brigandine)" -> "Iron Brigandine" -> "ironbrigandine"
    """
    text = (display_name or "").strip()
    text = PAREN_SUFFIX_RE.sub("", text).strip()
    return normalize_for_compare(text)


def strip_admin_note_parentheticals(display_name: str) -> str:
    text = (display_name or "").strip()
    if not text:
        return text

    def should_strip(content: str) -> bool:
        cleaned = (content or "").strip()
        if not cleaned:
            return False

        if ADMIN_NOTE_CONTENT_RE.match(cleaned):
            return True

        return bool(UPPERCASE_PAREN_CONTENT_RE.match(cleaned) and re.search(r"[A-Z]", cleaned))

    cleaned_name = text
    for match in list(PAREN_CONTENT_RE.finditer(text)):
        content = match.group(1)
        if should_strip(content):
            full_paren = match.group(0)
            cleaned_name = cleaned_name.replace(full_paren, " ")

    cleaned_name = re.sub(r"\s+", " ", cleaned_name).strip()
    return cleaned_name


def canonical_display_name_from_lr(lr_display_name: str, fallback_tail: str) -> str:
    cleaned = strip_admin_note_parentheticals(lr_display_name)
    return cleaned or humanize_game_tail(fallback_tail)


def lr_name_overlaps_game_code(lr_name: str, game_code_tail: str) -> bool:
    """
    For low-tier matches, determine whether LR-name inheritance is still safe.

    Rules:
      - extract LR words longer than 3 chars
      - strip trailing 's' from each word (plural handling)
      - if ANY normalized word appears in game-code tail (case-insensitive), overlap=True
    """
    tail = (game_code_tail or "").lower()
    if not tail:
        return False

    words = re.findall(r"[A-Za-z]+", lr_name or "")
    for word in words:
        if len(word) <= 3:
            continue
        stem = word.lower()
        if stem.endswith("s") and len(stem) > 1:
            stem = stem[:-1]
        if stem and stem in tail:
            return True
    return False


def canonical_display_name_for_match(
    *,
    tier: str,
    tail: str,
    lr_display_name: Optional[str],
) -> str:
    """
    Select canonical display_name from match confidence.

    Low-confidence LR fuzzy matches should retain game-code-derived naming to avoid
    propagating potentially incorrect LR display-name aliases.
    """
    if (tier or "").lower() == "low":
        if lr_display_name and lr_name_overlaps_game_code(lr_display_name, tail):
            return canonical_display_name_from_lr(lr_display_name, tail)
        return humanize_game_tail(tail)
    if lr_display_name:
        return canonical_display_name_from_lr(lr_display_name, tail)
    return humanize_game_tail(tail)


def humanize_game_tail(tail: str) -> str:
    text = (tail or "").strip()
    # Remove template placeholders entirely (e.g. "metalplate-{metal}" -> "metalplate-").
    text = PLACEHOLDER_RE.sub("", text)
    text = re.sub(r"[-_]{2,}", "-", text)
    text = text.strip("-_ ")

    text = text.replace("-", " ").replace("_", " ").strip()
    text = re.sub(r"\s+", " ", text)
    return text.title() if text else "Unknown Item"


def disambiguate_slug(base_slug: str, seen: Set[str]) -> str:
    slug = base_slug or "item"
    if slug not in seen:
        seen.add(slug)
        return slug

    index = 2
    while True:
        candidate = f"{slug}_{index}"
        if candidate not in seen:
            seen.add(candidate)
            return candidate
        index += 1


def choose_best_lr_match(game_tail: str, lr_items: Sequence[LRItem]) -> Tuple[Optional[LRItem], str, Optional[float]]:
    """
    Return (best_item, tier, score).

    Tiers:
      - exact (score 1.0)
      - suffix (score 1.0)
      - contains (score 1.0)
      - high (ratio >= 0.90)
      - low  (0.75 <= ratio <= 0.89)
      - unmatched
    """
    norm_tail = normalize_for_compare(game_tail)
    segments = [seg.strip() for seg in (game_tail or "").split("-") if seg.strip()]

    # Exact pass
    for item in lr_items:
        if normalize_lr_name_for_match(item.display_name) == norm_tail:
            return item, "exact", 1.0

    # Suffix pass (last '-' segment), only for short tails (1-2 segments)
    # where the preceding type segment is in a raw-material whitelist.
    if segments and len(segments) <= 2:
        prefix = normalize_for_compare(segments[0]) if len(segments) == 2 else ""
        if prefix in SUFFIX_MATCH_PREFIXES:
            # Try matching full-tail shape before plain last-segment suffix.
            # Example: metalplate-iron -> ironplate
            for token in SUFFIX_MATCH_PREFIXES:
                if prefix.endswith(token):
                    norm_full_tail_shape = normalize_for_compare(f"{segments[-1]}{token}")
                    for item in lr_items:
                        if normalize_lr_name_for_match(item.display_name) == norm_full_tail_shape:
                            return item, "suffix", 1.0

            norm_suffix = normalize_for_compare(segments[-1])
            for item in lr_items:
                if normalize_lr_name_for_match(item.display_name) == norm_suffix:
                    return item, "suffix", 1.0

    # LR-name-contained-in-tail pass, only if LR name is >50% of tail length.
    for item in lr_items:
        norm_name = normalize_lr_name_for_match(item.display_name)
        if not norm_name or not norm_tail:
            continue
        if norm_name in norm_tail and (len(norm_name) / len(norm_tail)) > 0.50:
            return item, "contains", 1.0

    # Fuzzy pass
    best_item: Optional[LRItem] = None
    best_ratio = -1.0
    for item in lr_items:
        norm_name = normalize_lr_name_for_match(item.display_name)
        if not norm_tail or not norm_name:
            continue
        ratio = SequenceMatcher(None, norm_tail, norm_name).ratio()
        if ratio > best_ratio:
            best_ratio = ratio
            best_item = item

    if best_item is None:
        return None, "unmatched", None

    if best_ratio >= 0.90:
        return best_item, "high", float(best_ratio)
    if 0.75 <= best_ratio <= 0.89:
        return best_item, "low", float(best_ratio)
    return None, "unmatched", None


def load_candidates(cur) -> Tuple[List[str], List[str], List[LRItem], List[FTAItem]]:
    cur.execute(
        """
        SELECT DISTINCT output_game_code
        FROM recipes
        WHERE output_game_code IS NOT NULL
          AND btrim(output_game_code) <> ''
        ORDER BY output_game_code
        """
    )
    game_codes = [row[0] for row in cur.fetchall()]

    cur.execute(
        """
        SELECT DISTINCT input_game_code
        FROM recipe_ingredients
        WHERE input_game_code IS NOT NULL
          AND btrim(input_game_code) <> ''
        ORDER BY input_game_code
        """
    )
    ingredient_codes = [row[0] for row in cur.fetchall()]

    cur.execute(
        """
        SELECT id, display_name, lr_category
        FROM lr_items
        ORDER BY id
        """
    )
    lr_items = [LRItem(id=row[0], display_name=row[1] or "", lr_category=row[2]) for row in cur.fetchall()]

    fta_items: List[FTAItem] = []
    if table_exists(cur, "fta_items"):
        cur.execute(
            """
            SELECT id, display_name
            FROM fta_items
            WHERE display_name IS NOT NULL
              AND btrim(display_name) <> ''
            ORDER BY id
            """
        )
        fta_items = [FTAItem(id=row[0], display_name=row[1] or "") for row in cur.fetchall()]

    return game_codes, ingredient_codes, lr_items, fta_items


def insert_rows(cur, rows: Sequence[CanonicalRow]) -> None:
    cur.executemany(
        """
        INSERT INTO canonical_items (
            id,
            display_name,
            game_code,
            lr_item_id,
            fta_item_id,
            match_tier,
            match_score
        ) VALUES (%s, %s, %s, %s, %s, %s, %s)
        """,
        [
            (
                row.slug,
                row.display_name,
                row.game_code,
                row.lr_item_id,
                row.fta_item_id,
                row.match_tier,
                row.match_score,
            )
            for row in rows
        ],
    )


def table_exists(cur, table_name: str) -> bool:
    cur.execute("SELECT to_regclass(%s)", (f"public.{table_name}",))
    row = cur.fetchone()
    return bool(row and row[0])


def discover_lang_files() -> List[str]:
    """Return candidate English lang files from base game + unpacked mods."""
    paths: List[str] = []

    vs_install_dir = os.getenv("VINTAGE_STORY_INSTALL_DIR", "C:/Games/Vintagestory")
    base_en = os.path.join(vs_install_dir, "assets", "game", "lang", "en.json")
    if os.path.exists(base_en):
        paths.append(base_en)

    unpack_root = os.path.join("Cache", "unpack")
    if os.path.isdir(unpack_root):
        for root, _dirs, files in os.walk(unpack_root):
            if "en.json" not in files:
                continue

            normalized_root = root.replace("\\", "/").lower()
            if "/lang" not in normalized_root:
                continue

            paths.append(os.path.join(root, "en.json"))

    return paths


def load_lang_alias_map() -> Dict[str, str]:
    """Build game_code -> display_name map from lang/en.json files."""
    alias_map: Dict[str, str] = {}

    for path in discover_lang_files():
        try:
            with open(path, "r", encoding="utf-8") as f:
                payload = json.load(f)
        except Exception:
            continue

        if not isinstance(payload, dict):
            continue

        for key, value in payload.items():
            if not isinstance(key, str) or not isinstance(value, str):
                continue

            key = key.strip().lower()
            label = value.strip()

            if not label or "{" in label:
                continue

            if key.startswith("item-"):
                tail = key[len("item-") :]
                if not tail or "*" in tail:
                    continue
                alias_map.setdefault(f"item:{tail}", label)
            elif key.startswith("block-"):
                tail = key[len("block-") :]
                if not tail or "*" in tail:
                    continue
                alias_map.setdefault(f"block:{tail}", label)

    return alias_map


def apply_lang_display_name_overrides(rows: Sequence[CanonicalRow], lang_alias_map: Dict[str, str]) -> int:
    """
    Apply lang-file display name overrides for game-code-backed canonical rows.

    Priority policy:
      - exact/high LR display names win (no override)
      - lang overrides game-code-derived names
      - for low tier, preserve LR name if low-tier overlap logic selected LR display
    """
    overrides = 0
    for row in rows:
        game_code = row.game_code
        if not game_code:
            continue

        lang_name = lang_alias_map.get(game_code)
        if not lang_name:
            continue

        tier = (row.match_tier or "").lower()
        if tier in {"exact", "high"}:
            continue

        if tier == "low":
            # Only override low tier when current display_name is still game-code-derived.
            tail = game_code_tail(game_code)
            if row.display_name != humanize_game_tail(tail):
                continue

        if row.display_name == lang_name:
            continue

        row.display_name = lang_name
        overrides += 1

    return overrides


def snapshot_price_overrides(cur) -> List[Tuple[Optional[str], Optional[str], float, Optional[str]]]:
    """Capture manual overrides so canonical rebuild can safely recreate referenced IDs."""
    if not table_exists(cur, "price_overrides"):
        return []

    cur.execute(
        """
        SELECT po.canonical_id, ci.game_code, po.unit_price, po.note
        FROM price_overrides po
        LEFT JOIN canonical_items ci ON ci.id = po.canonical_id
        """
    )
    rows = cur.fetchall()

    # canonical_items rebuild currently deletes rows; clear dependent FK rows first.
    cur.execute("DELETE FROM price_overrides")
    return rows


def restore_price_overrides(cur, snapshots: Sequence[Tuple[Optional[str], Optional[str], float, Optional[str]]]) -> None:
    if not snapshots or not table_exists(cur, "price_overrides"):
        return

    restored = 0
    skipped = 0

    for old_canonical_id, old_game_code, unit_price, note in snapshots:
        new_canonical_id: Optional[str] = None

        if old_game_code:
            normalized_code = normalize_game_code(old_game_code)
            cur.execute(
                "SELECT id FROM canonical_items WHERE game_code = %s LIMIT 1",
                (normalized_code,),
            )
            row = cur.fetchone()
            if row:
                new_canonical_id = row[0]

        if new_canonical_id is None and old_canonical_id:
            cur.execute(
                "SELECT id FROM canonical_items WHERE id = %s LIMIT 1",
                (old_canonical_id,),
            )
            row = cur.fetchone()
            if row:
                new_canonical_id = row[0]

        if new_canonical_id is None:
            skipped += 1
            continue

        cur.execute(
            """
            INSERT INTO price_overrides (canonical_id, unit_price, note)
            VALUES (%s, %s, %s)
            ON CONFLICT (canonical_id)
            DO UPDATE SET unit_price = EXCLUDED.unit_price, note = EXCLUDED.note
            """,
            (new_canonical_id, unit_price, note),
        )
        restored += 1

    print(f"Price overrides restored: {restored}")
    print(f"Price overrides skipped (unmapped): {skipped}")


def ensure_variant_family_columns(cur) -> None:
    """Ensure variant-family columns exist on canonical_items."""
    cur.execute("ALTER TABLE canonical_items ADD COLUMN IF NOT EXISTS variant_family TEXT")
    cur.execute("ALTER TABLE canonical_items ADD COLUMN IF NOT EXISTS variant_material TEXT")


def assign_variant_families(cur) -> int:
    """Populate variant_family/material for metal-suffixed item:<base>-<material> codes."""
    cur.execute(
        """
        SELECT id, game_code
        FROM canonical_items
        WHERE game_code IS NOT NULL
          AND game_code LIKE 'item:%'
        """
    )
    rows = cur.fetchall()

    updates: List[Tuple[str, str, str]] = []
    for canonical_id, game_code in rows:
        tail = game_code_tail(game_code)
        if "-" not in tail:
            continue

        base, material = tail.rsplit("-", 1)
        material = (material or "").lower().strip()
        if not base or material not in METAL_VARIANT_MATERIALS:
            continue

        updates.append((base, material, canonical_id))

    if not updates:
        return 0

    cur.executemany(
        """
        UPDATE canonical_items
        SET variant_family = %s,
            variant_material = %s
        WHERE id = %s
        """,
        updates,
    )
    return len(updates)


def main() -> int:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("[ERROR] DATABASE_URL environment variable is not set.", file=sys.stderr)
        return 1

    try:
        with psycopg2.connect(database_url) as conn:
            with conn.cursor() as cur:
                ensure_variant_family_columns(cur)
                game_codes, ingredient_codes, lr_items, fta_items = load_candidates(cur)
                lang_alias_map = load_lang_alias_map()
                price_override_snapshots = snapshot_price_overrides(cur)

                cur.execute("UPDATE recipe_ingredients SET input_canonical_id = NULL")
                cur.execute("UPDATE recipes SET output_canonical_id = NULL")
                # NOTE: TRUNCATE is blocked while FK constraints reference this table,
                # even when all referencing values are NULL. Use DELETE for safe rebuild.
                cur.execute("DELETE FROM canonical_items")

                rows: List[CanonicalRow] = []
                seen_slugs: Set[str] = set()
                matched_lr_ids: Set[int] = set()

                exact_matches = 0
                suffix_matches = 0
                segment_matches = 0
                contains_matches = 0
                high_matches = 0
                low_matches = 0
                unmatched_game_codes = 0

                # Source A: game-code-driven rows (matched or unmatched)
                processed_game_codes: Set[str] = set()
                for game_code_raw in game_codes:
                    game_code = normalize_game_code(game_code_raw)
                    if not game_code or game_code in processed_game_codes:
                        continue
                    processed_game_codes.add(game_code)

                    tail = game_code_tail(game_code)
                    base_slug = slug_from_game_code(game_code)
                    slug = disambiguate_slug(base_slug, seen_slugs)

                    best_item, tier, score = choose_best_lr_match(tail, lr_items)

                    if tier == "exact" and best_item is not None:
                        exact_matches += 1
                        matched_lr_ids.add(best_item.id)
                        display_name = canonical_display_name_for_match(
                            tier="exact",
                            tail=tail,
                            lr_display_name=best_item.display_name,
                        )
                        rows.append(
                            CanonicalRow(
                                slug=slug,
                                display_name=display_name,
                                game_code=game_code,
                                lr_item_id=best_item.id,
                                fta_item_id=None,
                                match_tier="exact",
                                match_score=1.0,
                            )
                        )
                    elif tier == "suffix" and best_item is not None:
                        suffix_matches += 1
                        matched_lr_ids.add(best_item.id)
                        display_name = canonical_display_name_for_match(
                            tier="exact",
                            tail=tail,
                            lr_display_name=best_item.display_name,
                        )
                        rows.append(
                            CanonicalRow(
                                slug=slug,
                                display_name=display_name,
                                game_code=game_code,
                                lr_item_id=best_item.id,
                                fta_item_id=None,
                                match_tier="exact",
                                match_score=1.0,
                            )
                        )
                    elif tier == "segment" and best_item is not None:
                        segment_matches += 1
                        matched_lr_ids.add(best_item.id)
                        display_name = canonical_display_name_for_match(
                            tier="exact",
                            tail=tail,
                            lr_display_name=best_item.display_name,
                        )
                        rows.append(
                            CanonicalRow(
                                slug=slug,
                                display_name=display_name,
                                game_code=game_code,
                                lr_item_id=best_item.id,
                                fta_item_id=None,
                                match_tier="exact",
                                match_score=1.0,
                            )
                        )
                    elif tier == "contains" and best_item is not None:
                        contains_matches += 1
                        matched_lr_ids.add(best_item.id)
                        display_name = canonical_display_name_for_match(
                            tier="exact",
                            tail=tail,
                            lr_display_name=best_item.display_name,
                        )
                        rows.append(
                            CanonicalRow(
                                slug=slug,
                                display_name=display_name,
                                game_code=game_code,
                                lr_item_id=best_item.id,
                                fta_item_id=None,
                                match_tier="exact",
                                match_score=1.0,
                            )
                        )
                    elif tier == "high" and best_item is not None and score is not None:
                        high_matches += 1
                        matched_lr_ids.add(best_item.id)
                        display_name = canonical_display_name_for_match(
                            tier="high",
                            tail=tail,
                            lr_display_name=best_item.display_name,
                        )
                        rows.append(
                            CanonicalRow(
                                slug=slug,
                                display_name=display_name,
                                game_code=game_code,
                                lr_item_id=best_item.id,
                                fta_item_id=None,
                                match_tier="high",
                                match_score=score,
                            )
                        )
                    elif tier == "low" and best_item is not None and score is not None:
                        low_matches += 1
                        matched_lr_ids.add(best_item.id)
                        display_name = canonical_display_name_for_match(
                            tier="low",
                            tail=tail,
                            lr_display_name=best_item.display_name,
                        )
                        rows.append(
                            CanonicalRow(
                                slug=slug,
                                display_name=display_name,
                                game_code=game_code,
                                lr_item_id=best_item.id,
                                fta_item_id=None,
                                match_tier="low",
                                match_score=score,
                            )
                        )
                    else:
                        unmatched_game_codes += 1
                        rows.append(
                            CanonicalRow(
                                slug=slug,
                                display_name=humanize_game_tail(tail),
                                game_code=game_code,
                                lr_item_id=None,
                                fta_item_id=None,
                                match_tier="unmatched",
                                match_score=None,
                            )
                        )

                # Source B: LR-only rows (not matched by any game code)
                lr_only_items = 0
                for item in lr_items:
                    if item.id in matched_lr_ids:
                        continue

                    base_slug = slug_from_display_name(item.display_name)
                    if not base_slug:
                        base_slug = f"lr_item_{item.id}"
                    slug = disambiguate_slug(base_slug, seen_slugs)

                    rows.append(
                        CanonicalRow(
                            slug=slug,
                            display_name=strip_admin_note_parentheticals(item.display_name) or f"LR Item {item.id}",
                            game_code=None,
                            lr_item_id=item.id,
                            fta_item_id=None,
                            match_tier=None,
                            match_score=None,
                        )
                    )
                    lr_only_items += 1

                # Source C: ingredient-only game codes not already represented by Source A/B canonical rows.
                ingredient_only_items = 0
                existing_canonical_codes: Set[str] = {
                    row.game_code for row in rows if row.game_code is not None
                }

                for ingredient_code_raw in ingredient_codes:
                    # Skip templates and mod schematic-like codes.
                    if "{" in ingredient_code_raw:
                        continue

                    ingredient_code = normalize_game_code(ingredient_code_raw)
                    if not ingredient_code:
                        continue
                    if ingredient_code in existing_canonical_codes:
                        continue

                    existing_canonical_codes.add(ingredient_code)
                    ingredient_only_items += 1

                    tail = game_code_tail(ingredient_code)
                    base_slug = slug_from_game_code(ingredient_code)
                    slug = disambiguate_slug(base_slug, seen_slugs)

                    best_item, tier, score = choose_best_lr_match(tail, lr_items)

                    if tier == "exact" and best_item is not None:
                        exact_matches += 1
                        matched_lr_ids.add(best_item.id)
                        display_name = canonical_display_name_for_match(
                            tier="exact",
                            tail=tail,
                            lr_display_name=best_item.display_name,
                        )
                        rows.append(
                            CanonicalRow(
                                slug=slug,
                                display_name=display_name,
                                game_code=ingredient_code,
                                lr_item_id=best_item.id,
                                fta_item_id=None,
                                match_tier="exact",
                                match_score=1.0,
                            )
                        )
                    elif tier == "suffix" and best_item is not None:
                        suffix_matches += 1
                        matched_lr_ids.add(best_item.id)
                        display_name = canonical_display_name_for_match(
                            tier="exact",
                            tail=tail,
                            lr_display_name=best_item.display_name,
                        )
                        rows.append(
                            CanonicalRow(
                                slug=slug,
                                display_name=display_name,
                                game_code=ingredient_code,
                                lr_item_id=best_item.id,
                                fta_item_id=None,
                                match_tier="exact",
                                match_score=1.0,
                            )
                        )
                    elif tier == "segment" and best_item is not None:
                        segment_matches += 1
                        matched_lr_ids.add(best_item.id)
                        display_name = canonical_display_name_for_match(
                            tier="exact",
                            tail=tail,
                            lr_display_name=best_item.display_name,
                        )
                        rows.append(
                            CanonicalRow(
                                slug=slug,
                                display_name=display_name,
                                game_code=ingredient_code,
                                lr_item_id=best_item.id,
                                fta_item_id=None,
                                match_tier="exact",
                                match_score=1.0,
                            )
                        )
                    elif tier == "contains" and best_item is not None:
                        contains_matches += 1
                        matched_lr_ids.add(best_item.id)
                        display_name = canonical_display_name_for_match(
                            tier="exact",
                            tail=tail,
                            lr_display_name=best_item.display_name,
                        )
                        rows.append(
                            CanonicalRow(
                                slug=slug,
                                display_name=display_name,
                                game_code=ingredient_code,
                                lr_item_id=best_item.id,
                                fta_item_id=None,
                                match_tier="exact",
                                match_score=1.0,
                            )
                        )
                    elif tier == "high" and best_item is not None and score is not None:
                        high_matches += 1
                        matched_lr_ids.add(best_item.id)
                        display_name = canonical_display_name_for_match(
                            tier="high",
                            tail=tail,
                            lr_display_name=best_item.display_name,
                        )
                        rows.append(
                            CanonicalRow(
                                slug=slug,
                                display_name=display_name,
                                game_code=ingredient_code,
                                lr_item_id=best_item.id,
                                fta_item_id=None,
                                match_tier="high",
                                match_score=score,
                            )
                        )
                    elif tier == "low" and best_item is not None and score is not None:
                        low_matches += 1
                        matched_lr_ids.add(best_item.id)
                        display_name = canonical_display_name_for_match(
                            tier="low",
                            tail=tail,
                            lr_display_name=best_item.display_name,
                        )
                        rows.append(
                            CanonicalRow(
                                slug=slug,
                                display_name=display_name,
                                game_code=ingredient_code,
                                lr_item_id=best_item.id,
                                fta_item_id=None,
                                match_tier="low",
                                match_score=score,
                            )
                        )
                    else:
                        unmatched_game_codes += 1
                        rows.append(
                            CanonicalRow(
                                slug=slug,
                                display_name=humanize_game_tail(tail),
                                game_code=ingredient_code,
                                lr_item_id=None,
                                fta_item_id=None,
                                match_tier="unmatched",
                                match_score=None,
                            )
                        )

                # Source D: FTA linking pass (match FTA display names to existing canonical display names).
                fta_exact_links = 0
                fta_trigram_links = 0
                fta_only_items = 0

                # Pre-index canonical rows for faster FTA linking.
                canonical_name_norms: List[str] = [
                    normalize_name_for_linking(row.display_name) for row in rows
                ]
                canonical_trigrams: List[Set[str]] = [trigram_set(row.display_name) for row in rows]
                trigram_to_indexes: Dict[str, Set[int]] = {}
                exact_name_to_indexes: Dict[str, List[int]] = {}
                for idx, name_norm in enumerate(canonical_name_norms):
                    if not name_norm:
                        continue
                    exact_name_to_indexes.setdefault(name_norm, []).append(idx)
                    for tri in canonical_trigrams[idx]:
                        trigram_to_indexes.setdefault(tri, set()).add(idx)

                for fta_item in fta_items:
                    fta_name_norm = normalize_name_for_linking(fta_item.display_name)
                    if not fta_name_norm:
                        continue

                    matched_index: Optional[int] = None

                    # Exact display_name match first.
                    for idx in exact_name_to_indexes.get(fta_name_norm, []):
                        if rows[idx].fta_item_id is not None:
                            continue
                        matched_index = idx
                        break

                    # Trigram similarity fallback (0.5+).
                    if matched_index is None:
                        best_idx: Optional[int] = None
                        best_score = 0.0
                        fta_trigrams = trigram_set(fta_item.display_name)

                        candidate_indexes: Set[int] = set()
                        for tri in fta_trigrams:
                            candidate_indexes.update(trigram_to_indexes.get(tri, set()))

                        for idx in candidate_indexes:
                            row = rows[idx]
                            if row.fta_item_id is not None:
                                continue
                            score = trigram_similarity_sets(fta_trigrams, canonical_trigrams[idx])
                            if score > best_score:
                                best_score = score
                                best_idx = idx

                        if best_idx is not None and best_score >= 0.5:
                            matched_index = best_idx
                            fta_trigram_links += 1

                    if matched_index is not None:
                        rows[matched_index].fta_item_id = fta_item.id
                        if normalize_name_for_linking(rows[matched_index].display_name) == fta_name_norm:
                            fta_exact_links += 1
                        continue

                    # FTA-only: create new canonical when no match exists.
                    base_slug = slug_from_display_name(fta_item.display_name) or f"fta_item_{fta_item.id}"
                    slug = disambiguate_slug(base_slug, seen_slugs)
                    rows.append(
                        CanonicalRow(
                            slug=slug,
                            display_name=fta_item.display_name,
                            game_code=None,
                            lr_item_id=None,
                            fta_item_id=fta_item.id,
                            match_tier=None,
                            match_score=None,
                        )
                    )
                    new_idx = len(rows) - 1
                    canonical_name_norms.append(fta_name_norm)
                    new_trigrams = trigram_set(fta_item.display_name)
                    canonical_trigrams.append(new_trigrams)
                    exact_name_to_indexes.setdefault(fta_name_norm, []).append(new_idx)
                    for tri in new_trigrams:
                        trigram_to_indexes.setdefault(tri, set()).add(new_idx)
                    fta_only_items += 1

                lang_overrides = apply_lang_display_name_overrides(rows, lang_alias_map)

                insert_rows(cur, rows)
                variant_family_count = assign_variant_families(cur)
                restore_price_overrides(cur, price_override_snapshots)

                print(f"Total canonical items created: {len(rows)}")
                print(f"  Exact matches: {exact_matches}")
                print(f"  Suffix matches: {suffix_matches}")
                print(f"  Any-segment matches: {segment_matches}")
                print(f"  LR-name-contained matches: {contains_matches}")
                print(f"  High fuzzy matches: {high_matches}")
                print(f"  Low fuzzy matches: {low_matches}")
                print(f"  Unmatched game codes: {unmatched_game_codes}")
                print(f"  LR-only items: {lr_only_items}")
                print(f"  Ingredient-only items: {ingredient_only_items}")
                print(f"  FTA exact display-name links: {fta_exact_links}")
                print(f"  FTA trigram links: {fta_trigram_links}")
                print(f"  FTA-only items: {fta_only_items}")
                print(f"  Lang-derived game-code labels loaded: {len(lang_alias_map)}")
                print(f"  Lang display_name overrides applied: {lang_overrides}")
                print(f"  Variant-family rows assigned: {variant_family_count}")

                cur.execute("SELECT COUNT(*) FROM recipes WHERE output_canonical_id IS NULL")
                recipe_unlinked_count_row = cur.fetchone()
                recipe_unlinked_count = int(recipe_unlinked_count_row[0]) if recipe_unlinked_count_row else 0
                if recipe_unlinked_count > 100:
                    print(
                        f"WARNING: Recipe linkage appears broken - {recipe_unlinked_count} recipes have no canonical link. "
                        "Run: python scripts/link_recipes.py"
                    )

                print("[OK] Done.")

    except Exception as exc:
        print(f"[ERROR] Failed to build canonical_items: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
