"""Investigation script for resolver.py LR branch analysis."""
import psycopg2
import sys

conn = psycopg2.connect('postgresql://postgres:FatCatTinHat@localhost:5432/postgres')
cur = conn.cursor()

print("=== canonical_items with 'copper' in id or display_name ===", flush=True)
cur.execute("""
    SELECT id, display_name, lr_item_id, fta_item_id 
    FROM canonical_items 
    WHERE lower(id) LIKE '%copper%' OR lower(display_name) LIKE '%copper%' 
    ORDER BY id
""")
rows = cur.fetchall()
if not rows:
    print("  (no results)", flush=True)
for r in rows:
    print(f"  id={r[0]}, name={r[1]}, lr={r[2]}, fta={r[3]}", flush=True)

print("\n=== canonical_items with 'ingot' in id (first 40) ===", flush=True)
cur.execute("""
    SELECT id, display_name, lr_item_id, fta_item_id 
    FROM canonical_items 
    WHERE lower(id) LIKE '%ingot%' 
    ORDER BY id 
    LIMIT 40
""")
rows = cur.fetchall()
if not rows:
    print("  (no results)", flush=True)
for r in rows:
    print(f"  id={r[0]}, name={r[1]}, lr={r[2]}, fta={r[3]}", flush=True)

print("\n=== canonical_items with 'tinbronze' or 'tin bronze' ===", flush=True)
cur.execute("""
    SELECT id, display_name, lr_item_id, fta_item_id 
    FROM canonical_items 
    WHERE lower(id) LIKE '%tinbronze%' 
       OR lower(display_name) LIKE '%tin bronze%'
       OR lower(id) LIKE '%tin%bronze%'
    ORDER BY id
""")
rows = cur.fetchall()
if not rows:
    print("  (no results)", flush=True)
for r in rows:
    print(f"  id={r[0]}, name={r[1]}, lr={r[2]}, fta={r[3]}", flush=True)

print("\n=== canonical_items with 'bismuth' ===", flush=True)
cur.execute("""
    SELECT id, display_name, lr_item_id, fta_item_id 
    FROM canonical_items 
    WHERE lower(id) LIKE '%bismuth%' OR lower(display_name) LIKE '%bismuth%'
    ORDER BY id
""")
rows = cur.fetchall()
if not rows:
    print("  (no results)", flush=True)
for r in rows:
    print(f"  id={r[0]}, name={r[1]}, lr={r[2]}, fta={r[3]}", flush=True)

print("\n=== canonical_items with 'iron' and 'ingot' ===", flush=True)
cur.execute("""
    SELECT id, display_name, lr_item_id, fta_item_id 
    FROM canonical_items 
    WHERE (lower(id) LIKE '%iron%' AND lower(id) LIKE '%ingot%')
       OR (lower(display_name) LIKE '%iron%' AND lower(display_name) LIKE '%ingot%')
    ORDER BY id
""")
rows = cur.fetchall()
if not rows:
    print("  (no results)", flush=True)
for r in rows:
    print(f"  id={r[0]}, name={r[1]}, lr={r[2]}, fta={r[3]}", flush=True)

print("\n=== Total canonical_items count ===", flush=True)
cur.execute("SELECT count(*) FROM canonical_items")
print(f"  count={cur.fetchone()[0]}", flush=True)

print("\n=== Sample canonical_items (first 20) ===", flush=True)
cur.execute("SELECT id, display_name, lr_item_id, fta_item_id FROM canonical_items ORDER BY id LIMIT 20")
rows = cur.fetchall()
for r in rows:
    print(f"  id={r[0]}, name={r[1]}, lr={r[2]}, fta={r[3]}", flush=True)

print("\n=== lr_items with 'copper' or 'ingot' (first 20) ===", flush=True)
cur.execute("""
    SELECT id, name 
    FROM lr_items 
    WHERE lower(name) LIKE '%copper%' OR lower(name) LIKE '%ingot%'
    ORDER BY id 
    LIMIT 20
""")
rows = cur.fetchall()
if not rows:
    print("  (no results)", flush=True)
for r in rows:
    print(f"  id={r[0]}, name={r[1]}", flush=True)

print("\n=== Recipes with 'alloy' type (first 20) ===", flush=True)
cur.execute("""
    SELECT r.id, r.output_canonical_id, r.recipe_type, r.output_qty, ci.display_name
    FROM recipes r
    LEFT JOIN canonical_items ci ON ci.id = r.output_canonical_id
    WHERE r.recipe_type = 'alloy'
    ORDER BY r.id
    LIMIT 20
""")
rows = cur.fetchall()
if not rows:
    print("  (no results)", flush=True)
for r in rows:
    print(f"  rid={r[0]}, output={r[1]}, type={r[2]}, qty={r[3]}, name={r[4]}", flush=True)

conn.close()
print("\nDone.", flush=True)
