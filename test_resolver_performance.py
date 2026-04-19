#!/usr/bin/env python3
"""
Resolver Performance & Correctness Test Suite
==============================================
Tests /calculate resolver behaviour across item categories:
  - Simple items (direct LR price)
  - Complex multi-layer recipe items
  - Items with no LR price (recipe-only / unresolved)
  - Batch orders (multiple items in one call)

Measures:
  - Response time per call
  - Recursion depth (tree depth of breakdown)
  - Repeated subtrees (shared canonical_ids across breakdown)

Detects:
  - Slow (>500ms) responses
  - Inconsistent pricing between runs
  - Missing breakdown nodes (recipes with no ingredients)

Outputs:
  - Timings table
  - Correctness issues list
  - Performance risk summary
"""

import json
import os
import sys
import time
import statistics

from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from scripts.resolver import (
    parse_order_input,
    process_order,
    resolve_canonical_id,
    calculate_cost,
)

# ---------------------------------------------------------------------------
# Database connection helper
# ---------------------------------------------------------------------------

def get_db_connection():
    import psycopg2
    DATABASE_URL = os.getenv("DATABASE_URL")
    if DATABASE_URL:
        return psycopg2.connect(DATABASE_URL)
    db_name = os.getenv("DB_NAME") or os.getenv("PGDATABASE")
    if not db_name:
        raise RuntimeError("DATABASE_URL or DB_NAME/PGDATABASE must be set")
    return psycopg2.connect(
        host=os.getenv("DB_HOST") or os.getenv("PGHOST") or "localhost",
        port=int(os.getenv("DB_PORT") or os.getenv("PGPORT") or 5432),
        dbname=db_name,
        user=os.getenv("DB_USER") or os.getenv("PGUSER"),
        password=os.getenv("DB_PASSWORD") or os.getenv("PGPASSWORD"),
    )

# ---------------------------------------------------------------------------
# Tree analysis helpers
# ---------------------------------------------------------------------------

def measure_tree_depth(node, depth=0):
    """Return the maximum depth of the ingredient/breakdown tree."""
    if not isinstance(node, dict):
        return depth
    max_depth = depth
    # Check ingredients list
    ingredients = node.get("ingredients")
    if isinstance(ingredients, list):
        for ing in ingredients:
            max_depth = max(max_depth, measure_tree_depth(ing, depth + 1))
    # Check crafting_breakdown
    breakdown = node.get("crafting_breakdown")
    if isinstance(breakdown, dict):
        max_depth = max(max_depth, measure_tree_depth(breakdown, depth + 1))
    # Check recipe_alternative
    alt = node.get("recipe_alternative")
    if isinstance(alt, dict):
        max_depth = max(max_depth, measure_tree_depth(alt, depth + 1))
    return max_depth


def collect_canonical_ids(node, collector=None):
    """Collect all canonical_ids that appear in the tree, tracking counts."""
    if collector is None:
        collector = {}
    if not isinstance(node, dict):
        return collector
    cid = node.get("canonical_id")
    if cid:
        collector[cid] = collector.get(cid, 0) + 1
    ingredients = node.get("ingredients")
    if isinstance(ingredients, list):
        for ing in ingredients:
            collect_canonical_ids(ing, collector)
    breakdown = node.get("crafting_breakdown")
    if isinstance(breakdown, dict):
        collect_canonical_ids(breakdown, collector)
    alt = node.get("recipe_alternative")
    if isinstance(alt, dict):
        collect_canonical_ids(alt, collector)
    return collector


def find_missing_breakdown_nodes(node, path="root"):
    """Find recipe nodes that claim source=recipe but have no/empty ingredients."""
    issues = []
    if not isinstance(node, dict):
        return issues
    source = node.get("source")
    ingredients = node.get("ingredients")
    recipe_type = node.get("recipe_type")
    cid = node.get("canonical_id") or "?"
    
    if source == "recipe" and recipe_type is not None:
        if ingredients is None or (isinstance(ingredients, list) and len(ingredients) == 0):
            issues.append(f"{path}: {cid} source=recipe type={recipe_type} but ingredients={ingredients}")
    
    if isinstance(ingredients, list):
        for i, ing in enumerate(ingredients):
            issues.extend(find_missing_breakdown_nodes(ing, f"{path}.ingredients[{i}]"))
    
    breakdown = node.get("crafting_breakdown")
    if isinstance(breakdown, dict):
        issues.extend(find_missing_breakdown_nodes(breakdown, f"{path}.crafting_breakdown"))
    
    alt = node.get("recipe_alternative")
    if isinstance(alt, dict):
        issues.extend(find_missing_breakdown_nodes(alt, f"{path}.recipe_alternative"))
    
    return issues


