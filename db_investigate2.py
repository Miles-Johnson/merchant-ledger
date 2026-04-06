"""Investigation part 2: LR items, alloy recipes, and resolve trace."""
import psycopg2

conn = psycopg2.connect('postgresql://postgres:FatCatTinHat@localhost:5432/postgres')
cur = conn.cursor()

# lr_items schema
print("=== lr_items columns ===", flush=True)
cur.execute("""
    SELECT column_name FROM information_schema.columns
    WHERE table_name='lr_items' ORDER BY ordinal_position
""")
for r in cur.fetchall():
    print(f"  {r[0]}", flush=True)

# Key ingot canonicals
print("\n=== Key ingot canonicals ===", flush=True)
for cid in ['ingot_copper', 'ingot_iron', 'ingot_tinbronze', 'ingot_bismuthbronze',
            'ingot_tin', 'ingot_bismuth', 'ingot_gold', 'ingot_silver', 'ingot_steel']:
    cur.execute("SELECT id, display_name, lr_item_id, fta_item_id FROM canonical_items WHERE id = %s", (cid,))
    row = cur.fetchone()
    if row:
        print(f"  id={row[0]}, name={row[1]}, lr_item_id={row[2]}, fta_item_id={row[3]}", flush=True)
    else:
        print(f"  {cid} -> NOT FOUND", flush=True)

# Recipes for ingot_copper
print("\n=== Recipes WHERE output_canonical_id = 'ingot_copper' ===", flush=True)
cur.execute("""
    SELECT r.id, r.output_canonical_id, r.recipe_type, r.output_qty
    FROM recipes r
    WHERE r.output_canonical_id = 'ingot_copper'
    ORDER BY r.id
""")
rows = cur.fetchall()
if not rows:
    print("  (no recipes)", flush=True)
for r in rows:
    print(f"  recipe_id={r[0]}, output={r[1]}, type={r[2]}, qty={r[3]}", flush=True)

# Recipes for ingot_tinbronze
print("\n=== Recipes WHERE output_canonical_id = 'ingot_tinbronze' ===", flush=True)
cur.execute("""
    SELECT r.id, r.output_canonical_id, r.recipe_type, r.output_qty
    FROM recipes r
    WHERE r.output_canonical_id = 'ingot_tinbronze'
    ORDER BY r.id
""")
rows = cur.fetchall()
if not rows:
    print("  (no recipes)", flush=True)
for r in rows:
    print(f"  recipe_id={r[0]}, output={r[1]}, type={r[2]}, qty={r[3]}", flush=True)

# Recipes for ingot_bismuthbronze  
print("\n=== Recipes WHERE output_canonical_id = 'ingot_bismuthbronze' ===", flush=True)
cur.execute("""
    SELECT r.id, r.output_canonical_id, r.recipe_type, r.output_qty
    FROM recipes r
    WHERE r.output_canonical_id = 'ingot_bismuthbronze'
    ORDER BY r.id
""")
rows = cur.fetchall()
if not rows:
    print("  (no recipes)", flush=True)
for r in rows:
    print(f"  recipe_id={r[0]}, output={r[1]}, type={r[2]}, qty={r[3]}", flush=True)

# LR items for the lr_item_ids found
print("\n=== lr_items for id=3 (copper ingot lr_item_id) ===", flush=True)
cur.execute("SELECT * FROM lr_items WHERE id = 3")
row = cur.fetchone()
if row:
    cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name='lr_items' ORDER BY ordinal_position")
    cols = [r[0] for r in cur.fetchall()]
    for col, val in zip(cols, row):
        print(f"  {col} = {val}", flush=True)
else:
    print("  (not found)", flush=True)

# What does _has_recipe_type return for ingot_copper, 'alloy'?
print("\n=== Does ingot_copper have alloy recipe? ===", flush=True)
cur.execute("""
    SELECT 1 FROM recipes
    WHERE output_canonical_id = 'ingot_copper' AND recipe_type = 'alloy'
    LIMIT 1
""")
print(f"  has_alloy = {cur.fetchone() is not None}", flush=True)

# What does _has_recipe_type return for ingot_tinbronze, 'alloy'?
print("\n=== Does ingot_tinbronze have alloy recipe? ===", flush=True)
cur.execute("""
    SELECT 1 FROM recipes
    WHERE output_canonical_id = 'ingot_tinbronze' AND recipe_type = 'alloy'
    LIMIT 1
""")
print(f"  has_alloy = {cur.fetchone() is not None}", flush=True)

# What does _has_recipe_type return for ingot_bismuthbronze, 'alloy'?  
print("\n=== Does ingot_bismuthbronze have alloy recipe? ===", flush=True)
cur.execute("""
    SELECT 1 FROM recipes
    WHERE output_canonical_id = 'ingot_bismuthbronze' AND recipe_type = 'alloy'
    LIMIT 1
""")
print(f"  has_alloy = {cur.fetchone() is not None}", flush=True)

# All alloy recipes - show their outputs
print("\n=== ALL alloy recipe outputs ===", flush=True)
cur.execute("""
    SELECT r.output_canonical_id, ci.display_name, r.id, r.output_qty
    FROM recipes r
    LEFT JOIN canonical_items ci ON ci.id = r.output_canonical_id
    WHERE r.recipe_type = 'alloy'
    ORDER BY r.output_canonical_id, r.id
""")
rows = cur.fetchall()
if not rows:
    print("  (no alloy recipes)", flush=True)
for r in rows:
    print(f"  output={r[0]}, name={r[1]}, recipe_id={r[2]}, qty={r[3]}", flush=True)

# Check price_overrides 
print("\n=== price_overrides for ingot_copper ===", flush=True)
cur.execute("SELECT * FROM price_overrides WHERE canonical_id = 'ingot_copper'")
rows = cur.fetchall()
if not rows:
    print("  (none)", flush=True)
for r in rows:
    print(f"  {r}", flush=True)

conn.close()
print("\nDone.", flush=True)
