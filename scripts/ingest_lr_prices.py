#!/usr/bin/env python3
"""
Ingest Lost Realm economy price sheets into lr_items.

Reads DATABASE_URL from environment and upserts rows from the three
published Google Sheets CSV sources:
  - industrial_goods
  - agricultural_goods
  - artisanal_goods
"""

import csv
import io
import os
import re
import sys
import urllib.request
from decimal import Decimal, InvalidOperation
from typing import Dict, Iterable, List, Optional, Tuple

import psycopg2
from dotenv import load_dotenv


load_dotenv()


SOURCES: List[Tuple[str, str]] = [
    (
        "industrial_goods",
        "https://docs.google.com/spreadsheets/d/e/2PACX-1vR73BLsil5C-xCp_P-_VCMWhSRliwou5FWfyhMmAbOTc4a91OcwpkxC0J_R0tdmuYilv8_OVWtJqtlj/pub?gid=1468550541&single=true&output=csv",
    ),
    (
        "agricultural_goods",
        "https://docs.google.com/spreadsheets/d/e/2PACX-1vR73BLsil5C-xCp_P-_VCMWhSRliwou5FWfyhMmAbOTc4a91OcwpkxC0J_R0tdmuYilv8_OVWtJqtlj/pub?gid=403466432&single=true&output=csv",
    ),
    (
        "artisanal_goods",
        "https://docs.google.com/spreadsheets/d/e/2PACX-1vR73BLsil5C-xCp_P-_VCMWhSRliwou5FWfyhMmAbOTc4a91OcwpkxC0J_R0tdmuYilv8_OVWtJqtlj/pub?gid=393020471&single=true&output=csv",
    ),
    (
        "settlement_specialization",
        "https://docs.google.com/spreadsheets/d/e/2PACX-1vR73BLsil5C-xCp_P-_VCMWhSRliwou5FWfyhMmAbOTc4a91OcwpkxC0J_R0tdmuYilv8_OVWtJqtlj/pub?gid=174237392&single=true&output=csv",
    ),
]


def fetch_csv(url: str) -> str:
    with urllib.request.urlopen(url, timeout=30) as response:
        return response.read().decode("utf-8-sig")


def save_csv_to_disk(category: str, csv_text: str) -> str:
    raw_dir = os.path.join("data", "raw")
    os.makedirs(raw_dir, exist_ok=True)

    output_path = os.path.join(raw_dir, f"{category}.csv")
    with open(output_path, "w", encoding="utf-8", newline="") as f:
        f.write(csv_text)

    return output_path


def normalize_cell(value: Optional[str]) -> str:
    return (value or "").strip()


def parse_numeric(value: Optional[str]) -> Optional[Decimal]:
    text = normalize_cell(value)
    if text in ("", "-"):
        return None

    text = text.replace(",", "")
    try:
        return Decimal(text)
    except InvalidOperation as exc:
        raise ValueError(f"Invalid numeric value: {value!r}") from exc


def parse_numeric_loose(value: Optional[str]) -> Optional[Decimal]:
    """Parse numeric values but tolerate spreadsheet error tokens.

    Used for price columns so malformed trend/formula leftovers (e.g. #VALUE!)
    do not cause an entire item row to be skipped.
    """
    try:
        return parse_numeric(value)
    except ValueError:
        return None


def parse_int(value: Optional[str]) -> int:
    text = normalize_cell(value)
    if text == "":
        raise ValueError("Count is blank")

    text = text.replace(",", "")
    match = re.match(r"^(\d+)", text)
    if not match:
        raise ValueError(f"Invalid integer value for count: {value!r}")

    return int(match.group(1))


def get_col(row: List[str], idx: int) -> str:
    if idx < len(row):
        return normalize_cell(row[idx])
    return ""


ITEM_ID_RE = re.compile(r"^[A-Z]{2,}\d+$")


STANDARD_PRICE_HEADER_LABELS: Dict[str, str] = {
    "current_price": "current price",
    "industrial_town": "industrial town",
    "industrial_city": "industrial city",
    "market_town": "market town",
    "market_city": "market city",
    "religious_town": "religious town",
    "temple_city": "temple city",
}


