#!/usr/bin/env python3
"""Audit industrial_goods lr_items vs canonical linkage."""
import os
from dotenv import load_dotenv
import psycopg2

load_dotenv()
conn = psycopg2.connect(os.environ["DATABASE_URL"])
cur = conn.cursor()

# Total lr_items for industrial_goods
cur.execute("SELECT COUNT(*) FROM lr_items WHERE lr_category='industrial_goods'")
print("Total industrial_goods lr_items:", cur.fetchone()[0])
print()

# Sub-category breakdown  
cur.execute("""
    SELECT lr_sub_category, COUNT(*) 
    FROM lr_items 
    WHERE lr_category='industrial_goods'
    GROUP BY lr_sub_category 
    ORDER BY COUNT(*) DESC
""")
print("=== lr_items by sub_category ===")
for r in cur.fetchall():
    print(f"  {r[0]:60s} {r[1]}")
print()

# Unlinked lr_items (no canonical pointing to them)
cur.execute("""
    SELECT li.item_id, li.display_name, li.lr_sub_category, li.price_current
    FROM lr_items li
    WHERE li.lr_category = 'industrial_goods'
      AND NOT EXISTS (SELECT 1 FROM canonical_items ci WHERE ci.lr_item_id = li.id)
    ORDER BY li.lr_sub_category, li.item_id
""")
rows = cur.fetchall()
print(f"=== Unlinked industrial_goods lr_items: {len(rows)} ===")
for r in rows:
    print(f"  {r[0]:8s} {r[1]:40s} sub={r[2]:30s} price_current={r[3]}")
print()

# Spot check specific items
for name in ['Iron Chain', 'Iron Scale', 'Iron Plate', 'Copper Chain', 'Steel Chain']:
    cur.execute("""
        SELECT li.item_id, li.display_name, li.price_current, li.unit_price_current,
               ci.id as canonical_id, ci.game_code, ci.display_name as canon_name
        FROM lr_items li
        LEFT JOIN canonical_items ci ON ci.lr_item_id = li.id
        WHERE li.lr_category='industrial_goods' AND li.display_name = %s
    """, (name,))
    rows = cur.fetchall()
    print(f"Spot check '{name}': {len(rows)} matches")
    for r in rows:
        print(f"  lr={r[0]} '{r[1]}' price_current={r[2]} unit_price={r[3]} -> canonical_id={r[4]} game_code={r[5]} canon_name={r[6]}")

conn.close()
