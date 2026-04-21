import psycopg2
RAILWAY = 'postgresql://postgres:oOxYpSxuanvKDQiExaCnCHpaBwWxwkya@maglev.proxy.rlwy.net:33597/railway'
conn = psycopg2.connect(RAILWAY)
cur = conn.cursor()
cur.execute("""
UPDATE canonical_items c
SET lr_item_id = l.id
FROM lr_items l
WHERE l.display_name = (
SELECT l2.display_name FROM lr_items l2 WHERE l2.id = c.lr_item_id LIMIT 1
)
AND l.id != c.lr_item_id
AND c.lr_item_id IS NOT NULL
""")
print('rows fixed:', cur.rowcount)
conn.commit()
cur.execute("SELECT id, lr_item_id FROM canonical_items WHERE id = 'resin_2'")
print('resin_2 after fix:', cur.fetchall())
cur.close()
conn.close()