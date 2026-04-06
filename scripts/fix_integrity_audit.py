#!/usr/bin/env python3
"""[MEMORY BANK: ACTIVE]
Surgical fixes for integrity audit issues:
  1) suspicious canonical<->FTA trigram links (<0.7)
  2) duplicate canonical display_name groups
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import psycopg2
from dotenv import load_dotenv


@dataclass
class SuspiciousRow:
    canonical_id: str
    canonical_name: str
    fta_id: int
    fta_name: str
    sim: float


def classify_suspicious(row: SuspiciousRow) -> Tuple[str, str]:
    """Return (disposition, rationale)."""
    # Manual adjudication for current 17-row audit set.
    false_matches = {
        "sake_whiskey_per_barrel": "Canonical is combined 'Sake / Whiskey' while FTA row is only 'Sake'.",
        "barrel": "Linked to 'Brandy (Per barrel)' due token overlap; different item.",
        "elephant_blanket_type": "Canonical is blanket item, FTA row is tame animal listing.",
        "chocolate_cocoapowder": "Canonical combines chocolate+cocoa; FTA row is only cocoa powder.",
        "seeds_spelt": "Seed item linked to grain commodity; not equivalent.",
    }

    needs_manual = {
        "clay_red": "Could be acceptable generic clay fallback or incorrect color-specific mismatch.",
    }

    if row.canonical_id in false_matches:
        return "fixed", false_matches[row.canonical_id]
    if row.canonical_id in needs_manual:
        return "needs manual review", needs_manual[row.canonical_id]
    return "kept", "Low trigram score is formatting/annotation noise; item meaning matches."


def choose_merge_target(rows: List[Tuple]) -> Optional[str]:
    """Prefer game-code rows, then LR-linked rows, then lowest id."""
    candidates = []
    for rid, game_code, lr_item_id, fta_item_id in rows:
        if fta_item_id is not None:
            continue
        candidates.append((0 if game_code else 1, 0 if lr_item_id is not None else 1, rid))
    if not candidates:
        return None
    candidates.sort()
    return candidates[0][2]


def main() -> int:
    load_dotenv()
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        raise SystemExit("[ERROR] DATABASE_URL not set")

    print("[MEMORY BANK: ACTIVE]")

    with psycopg2.connect(db_url) as conn:
        with conn.cursor() as cur:
            # ---------------------------
            # ISSUE 1: suspicious links
            # ---------------------------
            cur.execute(
                """
                SELECT ci.id, ci.display_name, fi.id, fi.display_name,
                       similarity(lower(ci.display_name), lower(fi.display_name)) AS sim
                FROM canonical_items ci
                JOIN fta_items fi ON fi.id = ci.fta_item_id
                WHERE ci.fta_item_id IS NOT NULL
                  AND similarity(lower(ci.display_name), lower(fi.display_name)) < 0.7
                ORDER BY sim ASC, ci.id
                """
            )
            suspicious = [SuspiciousRow(*r) for r in cur.fetchall()]

            print(f"ISSUE1 suspicious rows: {len(suspicious)}")

            issue1_report = []
            fixed_count = 0
            kept_count = 0
            manual_count = 0

            for row in suspicious:
                disposition, rationale = classify_suspicious(row)
                orphan_note = ""

                if disposition == "fixed":
                    cur.execute(
                        "UPDATE canonical_items SET fta_item_id = NULL WHERE id = %s",
                        (row.canonical_id,),
                    )
                    cur.execute(
                        "SELECT COUNT(*) FROM canonical_items WHERE fta_item_id = %s",
                        (row.fta_id,),
                    )
                    refs = cur.fetchone()[0]
                    if refs == 0:
                        orphan_note = "FTA item now orphaned (left intentionally for later matching)."
                    fixed_count += 1
                elif disposition == "kept":
                    kept_count += 1
                else:
                    manual_count += 1

                issue1_report.append(
                    {
                        "canonical_id": row.canonical_id,
                        "canonical_name": row.canonical_name,
                        "fta_id": row.fta_id,
                        "fta_name": row.fta_name,
                        "similarity": round(row.sim, 3),
                        "disposition": disposition,
                        "rationale": rationale,
                        "note": orphan_note,
                    }
                )

            # ---------------------------
            # ISSUE 2: duplicate groups
            # ---------------------------
            cur.execute(
                """
                SELECT display_name, COUNT(*)
                FROM canonical_items
                WHERE display_name IS NOT NULL
                  AND btrim(display_name) <> ''
                GROUP BY display_name
                HAVING COUNT(*) > 1
                ORDER BY COUNT(*) DESC, display_name
                """
            )
            dup_groups = cur.fetchall()
            print(f"ISSUE2 duplicate groups (pre-fix): {len(dup_groups)}")

            top10 = dup_groups[:10]
            top10_summary = []

            expected_groups = 0
            unexpected_groups = 0
            relinked = 0
            deleted = 0

            for display_name, cnt in dup_groups:
                cur.execute(
                    """
                    SELECT id, game_code, lr_item_id, fta_item_id
                    FROM canonical_items
                    WHERE display_name = %s
                    ORDER BY id
                    """,
                    (display_name,),
                )
                rows = cur.fetchall()

                fta_only_extras = [r for r in rows if r[1] is None and r[2] is None and r[3] is not None]
                anchor_rows = [r for r in rows if not (r[1] is None and r[2] is None and r[3] is not None)]

                group_cause = "expected variant/material duplicates"
                if fta_only_extras and anchor_rows:
                    group_cause = "unexpected FTA-only creation duplicate(s)"
                    unexpected_groups += 1

                    for rid, _gc, _lr, fta_id in fta_only_extras:
                        target_id = choose_merge_target(anchor_rows)
                        if target_id is None:
                            continue

                        cur.execute("UPDATE canonical_items SET fta_item_id = %s WHERE id = %s", (fta_id, target_id))
                        cur.execute("DELETE FROM canonical_items WHERE id = %s", (rid,))
                        relinked += 1
                        deleted += 1

                        # refresh anchors for subsequent moves in same group
                        cur.execute(
                            """
                            SELECT id, game_code, lr_item_id, fta_item_id
                            FROM canonical_items
                            WHERE display_name = %s
                            ORDER BY id
                            """,
                            (display_name,),
                        )
                        anchor_rows = cur.fetchall()
                else:
                    expected_groups += 1

                if (display_name, cnt) in top10:
                    game_rows = sum(1 for r in rows if r[1] is not None)
                    null_game_rows = cnt - game_rows
                    lr_rows = sum(1 for r in rows if r[2] is not None)
                    fta_rows = sum(1 for r in rows if r[3] is not None)
                    top10_summary.append(
                        {
                            "display_name": display_name,
                            "count": cnt,
                            "game_code_rows": game_rows,
                            "null_game_code_rows": null_game_rows,
                            "lr_rows": lr_rows,
                            "fta_rows": fta_rows,
                            "cause": group_cause,
                        }
                    )

            cur.execute(
                """
                SELECT COUNT(*)
                FROM (
                    SELECT display_name
                    FROM canonical_items
                    WHERE display_name IS NOT NULL
                      AND btrim(display_name) <> ''
                    GROUP BY display_name
                    HAVING COUNT(*) > 1
                ) d
                """
            )
            dup_groups_after = cur.fetchone()[0]

    # transaction auto-committed on normal exit

    print("\n=== ISSUE 1 FINAL DISPOSITION (all suspicious links) ===")
    for r in issue1_report:
        note = f" | note={r['note']}" if r["note"] else ""
        print(
            f"{r['canonical_id']} | {r['canonical_name']} -> {r['fta_name']} "
            f"(sim={r['similarity']}) | {r['disposition']} | {r['rationale']}{note}"
        )

    print("\nIssue 1 summary:")
    print(f"  fixed={fixed_count}, kept={kept_count}, needs_manual_review={manual_count}")

    print("\n=== ISSUE 2 TOP 10 DUPLICATE GROUP CAUSES ===")
    for row in top10_summary:
        print(
            f"{row['display_name']} | count={row['count']} | game_code_rows={row['game_code_rows']} "
            f"| null_game_code_rows={row['null_game_code_rows']} | lr_rows={row['lr_rows']} "
            f"| fta_rows={row['fta_rows']} | cause={row['cause']}"
        )

    print("\nIssue 2 summary:")
    print(f"  duplicate_groups_pre_fix={len(dup_groups)}")
    print(f"  duplicate_groups_post_fix={dup_groups_after}")
    print(f"  expected_groups={expected_groups}")
    print(f"  unexpected_groups={unexpected_groups}")
    print(f"  relinked_fta_duplicates={relinked}")
    print(f"  deleted_duplicate_canonicals={deleted}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
