"""Diagnostic: investigate tin bronze ingot + candle gate failures."""
import psycopg2, os
from dotenv import load_dotenv
load_dotenv()

conn = psycopg2.connect(os.environ["DATABASE_URL"])
cur = conn.cursor()

print("=" * 60)
print("TIN BRONZE INGOT: alias resolution candidates")
print("=" * 60)
cur.execute("""
    SELECT ia.canonical_id, ia.alias, ci.display_name, ci.game_code, ci.lr_item_id
    FROM item_aliases ia
    JOIN canonical_items ci ON ci.id = ia.canonical_id
    WHERE similarity(ia.alias, 'tin bronze ingot') > 0.3
    ORDER BY
        CASE WHEN ia.alias = 'tin bronze ingot' THEN 0 ELSE 1 END,
        similarity(ia.alias, 'tin bronze ingot') DESC,
        COALESCE((
            SELECT MIN(
                CASE r2.recipe_type
                    WHEN 'alloy' THEN 0
                    WHEN 'smithing' THEN 1
                    WHEN 'barrel' THEN 2
                    WHEN 'grid' THEN 3
                    WHEN 'cooking' THEN 4
                    WHEN 'knapping' THEN 5
                    WHEN 'clayforming' THEN 5
                    ELSE 6
                END
            )
            FROM recipes r2
            WHERE r2.output_canonical_id = ci.id
        ), 6) ASC,
        ci.id
    LIMIT 10
""")
for r in cur.fetchall():
    print(r)

print()
print("All canonicals with 'tin bronze' in display_name:")
cur.execute("""
    SELECT ci.id, ci.display_name, ci.game_code, ci.lr_item_id,
           (SELECT count(*) FROM recipes r WHERE r.output_canonical_id = ci.id) as recipe_count,
           (SELECT string_agg(DISTINCT r.recipe_type, ', ') FROM recipes r WHERE r.output_canonical_id = ci.id) as recipe_types
    FROM canonical_items ci
    WHERE lower(ci.display_name) LIKE '%%tin bronze%%'
    ORDER BY ci.id
""")
for r in cur.fetchall():
    print(r)

print()
print("Recipes with output game_code containing 'ingot-tinbronze':")
cur.execute("""
    SELECT r.id, r.output_game_code, r.output_canonical_id, r.recipe_type, r.output_qty
    FROM recipes r
    WHERE r.output_game_code LIKE '%%ingot-tinbronze%%'
       OR r.output_game_code LIKE '%%ingot_tinbronze%%'
    ORDER BY r.recipe_type, r.id
""")
for r in cur.fetchall():
    print(r)

print()
print("=" * 60)
print("CANDLE: alias resolution candidates")
print("=" * 60)
cur.execute("""
    SELECT ia.canonical_id, ia.alias, ci.display_name, ci.game_code, ci.lr_item_id
    FROM item_aliases ia
    JOIN canonical_items ci ON ci.id = ia.canonical_id
    WHERE similarity(ia.alias, 'candle') > 0.3
    ORDER BY
        CASE WHEN ia.alias = 'candle' THEN 0 ELSE 1 END,
        similarity(ia.alias, 'candle') DESC,
        COALESCE((
            SELECT MIN(
                CASE r2.recipe_type
                    WHEN 'alloy' THEN 0
                    WHEN 'smithing' THEN 1
                    WHEN 'barrel' THEN 2
                    WHEN 'grid' THEN 3
                    WHEN 'cooking' THEN 4
                    WHEN 'knapping' THEN 5
                    WHEN 'clayforming' THEN 5
                    ELSE 6
                END
            )
            FROM recipes r2
            WHERE r2.output_canonical_id = ci.id
        ), 6) ASC,
        ci.id
    LIMIT 10
""")
for r in cur.fetchall():
    print(r)

print()
print("All canonicals with 'candle' in display_name:")
cur.execute("""
    SELECT ci.id, ci.display_name, ci.game_code, ci.lr_item_id,
           (SELECT count(*) FROM recipes r WHERE r.output_canonical_id = ci.id) as recipe_count,
           (SELECT string_agg(DISTINCT r.recipe_type, ', ') FROM recipes r WHERE r.output_canonical_id = ci.id) as recipe_types
    FROM canonical_items ci
    WHERE lower(ci.display_name) LIKE '%%candle%%'
    ORDER BY ci.id
""")
for r in cur.fetchall():
    print(r)

print()
print("Recipes with output game_code containing 'candle':")
cur.execute("""
    SELECT r.id, r.output_game_code, r.output_canonical_id, r.recipe_type, r.output_qty
    FROM recipes r
    WHERE r.output_game_code LIKE '%%candle%%'
    ORDER BY r.recipe_type, r.id
""")
for r in cur.fetchall():
    print(r)

conn.close()