def count_total_nodes(node):
    """Count total nodes in the result tree."""
    if not isinstance(node, dict):
        return 0
    count = 1
    ingredients = node.get("ingredients")
    if isinstance(ingredients, list):
        for ing in ingredients:
            count += count_total_nodes(ing)
    breakdown = node.get("crafting_breakdown")
    if isinstance(breakdown, dict):
        count += count_total_nodes(breakdown)
    alt = node.get("recipe_alternative")
    if isinstance(alt, dict):
        count += count_total_nodes(alt)
    return count


# ---------------------------------------------------------------------------
# Test case definitions
# ---------------------------------------------------------------------------

TEST_CASES = [
    # Category 1: Simple items (direct LR price, shallow or no recipe tree)
    {
        "label": "Simple: copper ingot",
        "order": "1 copper ingot",
        "category": "simple",
        "expect_source": "lr_price",
    },
    {
        "label": "Simple: iron ingot",
        "order": "1 iron ingot",
        "category": "simple",
        "expect_source": "lr_price",
    },
    {
        "label": "Simple: leather",
        "order": "1 leather",
        "category": "simple",
        "expect_source": "lr_price",
    },
    {
        "label": "Simple: bismuth bronze ingot",
        "order": "1 bismuth bronze ingot",
        "category": "simple",
        "expect_source": "lr_price",
    },

    # Category 2: Complex multi-layer recipe items
    {
        "label": "Complex: lantern up (grid, multi-ingredient, deep)",
        "order": "1 lantern up",
        "category": "complex",
        "expect_source": "recipe",
    },
    {
        "label": "Complex: plate body armor iron (multi-step smithing+chain)",
        "order": "1 plate body armor iron",
        "category": "complex",
        "expect_source": "lr_price",
    },
    {
        "label": "Complex: chest (grid with unresolved ingredient)",
        "order": "1 chest",
        "category": "complex",
        "expect_source": "recipe",
    },
    {
        "label": "Complex: candle (cooking, partial)",
        "order": "1 candle",
        "category": "complex",
        "expect_source": "recipe",
    },
    {
        "label": "Complex: tannin (barrel recipe, partial)",
        "order": "1 tannin",
        "category": "complex",
        "expect_source": "recipe",
    },

    # Category 3: Items with no LR price
    {
        "label": "No-LR: flint knife blade (knapping, unresolved ingredient)",
        "order": "1 flint knife blade",
        "category": "no_lr",
        "expect_source": "recipe",
    },
    {
        "label": "No-LR: flint arrowhead (knapping, unresolved)",
        "order": "1 flint arrowhead",
        "category": "no_lr",
        "expect_source": "recipe",
    },
    {
        "label": "No-LR: pickaxe head iron (smithing, recipe-priced)",
        "order": "1 pickaxe head iron",
        "category": "no_lr",
        "expect_source": "recipe",
    },

    # Category 4: Not-found item
    {
        "label": "Not-found: totally made up item",
        "order": "1 totallymadeupitemxyz",
        "category": "not_found",
        "expect_source": "not_found",
    },

    # Category 5: Batch order (comma-separated multi-item)
    {
        "label": "Batch: copper ingot + iron ingot + leather",
        "order": "2 copper ingot, 3 iron ingot, 1 leather",
        "category": "batch",
        "expect_sources": ["lr_price", "lr_price", "lr_price"],
    },
    {
        "label": "Batch: lantern up + candle + chest + tannin",
        "order": "1 lantern up, 1 candle, 1 chest, 1 tannin",
        "category": "batch",
        "expect_sources": ["recipe", "recipe", "recipe", "recipe"],
    },
    {
        "label": "Batch: mix of simple + complex + not_found",
        "order": "1 copper ingot, 1 lantern up, 1 totallymadeupitemxyz",
        "category": "batch",
        "expect_sources": ["lr_price", "recipe", "not_found"],
    },
]

NUM_CONSISTENCY_RUNS = 3
SLOW_THRESHOLD_MS = 500.0

