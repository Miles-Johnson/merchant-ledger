"""Diagnostic: recipe-family disambiguation collisions."""
import psycopg2
from dotenv import load_dotenv
import os

load_dotenv()
conn = psycopg2.connect(os.getenv("DATABASE_URL"))
cur = conn.cursor()

print("=" * 70)
print("1. LEATHER CASE: resolve_canonical_id ranking")
print("=" * 70)
cur.execute("""
    SELECT ia.canonical_id, ia.alias, ci.display_name, ci.game_code, ci.lr_item_id,
           similarity(ia.alias, 'leather') as sim
    FROM item_aliases ia
    JOIN canonical_items ci ON ci.id = ia.canonical_id
    WHERE similarity(ia.alias, 'leather') > 0.3
    ORDER BY
        CASE WHEN ia.alias = 'leather' THEN 0 ELSE 1 END,
        similarity(ia.alias, 'leather') DESC,
        CASE WHEN lower(ci.display_name) = 'leather' THEN 0 ELSE 1 END,
        CASE WHEN ci.lr_item_id IS NOT NULL THEN 0 ELSE 1 END,
        ci.id
    LIMIT 15
""")
for r in cur.fetchall():
    print(r)

print()
print("=" * 70)
print("2. LEATHER: Which canonicals have recipes, and what types?")
print("=" * 70)
for cid in ['feather', 'leather', 'leather_2', 'leather_3', 'leather_normal_plain', 'panel_leather']:
    cur.execute("""
        SELECT r.output_canonical_id, r.recipe_type, r.output_game_code, r.output_qty
        FROM recipes r
        WHERE r.output_canonical_id = %s
        LIMIT 5
    """, (cid,))
    rows = cur.fetchall()
    if rows:
        for r in rows:
            print(f"  {cid}: type={r[1]}, game_code={r[2]}, qty={r[3]}")
    else:
        print(f"  {cid}: NO RECIPES")

print()
print("=" * 70)
print("3. BROAD COLLISION SCAN: aliases with 3+ distinct canonicals")
print("=" * 70)
cur.execute("""
    SELECT ia.alias, COUNT(DISTINCT ia.canonical_id) as cnt,
           array_agg(DISTINCT ia.canonical_id ORDER BY ia.canonical_id) as cids
    FROM item_aliases ia
    GROUP BY ia.alias
    HAVING COUNT(DISTINCT ia.canonical_id) >= 3
    ORDER BY cnt DESC, ia.alias
    LIMIT 30
""")
for r in cur.fetchall():
    print(f"  alias='{r[0]}' -> {r[1]} canonicals: {r[2]}")

print()
print("=" * 70)
print("4. CROSS-FAMILY COLLISIONS: same alias -> different recipe_types")
print("=" * 70)
cur.execute("""
    WITH alias_recipes AS (
        SELECT ia.alias, ia.canonical_id, r.recipe_type
        FROM item_aliases ia
        JOIN recipes r ON r.output_canonical_id = ia.canonical_id
    )
    SELECT alias, COUNT(DISTINCT recipe_type) as type_cnt,
           array_agg(DISTINCT recipe_type ORDER BY recipe_type) as types,
           array_agg(DISTINCT canonical_id ORDER BY canonical_id) as cids
    FROM alias_recipes
    WHERE recipe_type IS NOT NULL
    GROUP BY alias
    HAVING COUNT(DISTINCT recipe_type) >= 2
    ORDER BY type_cnt DESC, alias
    LIMIT 30
""")
for r in cur.fetchall():
    print(f"  alias='{r[0]}' -> types={r[2]}, canonicals={r[3]}")

print()
print("=" * 70)
print("5. SPECIFIC COLLISION PATTERNS: hide/leather, ore/ingot, log/plank")
print("=" * 70)
for term in ['hide', 'plank', 'planks', 'log', 'logs', 'ore', 'ingot', 'iron ingot', 'copper ingot', 'flax', 'bread', 'flour']:
    cur.execute("""
        SELECT ia.canonical_id, ci.display_name, ci.game_code, ci.lr_item_id
        FROM item_aliases ia
        JOIN canonical_items ci ON ci.id = ia.canonical_id
        WHERE ia.alias = %s
        ORDER BY ci.id
    """, (term,))
    rows = cur.fetchall()
    if rows:
        print(f"  '{term}' -> {len(rows)} canonicals:")
        for r in rows:
            print(f"    {r[0]}: display='{r[1]}', game_code={r[2]}, lr_id={r[3]}")

print()
print("=" * 70)
print("6. CANONICALS WHERE display_name='Leather' and their recipe types")
print("=" * 70)
cur.execute("""
    SELECT ci.id, ci.display_name, ci.game_code, ci.lr_item_id, ci.match_tier,
           (SELECT array_agg(DISTINCT r.recipe_type) FROM recipes r WHERE r.output_canonical_id = ci.id) as recipe_types,
           (SELECT COUNT(*) FROM recipes r WHERE r.output_canonical_id = ci.id) as recipe_count
    FROM canonical_items ci
    WHERE lower(ci.display_name) = 'leather'
    ORDER BY ci.id
""")
for r in cur.fetchall():
    print(f"  {r[0]}: game_code={r[2]}, lr_id={r[3]}, tier={r[4]}, recipe_types={r[5]}, recipe_count={r[6]}")

print()
print("=" * 70)
print("7. LR item 6066 details")
print("=" * 70)
cur.execute("SELECT id, display_name, lr_category, unit_price_current FROM lr_items WHERE id = 6066")
r = cur.fetchone()
if r:
    print(f"  LR #{r[0]}: '{r[1]}', category={r[2]}, unit_price={r[3]}")

print()
print("=" * 70)
print("8. TOTAL alias collision stats")
print("=" * 70)
cur.execute("""
    SELECT 
        COUNT(DISTINCT alias) as total_aliases,
        (SELECT COUNT(*) FROM (SELECT alias FROM item_aliases GROUP BY alias HAVING COUNT(DISTINCT canonical_id) >= 2) t) as aliases_with_2plus,
        (SELECT COUNT(*) FROM (SELECT alias FROM item_aliases GROUP BY alias HAVING COUNT(DISTINCT canonical_id) >= 3) t) as aliases_with_3plus,
        (SELECT COUNT(*) FROM (SELECT alias FROM item_aliases GROUP BY alias HAVING COUNT(DISTINCT canonical_id) >= 5) t) as aliases_with_5plus
    FROM item_aliases
""")
r = cur.fetchone()
print(f"  Total unique aliases: {r[0]}")
print(f"  Aliases with 2+ canonicals: {r[1]}")
print(f"  Aliases with 3+ canonicals: {r[2]}")
print(f"  Aliases with 5+ canonicals: {r[3]}")

conn.close()
