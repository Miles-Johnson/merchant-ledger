import psycopg2
conn = psycopg2.connect('postgresql://postgres:oOxYpSxuanvKDQiExaCnCHpaBwWxwkya@maglev.proxy.rlwy.net:33597/railway')
cur = conn.cursor()
cur.execute("SELECT id, display_name FROM lr_items WHERE display_name ILIKE '%resin%' AND display_name NOT ILIKE '%elder%'")
print('railway resin:', cur.fetchall())
cur.execute("SELECT id, lr_item_id FROM canonical_items WHERE id = 'resin_2'")
print('railway resin_2:', cur.fetchall())
cur.close()
conn.close()