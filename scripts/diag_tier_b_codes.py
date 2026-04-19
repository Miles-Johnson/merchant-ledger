#!/usr/bin/env python3
"""Diagnostic: find canonical game codes for Tier B weapon/armor items."""
import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()

conn = psycopg2.connect(os.environ["DATABASE_URL"])
cur = conn.cursor()

# Weapons - check what game codes exist for weapon types
weapon_patterns = [
    'arrowhead-%', 'blade-falx-%', 'axe-felling-%', 'blade-sabre-%',
    'blade-greatsword-%', 'blade-longsword-%', 'blade-shortsword-%',
    'blade-armingsword-%', 'spear-generic-%', 'spearhead-%',
    'pike-%', 'mace-%', 'poleaxe-%', 'halberd-%', 'javelin-%',
    'sword-%', 'blade-%',
]

print("=== WEAPON GAME CODES IN CANONICAL_ITEMS ===")
for pat in weapon_patterns:
    cur.execute("SELECT game_code, display_name FROM canonical_items WHERE game_code LIKE %s ORDER BY game_code", (f'item:{pat}',))
    rows = cur.fetchall()
    if rows:
        print(f"\n  Pattern: item:{pat}")
        for r in rows:
            print(f"    {r[0]} -> {r[1]}")

# Also check recipes output for weapon-like items
print("\n\n=== WEAPON GAME CODES IN RECIPES OUTPUT ===")
for pat in weapon_patterns:
    cur.execute("SELECT DISTINCT output_game_code FROM recipes WHERE output_game_code LIKE %s ORDER BY output_game_code", (f'item:{pat}',))
    rows = cur.fetchall()
    if rows:
        print(f"\n  Pattern: item:{pat}")
        for r in rows:
            print(f"    {r[0]}")

# Armor game codes
armor_patterns = [
    'armor-body-scale-%', 'armor-head-scale-%', 'armor-legs-scale-%',
    'armor-body-chain-%', 'armor-head-chain-%', 'armor-legs-chain-%',
    'armor-body-brigandine-%', 'armor-head-brigandine-%', 'armor-legs-brigandine-%',
    'armor-body-lamellar-%', 'armor-head-lamellar-%', 'armor-legs-lamellar-%',
    'armor-body-plate-%', 'armor-head-plate-%', 'armor-legs-plate-%',
    'armor-%',
]

print("\n\n=== ARMOR GAME CODES IN CANONICAL_ITEMS ===")
for pat in armor_patterns:
    cur.execute("SELECT game_code, display_name FROM canonical_items WHERE game_code LIKE %s ORDER BY game_code", (f'item:{pat}',))
    rows = cur.fetchall()
    if rows:
        print(f"\n  Pattern: item:{pat}")
        for r in rows:
            print(f"    {r[0]} -> {r[1]}")

# Crafting goods game codes
print("\n\n=== CRAFTING GOODS GAME CODES ===")
crafting_patterns = [
    'candle%', 'vessel%', 'sewingkit%', 'glass%', 'book%', 'cloth%',
    'leather%', 'tailoringkit%', 'twine%', 'linen%',
]
for pat in crafting_patterns:
    cur.execute("SELECT game_code, display_name FROM canonical_items WHERE game_code LIKE %s ORDER BY game_code", (f'item:{pat}',))
    rows = cur.fetchall()
    if rows:
        print(f"\n  Pattern: item:{pat}")
        for r in rows:
            print(f"    {r[0]} -> {r[1]}")

# Also check for block: prefixed items
for pat in ['candle%', 'vessel%', 'glass%', 'book%']:
    cur.execute("SELECT game_code, display_name FROM canonical_items WHERE game_code LIKE %s ORDER BY game_code", (f'block:{pat}',))
    rows = cur.fetchall()
    if rows:
        print(f"\n  Pattern: block:{pat}")
        for r in rows:
            print(f"    {r[0]} -> {r[1]}")

# Ranged
print("\n\n=== RANGED GAME CODES ===")
for pat in ['bow-%', 'crossbow%']:
    cur.execute("SELECT game_code, display_name FROM canonical_items WHERE game_code LIKE %s ORDER BY game_code", (f'item:{pat}',))
    rows = cur.fetchall()
    if rows:
        print(f"\n  Pattern: item:{pat}")
        for r in rows:
            print(f"    {r[0]} -> {r[1]}")

# Base armor items
print("\n\n=== BASE ARMOR (Jerkin/Gambeson/Bear) ===")
for pat in ['jerkin%', 'gambeson%', 'clothes-body-bearhide%']:
    cur.execute("SELECT game_code, display_name FROM canonical_items WHERE game_code LIKE %s ORDER BY game_code", (f'item:{pat}',))
    rows = cur.fetchall()
    if rows:
        print(f"\n  Pattern: item:{pat}")
        for r in rows:
            print(f"    {r[0]} -> {r[1]}")

conn.close()