def detect_standard_price_col_map(category: str, csv_text: str) -> Optional[Dict[str, int]]:
    """Detect non-tiered price column positions from header rows.

    Uses the first section header containing exact ``Current Price`` as canonical,
    then verifies repeated section headers are consistent. If required headers are
    missing or inconsistent between sections, returns None so ingestion can skip
    this category safely instead of ingesting misaligned values.
    """

    reader = csv.reader(io.StringIO(csv_text))
    canonical_map: Optional[Dict[str, int]] = None
    canonical_headers: Optional[List[str]] = None
    canonical_line: Optional[int] = None

    for line_no, row in enumerate(reader, start=1):
        normalized = [normalize_cell(cell) for cell in row]
        lowered = [cell.lower() for cell in normalized]

        if "current price" not in lowered:
            continue

        row_map: Dict[str, int] = {}
        missing: List[str] = []

        for key, label in STANDARD_PRICE_HEADER_LABELS.items():
            if label not in lowered:
                missing.append(label)
            else:
                row_map[key] = lowered.index(label)

        if missing:
            print(
                (
                    f"  [WARN] {category}: header row at line {line_no} is missing required "
                    f"non-tiered price headers {missing!r}; headers={normalized!r}. "
                    "Skipping category to avoid misaligned ingestion."
                ),
                file=sys.stderr,
            )
            return None

        if canonical_map is None:
            canonical_map = row_map
            canonical_headers = normalized
            canonical_line = line_no
            continue

        if row_map != canonical_map:
            print(
                (
                    f"  [WARN] {category}: inconsistent section header layout at line {line_no}; "
                    f"detected map={row_map}, canonical map={canonical_map} (line {canonical_line}). "
                    f"Section headers={normalized!r}, canonical headers={canonical_headers!r}. "
                    "Skipping category to avoid misaligned ingestion."
                ),
                file=sys.stderr,
            )
            return None

    if canonical_map is None:
        print(
            (
                f"  [WARN] {category}: could not find any non-tiered header row containing "
                "exact 'Current Price'; positional parsing may be incorrect. "
                "Skipping category to avoid misaligned ingestion."
            ),
            file=sys.stderr,
        )
        return None

    return canonical_map


def extract_sub_category(row: List[str]) -> Optional[str]:
    """Best-effort extraction of section labels from mixed-format CSV rows."""
    second_col = get_col(row, 1)
    if not second_col:
        return None

    upper = second_col.upper()
    if "ITEM ID" in upper:
        return None
    if upper in {"INDUSTRIAL GOODS", "AGRICULTURAL GOODS", "ARTISANAL GOODS"}:
        return None
    if second_col.startswith("Notes:"):
        return None

    return second_col.strip(" ,") or None


