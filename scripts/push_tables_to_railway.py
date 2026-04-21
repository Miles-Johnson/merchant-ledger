#!/usr/bin/env python3
import psycopg2
from psycopg2 import sql


LOCAL = "postgresql://postgres:FatCatTinHat@localhost:5432/postgres"
RAILWAY = "postgresql://postgres:oOxYpSxuanvKDQiExaCnCHpaBwWxwkya@maglev.proxy.rlwy.net:33597/railway"

TABLES = ["lr_items", "canonical_items"]
BATCH_SIZE = 500


def get_row_count(conn, table_name: str) -> int:
    with conn.cursor() as cur:
        cur.execute(
            sql.SQL("SELECT COUNT(*) FROM {}")
            .format(sql.Identifier(table_name))
        )
        return cur.fetchone()[0]


def get_columns(conn, table_name: str, *, include_generated: bool = True) -> list[str]:
    with conn.cursor() as cur:
        if include_generated:
            cur.execute(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = %s
                ORDER BY ordinal_position
                """,
                (table_name,),
            )
        else:
            cur.execute(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = %s
                  AND COALESCE(is_generated, 'NEVER') = 'NEVER'
                ORDER BY ordinal_position
                """,
                (table_name,),
            )
        cols = [r[0] for r in cur.fetchall()]

    if not cols:
        raise RuntimeError(f"No columns found for table '{table_name}'")
    return cols


def copy_table(local_conn, railway_conn, table_name: str) -> None:
    local_cols = set(get_columns(local_conn, table_name, include_generated=True))
    railway_insertable_cols = get_columns(railway_conn, table_name, include_generated=False)
    cols = [c for c in railway_insertable_cols if c in local_cols]

    if not cols:
        raise RuntimeError(f"No shared insertable columns found for table '{table_name}'")

    print(f"[TABLE] {table_name}")
    print(f"  [BEFORE] local={get_row_count(local_conn, table_name)} railway={get_row_count(railway_conn, table_name)}")

    with railway_conn.cursor() as tgt_cur:
        tgt_cur.execute(
            sql.SQL("TRUNCATE TABLE {} CASCADE")
            .format(sql.Identifier(table_name))
        )

    select_query = sql.SQL("SELECT {} FROM {}")\
        .format(
            sql.SQL(", ").join(sql.Identifier(c) for c in cols),
            sql.Identifier(table_name),
        )
    insert_query = sql.SQL("INSERT INTO {} ({}) VALUES ({})")\
        .format(
            sql.Identifier(table_name),
            sql.SQL(", ").join(sql.Identifier(c) for c in cols),
            sql.SQL(", ").join(sql.Placeholder() for _ in cols),
        )

    copied = 0
    with local_conn.cursor() as src_cur:
        src_cur.execute(select_query)
        all_rows = src_cur.fetchall()

    with railway_conn.cursor() as tgt_cur:
        insert_sql = insert_query.as_string(railway_conn)
        for i in range(0, len(all_rows), BATCH_SIZE):
            batch = all_rows[i:i + BATCH_SIZE]
            tgt_cur.executemany(insert_sql, batch)
            copied += len(batch)
            print(f"  copied {copied} rows...", flush=True)

    railway_conn.commit()
    print(f"  committed table {table_name}", flush=True)
    print(f"  [AFTER]  local={get_row_count(local_conn, table_name)} railway={get_row_count(railway_conn, table_name)}", flush=True)


def main() -> int:
    print("[MEMORY BANK: ACTIVE]")
    print("Connecting to local and Railway databases...")
    local_conn = psycopg2.connect(LOCAL)
    railway_conn = psycopg2.connect(RAILWAY)

    try:
        for table_name in TABLES:
            copy_table(local_conn, railway_conn, table_name)
    finally:
        local_conn.close()
        railway_conn.close()

    print("Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