# ---------------------------------------------------------------------------
# Main test runner
# ---------------------------------------------------------------------------

def run_single_test(test_case, conn):
    """Run a single test case and return detailed results."""
    order_text = test_case["order"]
    items = parse_order_input(order_text)
    
    start = time.perf_counter()
    result = process_order(items, "current", conn)
    elapsed_ms = (time.perf_counter() - start) * 1000.0
    
    return result, elapsed_ms


def analyze_result(test_case, result, elapsed_ms):
    """Analyze a single test result for correctness and performance."""
    analysis = {
        "label": test_case["label"],
        "category": test_case["category"],
        "elapsed_ms": round(elapsed_ms, 2),
        "is_slow": elapsed_ms > SLOW_THRESHOLD_MS,
        "issues": [],
        "tree_depth": 0,
        "total_nodes": 0,
        "repeated_subtrees": [],
        "missing_breakdowns": [],
    }
    
    result_items = result.get("items", [])
    
    # Source check
    if "expect_source" in test_case:
        if len(result_items) == 1:
            actual_source = result_items[0].get("source")
            if actual_source != test_case["expect_source"]:
                analysis["issues"].append(
                    f"Expected source={test_case['expect_source']}, got source={actual_source}"
                )
        elif len(result_items) == 0:
            analysis["issues"].append("No items returned")
    
    if "expect_sources" in test_case:
        expected = test_case["expect_sources"]
        actual_sources = [item.get("source") for item in result_items]
        if len(actual_sources) != len(expected):
            analysis["issues"].append(
                f"Expected {len(expected)} items, got {len(actual_sources)}"
            )
        else:
            for i, (exp, act) in enumerate(zip(expected, actual_sources)):
                if exp != act:
                    analysis["issues"].append(
                        f"Item[{i}]: expected source={exp}, got source={act}"
                    )
    
    # Tree analysis per item
    max_depth = 0
    total_nodes = 0
    all_cids = {}
    all_missing = []
    
    for item in result_items:
        depth = measure_tree_depth(item)
        max_depth = max(max_depth, depth)
        total_nodes += count_total_nodes(item)
        collect_canonical_ids(item, all_cids)
        all_missing.extend(find_missing_breakdown_nodes(item))
    
    analysis["tree_depth"] = max_depth
    analysis["total_nodes"] = total_nodes
    analysis["repeated_subtrees"] = [
        {"canonical_id": cid, "count": cnt}
        for cid, cnt in sorted(all_cids.items(), key=lambda x: -x[1])
        if cnt > 1
    ]
    analysis["missing_breakdowns"] = all_missing
    
    if all_missing:
        for mb in all_missing:
            analysis["issues"].append(f"Missing breakdown: {mb}")
    
    return analysis


def run_consistency_check(test_case, conn, num_runs):
    """Run a test case multiple times and check pricing consistency."""
    prices = []
    timings = []
    
    for _ in range(num_runs):
        result, elapsed_ms = run_single_test(test_case, conn)
        timings.append(elapsed_ms)
        
        items = result.get("items", [])
        # Collect total_combined and per-item prices
        total_combined = result.get("totals", {}).get("total_combined")
        item_prices = [(item.get("canonical_id"), item.get("unit_cost")) for item in items]
        prices.append({"total_combined": total_combined, "item_prices": item_prices})
    
    inconsistencies = []
    
    # Check total_combined consistency
    totals = [p["total_combined"] for p in prices]
    unique_totals = set(str(t) for t in totals)
    if len(unique_totals) > 1:
        inconsistencies.append(f"total_combined varied across runs: {totals}")
    
    # Check per-item unit_cost consistency
    for idx in range(len(prices[0]["item_prices"])):
        per_run_costs = []
        for run_prices in prices:
            if idx < len(run_prices["item_prices"]):
                per_run_costs.append(run_prices["item_prices"][idx][1])
        unique_costs = set(str(c) for c in per_run_costs)
        if len(unique_costs) > 1:
            cid = prices[0]["item_prices"][idx][0] if prices[0]["item_prices"] else "?"
            inconsistencies.append(f"item[{idx}] ({cid}) unit_cost varied: {per_run_costs}")
    
    return timings, inconsistencies