def parse_standard_row(
    row: List[str],
    category: str,
    sub_category: Optional[str],
    standard_col_map: Dict[str, int],
) -> Dict[str, object]:
    """Parse industrial/agricultural (and non-tier artisanal-style) rows."""
    has_quality_tiers = any(
        parse_numeric_loose(get_col(row, idx)) is not None
        for idx in (17, 28, 39)
    )

    if has_quality_tiers:
        # Some sheets now use the same quality-tier block layout as artisanal goods.
        # Common price remains base_value/count (handled downstream via base_value),
        # while current + settlement columns here represent uncommon tier values.
        return {
            "item_id": get_col(row, 0).upper(),
            "display_name": get_col(row, 1),
            "lr_category": category,
            "lr_sub_category": sub_category,
            "count": parse_int(get_col(row, 2)),
            "base_value": parse_numeric_loose(get_col(row, 3)),
            "price_current": parse_numeric_loose(get_col(row, 6)),
            "price_industrial_town": parse_numeric_loose(get_col(row, 7)),
            "price_industrial_city": parse_numeric_loose(get_col(row, 8)),
            "price_market_town": parse_numeric_loose(get_col(row, 9)),
            "price_market_city": parse_numeric_loose(get_col(row, 10)),
            "price_religious_town": parse_numeric_loose(get_col(row, 11)),
            "price_temple_city": parse_numeric_loose(get_col(row, 12)),
            "has_quality_tiers": True,
            "price_uncommon_current": parse_numeric_loose(get_col(row, 6)),
            "price_uncommon_industrial_town": parse_numeric_loose(get_col(row, 7)),
            "price_uncommon_industrial_city": parse_numeric_loose(get_col(row, 8)),
            "price_uncommon_market_town": parse_numeric_loose(get_col(row, 9)),
            "price_uncommon_market_city": parse_numeric_loose(get_col(row, 10)),
            "price_uncommon_religious_town": parse_numeric_loose(get_col(row, 11)),
            "price_uncommon_temple_city": parse_numeric_loose(get_col(row, 12)),
            "price_rare_current": parse_numeric_loose(get_col(row, 17)),
            "price_rare_industrial_town": parse_numeric_loose(get_col(row, 18)),
            "price_rare_industrial_city": parse_numeric_loose(get_col(row, 19)),
            "price_rare_market_town": parse_numeric_loose(get_col(row, 20)),
            "price_rare_market_city": parse_numeric_loose(get_col(row, 21)),
            "price_rare_religious_town": parse_numeric_loose(get_col(row, 22)),
            "price_rare_temple_city": parse_numeric_loose(get_col(row, 23)),
            "price_epic_current": parse_numeric_loose(get_col(row, 28)),
            "price_epic_industrial_town": parse_numeric_loose(get_col(row, 29)),
            "price_epic_industrial_city": parse_numeric_loose(get_col(row, 30)),
            "price_epic_market_town": parse_numeric_loose(get_col(row, 31)),
            "price_epic_market_city": parse_numeric_loose(get_col(row, 32)),
            "price_epic_religious_town": parse_numeric_loose(get_col(row, 33)),
            "price_epic_temple_city": parse_numeric_loose(get_col(row, 34)),
            "price_legendary_current": parse_numeric_loose(get_col(row, 39)),
            "price_legendary_industrial_town": parse_numeric_loose(get_col(row, 40)),
            "price_legendary_industrial_city": parse_numeric_loose(get_col(row, 41)),
            "price_legendary_market_town": parse_numeric_loose(get_col(row, 42)),
            "price_legendary_market_city": parse_numeric_loose(get_col(row, 43)),
            "price_legendary_religious_town": parse_numeric_loose(get_col(row, 44)),
            "price_legendary_temple_city": parse_numeric_loose(get_col(row, 45)),
        }

    return {
        "item_id": get_col(row, 0).upper(),
        "display_name": get_col(row, 1),
        "lr_category": category,
        "lr_sub_category": sub_category,
        "count": parse_int(get_col(row, 2)),
        "base_value": parse_numeric_loose(get_col(row, 3)),
        # Non-tiered layout is detected from headers per file/category.
        "price_current": parse_numeric_loose(get_col(row, standard_col_map["current_price"])),
        "price_industrial_town": parse_numeric_loose(get_col(row, standard_col_map["industrial_town"])),
        "price_industrial_city": parse_numeric_loose(get_col(row, standard_col_map["industrial_city"])),
        "price_market_town": parse_numeric_loose(get_col(row, standard_col_map["market_town"])),
        "price_market_city": parse_numeric_loose(get_col(row, standard_col_map["market_city"])),
        "price_religious_town": parse_numeric_loose(get_col(row, standard_col_map["religious_town"])),
        "price_temple_city": parse_numeric_loose(get_col(row, standard_col_map["temple_city"])),
        "has_quality_tiers": False,
        "price_uncommon_current": None,
        "price_uncommon_industrial_town": None,
        "price_uncommon_industrial_city": None,
        "price_uncommon_market_town": None,
        "price_uncommon_market_city": None,
        "price_uncommon_religious_town": None,
        "price_uncommon_temple_city": None,
        "price_rare_current": None,
        "price_rare_industrial_town": None,
        "price_rare_industrial_city": None,
        "price_rare_market_town": None,
        "price_rare_market_city": None,
        "price_rare_religious_town": None,
        "price_rare_temple_city": None,
        "price_epic_current": None,
        "price_epic_industrial_town": None,
        "price_epic_industrial_city": None,
        "price_epic_market_town": None,
        "price_epic_market_city": None,
        "price_epic_religious_town": None,
        "price_epic_temple_city": None,
        "price_legendary_current": None,
        "price_legendary_industrial_town": None,
        "price_legendary_industrial_city": None,
        "price_legendary_market_town": None,
        "price_legendary_market_city": None,
        "price_legendary_religious_town": None,
        "price_legendary_temple_city": None,
    }


