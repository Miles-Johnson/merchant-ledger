#!/usr/bin/env python3
"""Diagnostic: list Tier B LR items for curation planning."""
import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()

conn = psycopg2.connect(os.environ["DATABASE_URL"])
cur = conn.cursor()

# Crafting Goods
print("=== CRAFTING GOODS ===")
cur.execute("SELECT item_id, display_name FROM lr_items WHERE lr_sub_category = 'Crafting Goods' ORDER BY item_id")
for r in cur.fetchall():
    print(f"  {r[0]}: {r[1]}")

# Metal weapon categories
for cat in ['COPPER', 'BISMUTH BRONZE', 'IRON', 'STEEL', 'GOLD', 'SILVER', 'METEORIC IRON', 'RANGED']:
    print(f"\n=== {cat} ===")
    cur.execute("SELECT item_id, display_name FROM lr_items WHERE lr_sub_category = %s ORDER BY item_id", (cat,))
    for r in cur.fetchall():
        print(f"  {r[0]}: {r[1]}")

# Armor categories
for cat in ['SCALE', 'CHAIN', 'BRIGANDINE', 'LAMELLAR', 'PLATE', 'VIKING / TEMPLAR', 'Armor']:
    print(f"\n=== {cat} ===")
    cur.execute("SELECT item_id, display_name FROM lr_items WHERE lr_sub_category = %s ORDER BY item_id", (cat,))
    for r in cur.fetchall():
        print(f"  {r[0]}: {r[1]}")

conn.close()
