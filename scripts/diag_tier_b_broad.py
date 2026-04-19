#!/usr/bin/env python3
"""Broad weapon/crafting game code search for Tier B planning."""
import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()

conn = psycopg2.connect(os.environ["DATABASE_URL"])
cur = conn.cursor()

patterns = [
    '%sword%', '%sabre%', '%javelin%', '%pike%', '%mace%',
    '%poleaxe%', '%halberd%', '%longaxe%', '%arrow-%',
    '%bolt-%', '%crossbow%', '%jerkin%', '%gambeson%',
    '%bearhide%', '%vessel%', '%tailoring%',
    '%candle%', '%twine%',
]

print("=== CANONICAL ITEMS ===")
for pat in patterns:
    cur.execute(
        "SELECT game_code, display_name FROM canonical_items WHERE game_code ILIKE %s ORDER BY game_code",
        (pat,),
    )
    rows = cur.fetchall()
    if rows:
        print(f"\nPattern: {pat}")
        for r in rows:
            print(f"  {r[0]} -> {r[1]}")

print("\n\n=== RECIPE OUTPUTS ===")
for pat in patterns:
    cur.execute(
        "SELECT DISTINCT output_game_code FROM recipes WHERE output_game_code ILIKE %s ORDER BY output_game_code",
        (pat,),
    )
    rows = cur.fetchall()
    if rows:
        print(f"\nPattern: {pat}")
        for r in rows:
            print(f"  {r[0]}")

# Also check what items already mapped so we don't double-map
print("\n\n=== ALREADY MAPPED (match_tier='mapped') ===")
cur.execute(
    "SELECT game_code, display_name, lr_item_id FROM canonical_items WHERE match_tier = 'mapped' ORDER BY game_code"
)
for r in cur.fetchall():
    print(f"  {r[0]} -> {r[1]} (lr_id={r[2]})")

conn.close()
