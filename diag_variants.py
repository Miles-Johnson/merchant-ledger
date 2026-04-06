#!/usr/bin/env python3
"""Diagnostic: multi-variant canonical scope analysis."""
import os, psycopg2
from dotenv import load_dotenv
load_dotenv()

conn = psycopg2.connect(os.getenv("DATABASE_URL"))
cur = conn.cursor()

# 1. Total lantern_up recipes
cur.execute("SELECT COUNT(*) FROM recipes WHERE output_canonical_id = 'lantern_up'")
print(f"lantern_up total recipes: {cur.fetchone()[0]}")

# 2. Top 30 canonicals with multiple recipe rows
cur.execute("""
    SELECT output_canonical_id, COUNT(*) as cnt
    FROM recipes
    WHERE output_canonical_id IS NOT NULL
    GROUP BY output_canonical_id
    HAVING COUNT(*) > 1
    ORDER BY cnt DESC
    LIMIT 30
""")
print("\nTop 30 canonicals with multiple recipe rows:")
for r in cur.fetchall():
    print(f"  {r[0]}: {r[1]} rows")

# 3. Total distinct canonicals with >1 recipe row
cur.execute("""
    SELECT COUNT(*) FROM (
        SELECT output_canonical_id
        FROM recipes
        WHERE output_canonical_id IS NOT NULL
        GROUP BY output_canonical_id
        HAVING COUNT(*) > 1
    ) sub
""")
print(f"\nTotal distinct canonicals with >1 recipe row: {cur.fetchone()[0]}")

# 4. Specifically: canonicals where multiple recipes differ ONLY by material variant
# (same recipe_type, same output canonical, different ingredient sets)
cur.execute("""
    SELECT ci.display_name, r.output_canonical_id, r.recipe_type, COUNT(*) as cnt
    FROM recipes r
    JOIN canonical_items ci ON ci.id = r.output_canonical_id
    WHERE r.output_canonical_id IS NOT NULL
      AND r.recipe_type IN ('grid', 'smithing', 'knapping', 'clayforming', 'barrel')
    GROUP BY ci.display_name, r.output_canonical_id, r.recipe_type
    HAVING COUNT(*) > 5
    ORDER BY cnt DESC
    LIMIT 40
""")
print("\nCanonicals with >5 same-type recipe rows (likely variant expansions):")
for r in cur.fetchall():
    print(f"  {r[0]} ({r[1]}) [{r[2]}]: {r[3]} rows")

# 5. For lantern_up, show the first recipe the resolver would pick
# (it iterates recipes by DB row order from SELECT without ORDER BY)
cur.execute("""
    SELECT id, output_game_code, recipe_type
    FROM recipes
    WHERE output_canonical_id = 'lantern_up'
    ORDER BY id
    LIMIT 5
""")
print("\nFirst 5 lantern_up recipe rows (by id, which is DB insertion order):")
for r in cur.fetchall():
    print(f"  recipe_id={r[0]}, code={r[1]}, type={r[2]}")

# 6. Check: which recipe ID does the resolver find first with a priceable result?
# The resolver does: SELECT id, output_qty, recipe_type FROM recipes WHERE output_canonical_id = %s
# with NO ORDER BY - so result depends on DB physical/index order
cur.execute("""
    SELECT id, output_qty, recipe_type
    FROM recipes
    WHERE output_canonical_id = 'lantern_up'
""")
print(f"\nAll lantern_up recipe IDs (in DB return order, NO ORDER BY):")
ids = cur.fetchall()
for r in ids:
    print(f"  recipe_id={r[0]}, qty={r[1]}, type={r[2]}")
print(f"Total: {len(ids)}")

# 7. Representative sample of affected families
print("\n--- Representative affected families ---")
for family in ['armor_body_chain', 'armor_body_brigandine', 'armor_body_plate',
               'armor_head_plate', 'armor_legs_plate', 'chest_east',
               'metalplate', 'metalnailsandstrips', 'pickaxehead',
               'axehead', 'shovelhead', 'sword_blade', 'hoe_blade']:
    cur.execute("""
        SELECT output_canonical_id, COUNT(*)
        FROM recipes
        WHERE output_canonical_id LIKE %s
        GROUP BY output_canonical_id
        HAVING COUNT(*) > 1
        ORDER BY COUNT(*) DESC
        LIMIT 3
    """, (f"%{family}%",))
    rows = cur.fetchall()
    if rows:
        for r in rows:
            print(f"  {r[0]}: {r[1]} recipes")

conn.close()
