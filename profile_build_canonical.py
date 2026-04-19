#!/usr/bin/env python3
"""
Profile scripts/build_canonical_items.py — DB vs Python timing, top bottlenecks.

Non-invasive: monkey-patches psycopg2 cursor to capture query-level timings,
then runs cProfile over the main() entrypoint.

Output: structured report (console + data/profile_build_canonical.json).
"""

from __future__ import annotations

import cProfile
import io
import json
import os
import pstats
import sys
import time
from collections import defaultdict
from typing import Any, Dict, List, Tuple

# ── Instrumented cursor + patched psycopg2.connect ───────────────────────

import psycopg2
import psycopg2.extensions
import psycopg2.extras

_query_stats: Dict[str, Dict[str, Any]] = defaultdict(lambda: {
    "count": 0,
    "total_s": 0.0,
    "max_s": 0.0,
    "rows_affected": 0,
    "sample": "",
})


def _fingerprint(sql: Any) -> str:
    """Normalise SQL to a family fingerprint (first 120 chars, collapsed whitespace)."""
    text = str(sql or "").strip()
    text = " ".join(text.split())
    return text[:120]


class _ProfilingCursor(psycopg2.extensions.cursor):
    """Subclass that times every execute/executemany call."""

    def execute(self, query, vars=None):
        fp = _fingerprint(query)
        t0 = time.perf_counter()
        result = super().execute(query, vars)
        elapsed = time.perf_counter() - t0
        stat = _query_stats[fp]
        stat["count"] += 1
        stat["total_s"] += elapsed
        if elapsed > stat["max_s"]:
            stat["max_s"] = elapsed
        stat["sample"] = fp
        try:
            stat["rows_affected"] += self.rowcount if self.rowcount and self.rowcount >= 0 else 0
        except Exception:
            pass
        return result

    def executemany(self, query, vars_list):
        fp = _fingerprint(query)
        t0 = time.perf_counter()
        result = super().executemany(query, vars_list)
        elapsed = time.perf_counter() - t0
        stat = _query_stats[fp]
        stat["count"] += 1
        stat["total_s"] += elapsed
        if elapsed > stat["max_s"]:
            stat["max_s"] = elapsed
        stat["sample"] = fp
        try:
            n = len(vars_list) if vars_list else 0
            stat["rows_affected"] += n
        except Exception:
            pass
        return result


# Patch psycopg2.connect to inject our cursor_factory
_original_connect = psycopg2.connect


def _profiling_connect(*args, **kwargs):
    kwargs.setdefault("cursor_factory", _ProfilingCursor)
    return _original_connect(*args, **kwargs)


psycopg2.connect = _profiling_connect

# ── Import the target after patching ─────────────────────────────────────

sys.path.insert(0, os.path.dirname(__file__))
from scripts.build_canonical_items import main as build_main  # noqa: E402


