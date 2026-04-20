#!/usr/bin/env python3
# DEPRECATED (Gen 2 legacy): This importer targets legacy lr_items shape and is retained for reference only.
"""
import_lr_items_pg.py
Downloads all Lost Realm economy sheets from Google Sheets (public CSV export)
and imports them into a single PostgreSQL table: lr_items

Table structure:
  - item_name      TEXT
  - category       TEXT  (agricultural_goods / industrial_goods / artisanal_goods / settlement_specialization)
  - + all other columns found in each sheet (dynamic)

Usage:
  python import_lr_items_pg.py --host localhost --port 5432 --database postgres --user postgres --password YOUR_PASSWORD
"""

import argparse
import csv
import io
import urllib.request
import psycopg2
import sys

# ── Sheet definitions ────────────────────────────────────────────────────────
SPREADSHEET_ID = "2PACX-1vR73BLsil5C-xCp_P-_VCMWhSRliwou5FWfyhMmAbOTc4a91OcwpkxC0J_R0tdmuYilv8_OVWtJqtlj"

SHEETS = [
    {"name": "agricultural_goods", "gid": "403466432"},
    {"name": "industrial_goods", "gid": "1468550541"},
    {"name": "artisanal_goods", "gid": "393020471"},
    {"name": "settlement_specialization", "gid": "174237392"},
]

BASE_URL = (
    "https://docs.google.com/spreadsheets/d/e/"
    "{sid}/pub?gid={gid}&single=true&output=csv"
)


# ── Helpers ──────────────────────────────────────────────────────────────────

def fetch_csv(sid, gid):
    url = BASE_URL.format(sid=sid, gid=gid)
    print(f"  Fetching: {url}")
    with urllib.request.urlopen(url) as resp:
        return resp.read().decode("utf-8")


def parse_csv(text):
    reader = csv.DictReader(io.StringIO(text))
    rows = list(reader)
    headers = reader.fieldnames or []
    return headers, rows


def sanitize_col(name):
    """Turn a header string into a safe SQL column name."""
    return (
        name.strip()
        .lower()
        .replace(" ", "_")
        .replace("(", "")
        .replace(")", "")
        .replace("/", "_")
        .replace("-", "_")
        .replace("%", "pct")
        .replace(".", "")
        .replace(",", "")
        .replace("'", "")
        .replace('"', "")
        .replace("&", "and")
    )