def parse_artisanal_row(row: List[str], category: str, sub_category: Optional[str]) -> Dict[str, object]:
    """Parse artisanal rows, including quality-tiered blocks.

    Tiered blocks have uncommon/rare/epic/legendary current + settlement columns.
    Non-tiered artisanal blocks (e.g. transport, alcohol, medicinal) keep the
    standard current+settlement shape.
    """
    item_id = get_col(row, 0).upper()
    count = parse_int(get_col(row, 2))
    base_value = parse_numeric_loose(get_col(row, 3))

    has_quality_tiers = any(
        parse_numeric_loose(get_col(row, idx)) is not None
        for idx in (17, 28, 39)
    )

    if has_quality_tiers:
        # Uncommon block starts at col 6 (current), settlements 7..12
        price_current = parse_numeric_loose(get_col(row, 6))
        price_industrial_town = parse_numeric_loose(get_col(row, 7))
        price_industrial_city = parse_numeric_loose(get_col(row, 8))
        price_market_town = parse_numeric_loose(get_col(row, 9))
        price_market_city = parse_numeric_loose(get_col(row, 10))
        price_religious_town = parse_numeric_loose(get_col(row, 11))
        price_temple_city = parse_numeric_loose(get_col(row, 12))

        return {
            "item_id": item_id,
            "display_name": get_col(row, 1),
            "lr_category": category,
            "lr_sub_category": sub_category,
            "count": count,
            "base_value": base_value,
            "price_current": price_current,
            "price_industrial_town": price_industrial_town,
            "price_industrial_city": price_industrial_city,
            "price_market_town": price_market_town,
            "price_market_city": price_market_city,
            "price_religious_town": price_religious_town,
            "price_temple_city": price_temple_city,
            "has_quality_tiers": True,
            "price_uncommon_current": parse_numeric_loose(get_col(row, 6)),
            "price_uncommon_industrial_town": parse_numeric_loose(get_col(row, 7)),
            "price_uncommon_industrial_city": parse_numeric_loose(get_col(row, 8)),
            "price_uncommon_market_town": parse_numeric_loose(get_col(row, 9)),
            "price_uncommon_market_city": parse_numeric_loose(get_col(row, 10)),
            "price_uncommon_religious_town": parse_numeric_loose(get_col(row, 11)),
            "price_uncommon_temple_city": parse_numeric_loose(get_col(row, 12)),
            "price_rare_current": parse_numeric_loose(get_col(row, 17)),
            "price_rare_industrial_town": parse_numeric_loose(get_col(row, 18)),
            "price_rare_industrial_city": parse_numeric_loose(get_col(row, 19)),
            "price_rare_market_town": parse_numeric_loose(get_col(row, 20)),
            "price_rare_market_city": parse_numeric_loose(get_col(row, 21)),
            "price_rare_religious_town": parse_numeric_loose(get_col(row, 22)),
            "price_rare_temple_city": parse_numeric_loose(get_col(row, 23)),
            "price_epic_current": parse_numeric_loose(get_col(row, 28)),
            "price_epic_industrial_town": parse_numeric_loose(get_col(row, 29)),
            "price_epic_industrial_city": parse_numeric_loose(get_col(row, 30)),
            "price_epic_market_town": parse_numeric_loose(get_col(row, 31)),
            "price_epic_market_city": parse_numeric_loose(get_col(row, 32)),
            "price_epic_religious_town": parse_numeric_loose(get_col(row, 33)),
            "price_epic_temple_city": parse_numeric_loose(get_col(row, 34)),
            "price_legendary_current": parse_numeric_loose(get_col(row, 39)),
            "price_legendary_industrial_town": parse_numeric_loose(get_col(row, 40)),
            "price_legendary_industrial_city": parse_numeric_loose(get_col(row, 41)),
            "price_legendary_market_town": parse_numeric_loose(get_col(row, 42)),
            "price_legendary_market_city": parse_numeric_loose(get_col(row, 43)),
            "price_legendary_religious_town": parse_numeric_loose(get_col(row, 44)),
            "price_legendary_temple_city": parse_numeric_loose(get_col(row, 45)),
        }

    # Non-tiered artisanal rows (e.g. transport/alcohol/medicinal/crafting goods)
    return {
        "item_id": item_id,
        "display_name": get_col(row, 1),
        "lr_category": category,
        "lr_sub_category": sub_category,
        "count": count,
        "base_value": base_value,
        "price_current": parse_numeric_loose(get_col(row, 6)),
        "price_industrial_town": parse_numeric_loose(get_col(row, 7)),
        "price_industrial_city": parse_numeric_loose(get_col(row, 8)),
        "price_market_town": parse_numeric_loose(get_col(row, 9)),
        "price_market_city": parse_numeric_loose(get_col(row, 10)),
        "price_religious_town": parse_numeric_loose(get_col(row, 11)),
        "price_temple_city": parse_numeric_loose(get_col(row, 12)),
        "has_quality_tiers": False,
        "price_uncommon_current": None,
        "price_uncommon_industrial_town": None,
        "price_uncommon_industrial_city": None,
        "price_uncommon_market_town": None,
        "price_uncommon_market_city": None,
        "price_uncommon_religious_town": None,
        "price_uncommon_temple_city": None,
        "price_rare_current": None,
        "price_rare_industrial_town": None,
        "price_rare_industrial_city": None,
        "price_rare_market_town": None,
        "price_rare_market_city": None,
        "price_rare_religious_town": None,
        "price_rare_temple_city": None,
        "price_epic_current": None,
        "price_epic_industrial_town": None,
        "price_epic_industrial_city": None,
        "price_epic_market_town": None,
        "price_epic_market_city": None,
        "price_epic_religious_town": None,
        "price_epic_temple_city": None,
        "price_legendary_current": None,
        "price_legendary_industrial_town": None,
        "price_legendary_industrial_city": None,
        "price_legendary_market_town": None,
        "price_legendary_market_city": None,
        "price_legendary_religious_town": None,
        "price_legendary_temple_city": None,
    }