def run_profile() -> None:
    print("=" * 72)
    print("PROFILING scripts/build_canonical_items.py")
    print("=" * 72)

    # ── cProfile pass ────────────────────────────────────────────────────
    profiler = cProfile.Profile()
    wall_t0 = time.perf_counter()
    profiler.enable()
    exit_code = build_main()
    profiler.disable()
    wall_elapsed = time.perf_counter() - wall_t0

    print(f"\n{'=' * 72}")
    print(f"Exit code: {exit_code}")
    print(f"Total wall-clock time: {wall_elapsed:.3f}s")
    print(f"{'=' * 72}\n")

    # ── DB timing report ─────────────────────────────────────────────────
    db_total = sum(s["total_s"] for s in _query_stats.values())
    python_total = wall_elapsed - db_total

    print(f"DB time (cumulative execute/executemany): {db_total:.3f}s  ({100*db_total/wall_elapsed:.1f}%)")
    print(f"Python time (approx wall - DB):            {python_total:.3f}s  ({100*python_total/wall_elapsed:.1f}%)")
    print()

    # Sort queries by total time descending
    sorted_queries = sorted(_query_stats.values(), key=lambda s: s["total_s"], reverse=True)

    print("--- All DB queries (by cumulative time) ---")
    for i, stat in enumerate(sorted_queries):
        mean = stat["total_s"] / stat["count"] if stat["count"] else 0
        print(
            f"  #{i+1}  total={stat['total_s']:.4f}s  count={stat['count']}  "
            f"max={stat['max_s']:.4f}s  mean={mean:.4f}s  rows~{stat['rows_affected']}"
        )
        print(f"       SQL: {stat['sample']}")
    print()

    # ── cProfile top functions ───────────────────────────────────────────
    print("--- cProfile top 30 (cumulative) ---")
    stream = io.StringIO()
    ps = pstats.Stats(profiler, stream=stream)
    ps.sort_stats("cumulative")
    ps.print_stats(30)
    print(stream.getvalue())

    print("--- cProfile top 30 (total internal time) ---")
    stream2 = io.StringIO()
    ps2 = pstats.Stats(profiler, stream=stream2)
    ps2.sort_stats("tottime")
    ps2.print_stats(30)
    print(stream2.getvalue())

    # ── Identify top 3 bottlenecks ───────────────────────────────────────
    bottlenecks: List[Dict[str, Any]] = []

    # Collect cProfile entries for analysis
    ps_data = pstats.Stats(profiler)
    func_stats: List[Tuple[str, float, float, int]] = []
    for (filename, lineno, funcname), (cc, nc, tt, ct, callers) in ps_data.stats.items():
        label = f"{os.path.basename(filename)}:{lineno}({funcname})"
        func_stats.append((label, tt, ct, nc))

    func_stats.sort(key=lambda x: x[1], reverse=True)  # sort by tottime

    # Top DB bottleneck
    if sorted_queries:
        top_q = sorted_queries[0]
        bottlenecks.append({
            "rank": None,
            "type": "DB",
            "description": f"Slowest query family: {top_q['sample'][:80]}",
            "total_s": round(top_q["total_s"], 4),
            "pct_of_wall": round(100 * top_q["total_s"] / wall_elapsed, 1),
            "count": top_q["count"],
            "max_s": round(top_q["max_s"], 4),
        })

    # Top Python bottlenecks from cProfile (skip built-in overhead, focus on project code)
    project_funcs = [
        f for f in func_stats
        if ("build_canonical" in f[0] or "scripts" in f[0])
        and f[1] > 0.001
    ]
    # Also include stdlib heavy-hitters (SequenceMatcher, etc.)
    stdlib_funcs = [
        f for f in func_stats
        if ("difflib" in f[0] or "SequenceMatcher" in f[0] or "trigram" in f[0] or "normalize" in f[0])
        and f[1] > 0.001
    ]
    combined = {f[0]: f for f in project_funcs}
    for f in stdlib_funcs:
        combined[f[0]] = f
    combined_sorted = sorted(combined.values(), key=lambda x: x[1], reverse=True)

    for label, tt, ct, nc in combined_sorted[:5]:
        bottlenecks.append({
            "rank": None,
            "type": "Python",
            "description": label,
            "tottime_s": round(tt, 4),
            "cumtime_s": round(ct, 4),
            "pct_of_wall": round(100 * tt / wall_elapsed, 1),
            "ncalls": nc,
        })

    # Rank all candidates by impact
    bottlenecks.sort(key=lambda b: b.get("total_s") or b.get("tottime_s", 0), reverse=True)
    for i, b in enumerate(bottlenecks[:3], 1):
        b["rank"] = i

    top3 = bottlenecks[:3]

    print("=" * 72)
    print("TOP 3 BOTTLENECKS")
    print("=" * 72)
    for b in top3:
        print(f"\n  #{b['rank']}  [{b['type']}]  {b['description']}")
        for k, v in b.items():
            if k in ("rank", "type", "description"):
                continue
            print(f"      {k}: {v}")

    # ── Improvement opportunities ────────────────────────────────────────
    print(f"\n{'=' * 72}")
    print("ESTIMATED IMPROVEMENT OPPORTUNITIES")
    print("=" * 72)

    opportunities = []

    # Check for choose_best_lr_match N×M loop
    lr_match_funcs = [f for f in func_stats if "choose_best_lr_match" in f[0]]
    lr_match_time = sum(f[1] for f in lr_match_funcs)
    seq_matcher_funcs = [f for f in func_stats if "SequenceMatcher" in f[0] or "ratio" in f[0]]
    seq_matcher_time = sum(f[1] for f in seq_matcher_funcs)
    fuzzy_total = lr_match_time + seq_matcher_time
    if fuzzy_total > 0.01:
        opportunities.append({
            "area": "LR fuzzy matching (choose_best_lr_match + SequenceMatcher)",
            "current_s": round(fuzzy_total, 3),
            "pct_of_wall": round(100 * fuzzy_total / wall_elapsed, 1),
            "suggestion": "Pre-index LR names into normalized lookup dict; batch fuzzy only for non-exact residuals. "
                          "Potential 50-80% reduction of this segment.",
            "estimated_savings_s": f"{fuzzy_total * 0.5:.3f}-{fuzzy_total * 0.8:.3f}",
        })

    # Check for FTA trigram matching
    fta_funcs = [f for f in func_stats if "trigram" in f[0].lower()]
    fta_time = sum(f[1] for f in fta_funcs)
    if fta_time > 0.01:
        opportunities.append({
            "area": "FTA trigram similarity matching",
            "current_s": round(fta_time, 3),
            "pct_of_wall": round(100 * fta_time / wall_elapsed, 1),
            "suggestion": "Pre-compute trigram sets once; use inverted index (already partially done). "
                          "Potential 30-60% reduction.",
            "estimated_savings_s": f"{fta_time * 0.3:.3f}-{fta_time * 0.6:.3f}",
        })

    # Check for repeated normalize calls
    norm_funcs = [f for f in func_stats if "normalize" in f[0].lower() and f[2] > 0.005]
    norm_time = sum(f[1] for f in norm_funcs)
    if norm_time > 0.01:
        opportunities.append({
            "area": "Repeated normalization calls (normalize_for_compare, normalize_lr_name_for_match, etc.)",
            "current_s": round(norm_time, 3),
            "pct_of_wall": round(100 * norm_time / wall_elapsed, 1),
            "suggestion": "Memoize/pre-compute normalized LR names once before matching loop. "
                          "Potential 60-90% reduction of normalize overhead.",
            "estimated_savings_s": f"{norm_time * 0.6:.3f}-{norm_time * 0.9:.3f}",
        })

    # DB-side opportunities
    if sorted_queries:
        slowest_q = sorted_queries[0]
        if slowest_q["total_s"] > 0.1:
            opportunities.append({
                "area": f"Slowest DB query: {slowest_q['sample'][:60]}",
                "current_s": round(slowest_q["total_s"], 3),
                "pct_of_wall": round(100 * slowest_q["total_s"] / wall_elapsed, 1),
                "suggestion": "Batch operations where possible; ensure indexes on FK columns.",
                "estimated_savings_s": f"{slowest_q['total_s'] * 0.3:.3f}-{slowest_q['total_s'] * 0.6:.3f}",
            })

    # Check for lang file I/O
    lang_funcs = [f for f in func_stats if "lang" in f[0].lower() or "discover" in f[0].lower()]
    lang_time = sum(f[1] for f in lang_funcs)
    if lang_time > 0.05:
        opportunities.append({
            "area": "Lang-file discovery and loading (discover_lang_files + load_lang_alias_map)",
            "current_s": round(lang_time, 3),
            "pct_of_wall": round(100 * lang_time / wall_elapsed, 1),
            "suggestion": "Cache lang alias map to disk; skip filesystem walk if cache is fresh.",
            "estimated_savings_s": f"{lang_time * 0.7:.3f}-{lang_time * 0.9:.3f}",
        })

    for opp in opportunities:
        print(f"\n  * {opp['area']}")
        for k, v in opp.items():
            if k == "area":
                continue
            print(f"      {k}: {v}")

    if not opportunities:
        print("  (No significant improvement opportunities detected -- script is already fast.)")

    # ── Persist JSON report ──────────────────────────────────────────────
    report = {
        "wall_clock_s": round(wall_elapsed, 3),
        "db_time_s": round(db_total, 3),
        "python_time_s": round(python_total, 3),
        "db_pct": round(100 * db_total / wall_elapsed, 1),
        "python_pct": round(100 * python_total / wall_elapsed, 1),
        "query_stats": [
            {
                "sql": s["sample"],
                "count": s["count"],
                "total_s": round(s["total_s"], 4),
                "max_s": round(s["max_s"], 4),
                "mean_s": round(s["total_s"] / s["count"], 4) if s["count"] else 0,
                "rows_affected": s["rows_affected"],
            }
            for s in sorted_queries
        ],
        "top3_bottlenecks": top3,
        "improvement_opportunities": opportunities,
    }

    out_path = os.path.join("data", "profile_build_canonical.json")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"\nFull report saved to: {out_path}")


if __name__ == "__main__":
    run_profile()