def normalize_headers(raw_headers):
    """Sanitize headers, drop blanks, and ensure uniqueness."""
    out = []
    seen = {}
    for idx, h in enumerate(raw_headers, start=1):
        base = sanitize_col(h or "")
        if not base:
            continue
        n = seen.get(base, 0) + 1
        seen[base] = n
        col = base if n == 1 else f"{base}_{n}"
        out.append((h, col))
    return out


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Import Lost Realm economy data into PostgreSQL")
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", default=5432, type=int)
    parser.add_argument("--database", default="postgres")
    parser.add_argument("--user", default="postgres")
    parser.add_argument("--password", required=True)
    args = parser.parse_args()

    # ── Step 1: download all sheets ──────────────────────────────────────────
    print("\n📥 Downloading sheets...")
    all_data = []  # list of (category, sanitized_headers, rows)
    all_columns = set()  # union of all column names across sheets

    for sheet in SHEETS:
        print(f"\n  Sheet: {sheet['name']}")
        try:
            csv_text = fetch_csv(SPREADSHEET_ID, sheet["gid"])
        except Exception as e:
            print(f"  ⚠️  Failed to fetch {sheet['name']}: {e}")
            continue

        raw_headers, rows = parse_csv(csv_text)
        # Skip completely empty rows
        rows = [r for r in rows if any(v.strip() for v in r.values())]

        normalized = normalize_headers(raw_headers)
        san_headers = [c for _, c in normalized]
        all_columns.update(san_headers)
        all_data.append((sheet["name"], normalized, rows))
        print(f"  ✅ {len(rows)} rows, {len(san_headers)} columns: {san_headers}")

    if not all_data:
        print("No data fetched. Exiting.")
        sys.exit(1)

    # ── Step 2: build unified column list ───────────────────────────────────
    # Preserve insertion order: category first, then all columns alphabetically
    ordered_cols = sorted(all_columns)

    # ── Step 3: connect to PostgreSQL ────────────────────────────────────────
    print(f"\n🔌 Connecting to PostgreSQL at {args.host}:{args.port}/{args.database}...")
    conn = psycopg2.connect(
        host=args.host,
        port=args.port,
        dbname=args.database,
        user=args.user,
        password=args.password,
    )
    cur = conn.cursor()

    # ── Step 4: create table ─────────────────────────────────────────────────
    col_defs = ["category TEXT"] + [f'"{c}" TEXT' for c in ordered_cols]
    create_sql = f"""
    DROP TABLE IF EXISTS lr_items;
    CREATE TABLE lr_items (
        id SERIAL PRIMARY KEY,
        {",\n        ".join(col_defs)},
        inserted_at TIMESTAMPTZ DEFAULT NOW()
    );
    """
    print("\n🛠  Creating table lr_items...")
    cur.execute(create_sql)

    # Index on common lookup columns if they exist
    for idx_col in ["item_name", "name", "item", "good", "resource"]:
        if idx_col in ordered_cols:
            cur.execute(f'CREATE INDEX ON lr_items ("{idx_col}");')
            print(f"  📑 Index created on \"{idx_col}\"")

    cur.execute("CREATE INDEX ON lr_items (category);")

    # ── Step 5: insert rows ──────────────────────────────────────────────────
    total_inserted = 0
    for category, normalized_headers, rows in all_data:
        print(f"\n📤 Inserting {len(rows)} rows for category '{category}'...")
        insert_cols = ["category"] + [f'"{c}"' for c in ordered_cols]
        placeholders = ", ".join(["%s"] * len(insert_cols))
        insert_sql = f"INSERT INTO lr_items ({', '.join(insert_cols)}) VALUES ({placeholders})"

        # Map sanitized header -> raw header for lookup in row dict
        san_to_raw = {san: raw for raw, san in normalized_headers}

        batch = []
        for row in rows:
            values = [category]
            for col in ordered_cols:
                raw_col = san_to_raw.get(col)
                val = row.get(raw_col, "").strip() if raw_col else None
                values.append(val if val else None)
            batch.append(values)

        cur.executemany(insert_sql, batch)
        total_inserted += len(batch)
        print(f"  ✅ {len(batch)} rows inserted")

    conn.commit()

    # ── Step 6: validation ───────────────────────────────────────────────────
    print("\n🔍 Validation queries:")
    cur.execute("SELECT category, COUNT(*) FROM lr_items GROUP BY category ORDER BY category;")
    rows = cur.fetchall()
    for cat, count in rows:
        print(f"  {cat}: {count} rows")

    cur.execute("SELECT COUNT(*) FROM lr_items;")
    total = cur.fetchone()[0]
    print(f"\n  Total rows in lr_items: {total}")

    print("\n📋 Columns in lr_items:")
    cur.execute(
        """
        SELECT column_name FROM information_schema.columns
        WHERE table_name = 'lr_items'
        ORDER BY ordinal_position;
    """
    )
    for (col,) in cur.fetchall():
        print(f"  - {col}")

    cur.close()
    conn.close()

    print(f"\n✅ Done! {total_inserted} rows imported into lr_items.")
    print("\n💡 Example join with your recipes:")
    print(
        """
    SELECT
        r.*,
        i.price,
        i.category AS item_category
    FROM vs_recipes r
    LEFT JOIN lr_items i
        ON LOWER(r.name) = LOWER(i.item_name)   -- adjust column names after inspecting data
    LIMIT 20;
    """
    )


if __name__ == "__main__":
    main()