def parse_rows(csv_text: str, category: str) -> Tuple[List[Dict[str, object]], int]:
    """
    Parse rows from one CSV.

    Returns:
      (parsed_rows, skipped_rows)
    """
    standard_col_map: Optional[Dict[str, int]] = None
    if category != "artisanal_goods":
        standard_col_map = detect_standard_price_col_map(category, csv_text)
        if standard_col_map is None:
            total_rows = len(list(csv.reader(io.StringIO(csv_text))))
            return [], total_rows

    reader = csv.reader(io.StringIO(csv_text))
    parsed: List[Dict[str, object]] = []
    skipped = 0
    skipped_examples: List[Tuple[int, str, List[str]]] = []
    current_sub_category: Optional[str] = None

    for line_no, row in enumerate(reader, start=1):
        # Strict positional mapping: only rows with a canonical item ID in col0
        # are considered data rows. Header text/content is ignored.
        item_id_cell = get_col(row, 0).upper()
        if not ITEM_ID_RE.match(item_id_cell):
            maybe_sub_category = extract_sub_category(row)
            if maybe_sub_category:
                current_sub_category = maybe_sub_category

            skipped += 1
            if category == "agricultural_goods" and len(skipped_examples) < 5:
                skipped_examples.append((line_no, "non_canonical_item_id", row.copy()))
            continue

        try:
            if category == "artisanal_goods":
                parsed.append(parse_artisanal_row(row, category, current_sub_category))
            else:
                parsed.append(parse_standard_row(row, category, current_sub_category, standard_col_map))
        except ValueError as err:
            skipped += 1
            print(
                f"  [WARN] Skipping malformed row ({category}, line {line_no}): {err}",
                file=sys.stderr,
            )
            if category == "agricultural_goods" and len(skipped_examples) < 5:
                skipped_examples.append((line_no, f"malformed: {err}", row.copy()))

    if category == "agricultural_goods" and skipped_examples:
        print(
            "  [DEBUG] First 5 skipped rows for agricultural_goods (raw columns):",
            file=sys.stderr,
        )
        for ex_line_no, reason, raw_row in skipped_examples:
            print(
                f"    line {ex_line_no} [{reason}]: {raw_row!r}",
                file=sys.stderr,
            )

    return parsed, skipped


