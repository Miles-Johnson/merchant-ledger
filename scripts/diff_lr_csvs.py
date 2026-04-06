#!/usr/bin/env python3
import csv
import os
import re


BACKUP_DIR = os.path.join("data", "raw", "backup_20260324_114213")
CURRENT_DIR = os.path.join("data", "raw")
FILES = ["industrial_goods.csv", "agricultural_goods.csv", "artisanal_goods.csv"]
ITEM_ID_RE = re.compile(r"^(IN|AG|AR)\d+$")


def load_rows(path: str):
    rows = {}
    with open(path, encoding="utf-8-sig", newline="") as f:
        for row in csv.reader(f):
            if not row:
                continue
            item_id = (row[0] or "").strip().upper()
            if ITEM_ID_RE.match(item_id):
                rows[item_id] = [c.strip() for c in row]
    return rows


def main():
    for filename in FILES:
        old_path = os.path.join(BACKUP_DIR, filename)
        new_path = os.path.join(CURRENT_DIR, filename)

        old_rows = load_rows(old_path)
        new_rows = load_rows(new_path)

        added = sorted(set(new_rows) - set(old_rows))
        removed = sorted(set(old_rows) - set(new_rows))
        changed = sorted(
            item_id
            for item_id in (set(old_rows) & set(new_rows))
            if old_rows[item_id] != new_rows[item_id]
        )

        print(f"--- {filename} ---")
        print(
            f"old={len(old_rows)} new={len(new_rows)} "
            f"added={len(added)} removed={len(removed)} changed={len(changed)}"
        )
        if added:
            print("added sample:", ", ".join(added[:15]))
        if removed:
            print("removed sample:", ", ".join(removed[:15]))
        if changed:
            print("changed sample:", ", ".join(changed[:15]))


if __name__ == "__main__":
    main()