def main():
    print("=" * 80)
    print("RESOLVER PERFORMANCE & CORRECTNESS TEST SUITE")
    print("=" * 80)
    print()
    
    conn = get_db_connection()
    
    all_analyses = []
    all_consistency_issues = []
    all_timings_per_case = {}
    
    # -----------------------------------------------------------------------
    # Phase 1: Single-run correctness + timing + tree analysis
    # -----------------------------------------------------------------------
    print("Phase 1: Single-run correctness & timing analysis")
    print("-" * 60)
    
    for tc in TEST_CASES:
        try:
            result, elapsed_ms = run_single_test(tc, conn)
            analysis = analyze_result(tc, result, elapsed_ms)
            all_analyses.append(analysis)
            
            status = "SLOW" if analysis["is_slow"] else "OK"
            issues_flag = f" [{len(analysis['issues'])} issues]" if analysis["issues"] else ""
            print(f"  [{status:4s}] {elapsed_ms:8.1f}ms  depth={analysis['tree_depth']}  nodes={analysis['total_nodes']:3d}  "
                  f"repeats={len(analysis['repeated_subtrees'])}  {tc['label']}{issues_flag}")
        except Exception as e:
            print(f"  [ERR ] {tc['label']}: {e}")
            all_analyses.append({
                "label": tc["label"],
                "category": tc["category"],
                "elapsed_ms": None,
                "is_slow": False,
                "issues": [f"Exception: {e}"],
                "tree_depth": 0,
                "total_nodes": 0,
                "repeated_subtrees": [],
                "missing_breakdowns": [],
            })
    
    print()
    
    # -----------------------------------------------------------------------
    # Phase 2: Multi-run consistency check
    # -----------------------------------------------------------------------
    print(f"Phase 2: Consistency check ({NUM_CONSISTENCY_RUNS} runs per case)")
    print("-" * 60)
    
    for tc in TEST_CASES:
        try:
            timings, inconsistencies = run_consistency_check(tc, conn, NUM_CONSISTENCY_RUNS)
            all_timings_per_case[tc["label"]] = timings
            
            if inconsistencies:
                all_consistency_issues.append({"label": tc["label"], "issues": inconsistencies})
                print(f"  [WARN] {tc['label']}: {len(inconsistencies)} inconsistencies")
                for issue in inconsistencies:
                    print(f"         - {issue}")
            else:
                avg_ms = statistics.mean(timings)
                std_ms = statistics.stdev(timings) if len(timings) > 1 else 0.0
                print(f"  [ OK ] {tc['label']}: avg={avg_ms:.1f}ms stddev={std_ms:.1f}ms  (consistent)")
        except Exception as e:
            print(f"  [ERR ] {tc['label']}: {e}")
    
    print()
    
    # -----------------------------------------------------------------------
    # Output: Summary report
    # -----------------------------------------------------------------------
    print("=" * 80)
    print("RESULTS SUMMARY")
    print("=" * 80)
    print()
    
    # --- Timings table ---
    print("TIMINGS")
    print("-" * 80)
    print(f"  {'Test Case':<58s} {'Single':>8s}  {'Avg':>8s}  {'StdDev':>8s}")
    print(f"  {'-'*58}  {'-'*8}  {'-'*8}  {'-'*8}")
    
    for analysis in all_analyses:
        label = analysis["label"]
        single_ms = analysis.get("elapsed_ms")
        single_str = f"{single_ms:.1f}ms" if single_ms is not None else "ERROR"
        
        timings = all_timings_per_case.get(label, [])
        if timings:
            avg_ms = statistics.mean(timings)
            std_ms = statistics.stdev(timings) if len(timings) > 1 else 0.0
            avg_str = f"{avg_ms:.1f}ms"
            std_str = f"{std_ms:.1f}ms"
        else:
            avg_str = "N/A"
            std_str = "N/A"
        
        slow_marker = " ***SLOW***" if analysis.get("is_slow") else ""
        print(f"  {label:<58s} {single_str:>8s}  {avg_str:>8s}  {std_str:>8s}{slow_marker}")
    
    print()
    
    # --- Correctness issues ---
    print("CORRECTNESS ISSUES")
    print("-" * 80)
    any_issues = False
    for analysis in all_analyses:
        if analysis["issues"]:
            any_issues = True
            print(f"  {analysis['label']}:")
            for issue in analysis["issues"]:
                print(f"    - {issue}")
    
    if all_consistency_issues:
        any_issues = True
        print()
        print("  Consistency issues (pricing varied between runs):")
        for ci in all_consistency_issues:
            print(f"    {ci['label']}:")
            for issue in ci["issues"]:
                print(f"      - {issue}")
    
    if not any_issues:
        print("  No correctness issues detected.")
    
    print()
    
    # --- Performance risks ---
    print("PERFORMANCE RISKS")
    print("-" * 80)
    
    slow_cases = [a for a in all_analyses if a.get("is_slow")]
    deep_cases = [a for a in all_analyses if a.get("tree_depth", 0) >= 4]
    high_node_cases = [a for a in all_analyses if a.get("total_nodes", 0) >= 20]
    repeated_cases = [a for a in all_analyses if len(a.get("repeated_subtrees", [])) > 0]
    missing_breakdown_cases = [a for a in all_analyses if len(a.get("missing_breakdowns", [])) > 0]
    
    if slow_cases:
        print(f"  SLOW RESPONSES (>{SLOW_THRESHOLD_MS}ms):")
        for sc in slow_cases:
            print(f"    - {sc['label']}: {sc['elapsed_ms']}ms")
    else:
        print(f"  No responses exceeded {SLOW_THRESHOLD_MS}ms threshold.")
    
    print()
    
    if deep_cases:
        print(f"  DEEP RECURSION (depth >= 4):")
        for dc in deep_cases:
            print(f"    - {dc['label']}: depth={dc['tree_depth']}")
    else:
        print(f"  No cases with recursion depth >= 4.")
    
    print()
    
    if high_node_cases:
        print(f"  HIGH NODE COUNT (>= 20 nodes):")
        for hnc in high_node_cases:
            print(f"    - {hnc['label']}: {hnc['total_nodes']} nodes")
    else:
        print(f"  No cases with >= 20 tree nodes.")
    
    print()
    
    if repeated_cases:
        print(f"  REPEATED SUBTREES (same canonical_id appears multiple times):")
        for rc in repeated_cases:
            repeats = rc["repeated_subtrees"]
            top_repeats = repeats[:5]
            print(f"    - {rc['label']}:")
            for r in top_repeats:
                print(f"        {r['canonical_id']} x{r['count']}")
    else:
        print(f"  No repeated subtrees detected.")
    
    print()
    
    if missing_breakdown_cases:
        print(f"  MISSING BREAKDOWN NODES:")
        for mbc in missing_breakdown_cases:
            print(f"    - {mbc['label']}:")
            for mb in mbc["missing_breakdowns"]:
                print(f"        {mb}")
    else:
        print(f"  No missing breakdown nodes.")
    
    print()
    
    # --- Overall verdict ---
    print("=" * 80)
    total_issues = sum(len(a["issues"]) for a in all_analyses) + len(all_consistency_issues)
    total_slow = len(slow_cases)
    print(f"VERDICT: {len(all_analyses)} tests | {total_issues} issues | {total_slow} slow | "
          f"{len(all_consistency_issues)} consistency failures")
    print("=" * 80)
    
    # Save full results to JSON
    output = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "threshold_ms": SLOW_THRESHOLD_MS,
        "consistency_runs": NUM_CONSISTENCY_RUNS,
        "summary": {
            "total_tests": len(all_analyses),
            "total_issues": total_issues,
            "slow_count": total_slow,
            "consistency_failures": len(all_consistency_issues),
        },
        "analyses": [],
        "consistency_issues": all_consistency_issues,
        "timings_per_case": {
            label: [round(t, 2) for t in timings]
            for label, timings in all_timings_per_case.items()
        },
    }
    
    for analysis in all_analyses:
        output["analyses"].append({
            "label": analysis["label"],
            "category": analysis["category"],
            "elapsed_ms": analysis["elapsed_ms"],
            "is_slow": analysis["is_slow"],
            "tree_depth": analysis["tree_depth"],
            "total_nodes": analysis["total_nodes"],
            "repeated_subtrees": analysis["repeated_subtrees"],
            "missing_breakdowns": analysis["missing_breakdowns"],
            "issues": analysis["issues"],
        })
    
    output_path = os.path.join("data", "resolver_perf_test_results.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    print(f"\nFull results saved to: {output_path}")
    
    conn.close()
    
    # Exit with non-zero if issues found
    sys.exit(1 if total_issues > 0 else 0)


if __name__ == "__main__":
    main()