UPSERT_SQL = """
INSERT INTO lr_items (
    item_id,
    display_name,
    lr_category,
    lr_sub_category,
    count,
    base_value,
    price_current,
    price_industrial_town,
    price_industrial_city,
    price_market_town,
    price_market_city,
    price_religious_town,
    price_temple_city,
    has_quality_tiers,
    price_uncommon_current,
    price_uncommon_industrial_town,
    price_uncommon_industrial_city,
    price_uncommon_market_town,
    price_uncommon_market_city,
    price_uncommon_religious_town,
    price_uncommon_temple_city,
    price_rare_current,
    price_rare_industrial_town,
    price_rare_industrial_city,
    price_rare_market_town,
    price_rare_market_city,
    price_rare_religious_town,
    price_rare_temple_city,
    price_epic_current,
    price_epic_industrial_town,
    price_epic_industrial_city,
    price_epic_market_town,
    price_epic_market_city,
    price_epic_religious_town,
    price_epic_temple_city,
    price_legendary_current,
    price_legendary_industrial_town,
    price_legendary_industrial_city,
    price_legendary_market_town,
    price_legendary_market_city,
    price_legendary_religious_town,
    price_legendary_temple_city
) VALUES (
    %(item_id)s,
    %(display_name)s,
    %(lr_category)s,
    %(lr_sub_category)s,
    %(count)s,
    %(base_value)s,
    %(price_current)s,
    %(price_industrial_town)s,
    %(price_industrial_city)s,
    %(price_market_town)s,
    %(price_market_city)s,
    %(price_religious_town)s,
    %(price_temple_city)s,
    %(has_quality_tiers)s,
    %(price_uncommon_current)s,
    %(price_uncommon_industrial_town)s,
    %(price_uncommon_industrial_city)s,
    %(price_uncommon_market_town)s,
    %(price_uncommon_market_city)s,
    %(price_uncommon_religious_town)s,
    %(price_uncommon_temple_city)s,
    %(price_rare_current)s,
    %(price_rare_industrial_town)s,
    %(price_rare_industrial_city)s,
    %(price_rare_market_town)s,
    %(price_rare_market_city)s,
    %(price_rare_religious_town)s,
    %(price_rare_temple_city)s,
    %(price_epic_current)s,
    %(price_epic_industrial_town)s,
    %(price_epic_industrial_city)s,
    %(price_epic_market_town)s,
    %(price_epic_market_city)s,
    %(price_epic_religious_town)s,
    %(price_epic_temple_city)s,
    %(price_legendary_current)s,
    %(price_legendary_industrial_town)s,
    %(price_legendary_industrial_city)s,
    %(price_legendary_market_town)s,
    %(price_legendary_market_city)s,
    %(price_legendary_religious_town)s,
    %(price_legendary_temple_city)s
)
ON CONFLICT (item_id) DO UPDATE
SET
    display_name = EXCLUDED.display_name,
    lr_category = EXCLUDED.lr_category,
    lr_sub_category = EXCLUDED.lr_sub_category,
    count = EXCLUDED.count,
    base_value = EXCLUDED.base_value,
    price_current = EXCLUDED.price_current,
    price_industrial_town = EXCLUDED.price_industrial_town,
    price_industrial_city = EXCLUDED.price_industrial_city,
    price_market_town = EXCLUDED.price_market_town,
    price_market_city = EXCLUDED.price_market_city,
    price_religious_town = EXCLUDED.price_religious_town,
    price_temple_city = EXCLUDED.price_temple_city,
    has_quality_tiers = EXCLUDED.has_quality_tiers,
    price_uncommon_current = EXCLUDED.price_uncommon_current,
    price_uncommon_industrial_town = EXCLUDED.price_uncommon_industrial_town,
    price_uncommon_industrial_city = EXCLUDED.price_uncommon_industrial_city,
    price_uncommon_market_town = EXCLUDED.price_uncommon_market_town,
    price_uncommon_market_city = EXCLUDED.price_uncommon_market_city,
    price_uncommon_religious_town = EXCLUDED.price_uncommon_religious_town,
    price_uncommon_temple_city = EXCLUDED.price_uncommon_temple_city,
    price_rare_current = EXCLUDED.price_rare_current,
    price_rare_industrial_town = EXCLUDED.price_rare_industrial_town,
    price_rare_industrial_city = EXCLUDED.price_rare_industrial_city,
    price_rare_market_town = EXCLUDED.price_rare_market_town,
    price_rare_market_city = EXCLUDED.price_rare_market_city,
    price_rare_religious_town = EXCLUDED.price_rare_religious_town,
    price_rare_temple_city = EXCLUDED.price_rare_temple_city,
    price_epic_current = EXCLUDED.price_epic_current,
    price_epic_industrial_town = EXCLUDED.price_epic_industrial_town,
    price_epic_industrial_city = EXCLUDED.price_epic_industrial_city,
    price_epic_market_town = EXCLUDED.price_epic_market_town,
    price_epic_market_city = EXCLUDED.price_epic_market_city,
    price_epic_religious_town = EXCLUDED.price_epic_religious_town,
    price_epic_temple_city = EXCLUDED.price_epic_temple_city,
    price_legendary_current = EXCLUDED.price_legendary_current,
    price_legendary_industrial_town = EXCLUDED.price_legendary_industrial_town,
    price_legendary_industrial_city = EXCLUDED.price_legendary_industrial_city,
    price_legendary_market_town = EXCLUDED.price_legendary_market_town,
    price_legendary_market_city = EXCLUDED.price_legendary_market_city,
    price_legendary_religious_town = EXCLUDED.price_legendary_religious_town,
    price_legendary_temple_city = EXCLUDED.price_legendary_temple_city
RETURNING (xmax = 0) AS inserted;
"""


def ingest_category(cur, category: str, rows: Iterable[Dict[str, object]]) -> Tuple[int, int]:
    inserted = 0
    updated = 0

    for row in rows:
        cur.execute(UPSERT_SQL, row)
        was_inserted = cur.fetchone()[0]
        if was_inserted:
            inserted += 1
        else:
            updated += 1

    return inserted, updated


def main() -> int:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("[ERROR] DATABASE_URL environment variable is not set.", file=sys.stderr)
        return 1

    print("Starting Lost Realm price ingestion...")

    all_rows: Dict[str, List[Dict[str, object]]] = {}

    for category, url in SOURCES:
        print(f"\nFetching {category}...")
        try:
            csv_text = fetch_csv(url)
            saved_path = save_csv_to_disk(category, csv_text)
            print(f"  Saved raw CSV to {saved_path}")
            parsed_rows, skipped_rows = parse_rows(csv_text, category)
            all_rows[category] = parsed_rows
            print(
                f"  Parsed {len(parsed_rows)} rows"
                + (f" (skipped {skipped_rows})" if skipped_rows else "")
            )
        except Exception as exc:
            print(f"  [ERROR] Failed to fetch/parse {category}: {exc}", file=sys.stderr)
            continue

    if not all_rows:
        print("[ERROR] No CSVs were successfully fetched/parsed; nothing to ingest.", file=sys.stderr)
        return 1

    try:
        with psycopg2.connect(database_url) as conn:
            with conn.cursor() as cur:
                totals: Dict[str, Tuple[int, int]] = {}
                for category, rows in all_rows.items():
                    ins, upd = ingest_category(cur, category, rows)
                    totals[category] = (ins, upd)

                print("\nIngestion summary:")
                for category, (ins, upd) in totals.items():
                    print(f"  {category}: inserted={ins}, updated={upd}")

    except Exception as exc:
        print(f"[ERROR] Database ingestion failed: {exc}", file=sys.stderr)
        return 1

    print("\nDone.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
