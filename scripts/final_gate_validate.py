#!/usr/bin/env python3
"""[MEMORY BANK: ACTIVE]
Final validation gate checks for requested recipe-pricing cases.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

# [MEMORY BANK: ACTIVE]
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from api.app import app


@dataclass
class Case:
    label: str
    order: str
    material: str | None = None
    expected_source: str | None = "recipe"
    expected_recipe_type: str | None = None
    expected_top_ingredients: dict[str, float] | None = None
    allow_null_cost: bool = False
    allowed_sources: set[str] | None = None
    flexible_grid_or_lr_price: bool = False
    minimal_spot_check: bool = False


CASES: list[Case] = [
    Case(
        label="Grid: lantern up (iron)",
        order="1 lantern up",
        material="iron",
        expected_source="recipe",
        expected_recipe_type="grid",
        # Intent check: should include metalplate-iron path, not tinbronze.
        expected_top_ingredients={
            "metalplate_iron": 1.0,
            "glassslab_plain_down_free": 2.0,
            "candle": 1.0,
        },
    ),
    Case(
        label="Grid: chest",
        order="1 chest",
        expected_source="recipe",
        expected_recipe_type="grid",
    ),
    Case(
        label="Smithing: metal plate iron",
        order="1 metal plate iron",
        expected_source="lr_price",
        expected_recipe_type="smithing",
        expected_top_ingredients={"ingot_iron": 2.0},
    ),
    Case(
        label="Smithing: pickaxe head iron",
        order="1 pickaxe head iron",
        expected_source="recipe",
        expected_recipe_type="smithing",
    ),
    Case(
        label="Barrel: leather",
        order="1 leather",
        expected_source=None,
        allowed_sources={"recipe", "lr_price"},
        flexible_grid_or_lr_price=True,
    ),
    Case(
        label="Cooking: candle",
        order="1 candle",
        expected_source="recipe",
        expected_recipe_type="cooking",
        expected_top_ingredients={"beeswax": 3.0, "flaxfibers": 1.0},
    ),
    Case(
        label="Alloy: tin bronze ingot",
        order="1 tin bronze ingot",
        expected_source="lr_price",
        expected_recipe_type="alloy",
        expected_top_ingredients={"ingot_tin": 0.1, "ingot_copper": 0.9},
    ),
    Case(
        label="Knapping: flint knife blade",
        order="1 flint knife blade",
        expected_source="recipe",
        expected_recipe_type="knapping",
        allow_null_cost=True,
    ),
    Case(
        label="Multi-step: plate body armor iron",
        order="1 plate body armor iron",
        expected_source=None,
        allowed_sources={"recipe", "lr_price"},
        flexible_grid_or_lr_price=True,
    ),
    Case(
        label="Spot: bismuth bronze ingot",
        order="1 bismuth bronze ingot",
        expected_source=None,
        minimal_spot_check=True,
    ),
    Case(
        label="Spot: copper ingot",
        order="1 copper ingot",
        expected_source=None,
        minimal_spot_check=True,
    ),
    Case(
        label="Spot: flint arrowhead",
        order="1 flint arrowhead",
        expected_source=None,
        minimal_spot_check=True,
        allow_null_cost=True,
    ),
    Case(
        label="Spot: iron axe head",
        order="1 iron axe head",
        expected_source=None,
        minimal_spot_check=True,
    ),
    Case(
        label="Spot: tannin",
        order="1 tannin",
        expected_source=None,
        minimal_spot_check=True,
    ),
    Case(
        label="Spot: iron ingot",
        order="1 iron ingot",
        expected_source=None,
        minimal_spot_check=True,
    ),
]


def _to_float(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _check_case(client, case: Case) -> dict[str, Any]:
    request_payload: dict[str, Any] = {
        "order": case.order,
        "settlement_type": "current",
    }
    if case.material:
        request_payload["material"] = case.material

    response = client.post(
        "/calculate",
        json=request_payload,
    )
    data = response.get_json(silent=True) or {}
    item = ((data.get("items") or [{}])[0]) if isinstance(data, dict) else {}
    primary_ingredients = item.get("ingredients") or []
    crafting_breakdown = item.get("crafting_breakdown") or {}
    crafting_ingredients = crafting_breakdown.get("ingredients") if isinstance(crafting_breakdown, dict) else None
    ingredients = (
        crafting_ingredients
        if isinstance(crafting_ingredients, list) and len(crafting_ingredients) > 0
        else primary_ingredients
    )

    failures: list[str] = []

    if response.status_code != 200:
        failures.append(f"HTTP status {response.status_code}")

    source = item.get("source")

    if case.minimal_spot_check:
        if source is None:
            failures.append("source is None")
        elif source == "unresolved":
            failures.append("source should not be unresolved")
        unit_cost = _to_float(item.get("unit_cost"))
        if source in {"lr_price", "recipe"}:
            if unit_cost is None:
                if not case.allow_null_cost:
                    failures.append("unit_cost is null/non-numeric for priced source")
            elif unit_cost <= 0:
                failures.append("unit_cost must be positive for priced source")

        recipe_type = item.get("recipe_type")
        total_cost = _to_float(item.get("total_cost"))
        ingredients = item.get("ingredients") or []

        return {
            "label": case.label,
            "order": case.order,
            "status_code": response.status_code,
            "source": source,
            "recipe_type": recipe_type,
            "unit_cost": unit_cost,
            "total_cost": total_cost,
            "is_partial": bool(item.get("is_partial")),
            "completeness_ratio": _to_float(item.get("completeness_ratio")),
            "top_level_ingredients": [
                {
                    "canonical_id": ing.get("canonical_id"),
                    "display_name": ing.get("display_name"),
                    "quantity": _to_float(ing.get("quantity")),
                    "unit_cost": _to_float(ing.get("unit_cost")),
                    "total_cost": _to_float(ing.get("total_cost")),
                    "source": ing.get("source"),
                    "is_partial": bool(ing.get("is_partial")),
                }
                for ing in ingredients
            ],
            "failures": failures,
            "passed": not failures,
        }

    if case.allowed_sources is not None:
        if source not in case.allowed_sources:
            failures.append(f"source expected one of {sorted(case.allowed_sources)}, got {source}")
    elif case.expected_source is not None and source != case.expected_source:
        failures.append(f"source expected {case.expected_source}, got {source}")

    if case.flexible_grid_or_lr_price:
        recipe_type = item.get("recipe_type")
        unit_cost = _to_float(item.get("unit_cost"))
        total_cost = _to_float(item.get("total_cost"))
        if unit_cost is None or unit_cost <= 0:
            failures.append("unit_cost must be non-null positive")
        if total_cost is None or total_cost <= 0:
            failures.append("total_cost must be non-null positive")
        if source == "recipe":
            if recipe_type != "grid":
                failures.append(f"recipe_type expected grid for recipe source, got {recipe_type}")
            if not isinstance(ingredients, list) or len(ingredients) == 0:
                failures.append("missing top-level ingredient breakdown for recipe source")

        return {
            "label": case.label,
            "order": case.order,
            "status_code": response.status_code,
            "source": source,
            "recipe_type": recipe_type,
            "unit_cost": unit_cost,
            "total_cost": total_cost,
            "is_partial": bool(item.get("is_partial")),
            "completeness_ratio": _to_float(item.get("completeness_ratio")),
            "top_level_ingredients": [
                {
                    "canonical_id": ing.get("canonical_id"),
                    "display_name": ing.get("display_name"),
                    "quantity": _to_float(ing.get("quantity")),
                    "unit_cost": _to_float(ing.get("unit_cost")),
                    "total_cost": _to_float(ing.get("total_cost")),
                    "source": ing.get("source"),
                    "is_partial": bool(ing.get("is_partial")),
                }
                for ing in ingredients
            ],
            "failures": failures,
            "passed": not failures,
        }

    recipe_type = item.get("recipe_type") or (
        crafting_breakdown.get("recipe_type") if isinstance(crafting_breakdown, dict) else None
    )
    if case.expected_recipe_type and recipe_type != case.expected_recipe_type:
        failures.append(
            f"recipe_type expected {case.expected_recipe_type}, got {recipe_type}"
        )

    if not isinstance(ingredients, list) or len(ingredients) == 0:
        failures.append("missing top-level ingredient breakdown")

    unit_cost = _to_float(item.get("unit_cost"))
    total_cost = _to_float(item.get("total_cost"))
    if not case.allow_null_cost:
        if unit_cost is None:
            failures.append("unit_cost is null/non-numeric")
        elif unit_cost == 0:
            failures.append("unit_cost is zero")
        if total_cost is None:
            failures.append("total_cost is null/non-numeric")
        elif total_cost == 0:
            failures.append("total_cost is zero")

    ing_map = {ing.get("canonical_id"): _to_float(ing.get("quantity")) for ing in ingredients}
    if case.expected_top_ingredients:
        for canonical_id, expected_qty in case.expected_top_ingredients.items():
            got = ing_map.get(canonical_id)
            if got is None:
                failures.append(f"missing ingredient {canonical_id}")
            elif abs(got - expected_qty) > 1e-9:
                failures.append(
                    f"ingredient {canonical_id} qty expected {expected_qty}, got {got}"
                )

    return {
        "label": case.label,
        "order": case.order,
        "status_code": response.status_code,
        "source": source,
        "recipe_type": recipe_type,
        "unit_cost": unit_cost,
        "total_cost": total_cost,
        "is_partial": bool(item.get("is_partial")),
        "completeness_ratio": _to_float(item.get("completeness_ratio")),
        "top_level_ingredients": [
            {
                "canonical_id": ing.get("canonical_id"),
                "display_name": ing.get("display_name"),
                "quantity": _to_float(ing.get("quantity")),
                "unit_cost": _to_float(ing.get("unit_cost")),
                "total_cost": _to_float(ing.get("total_cost")),
                "source": ing.get("source"),
                "is_partial": bool(ing.get("is_partial")),
            }
            for ing in ingredients
        ],
        "failures": failures,
        "passed": not failures,
    }


def main() -> int:
    client = app.test_client()
    run_timestamp = datetime.now().isoformat(timespec="seconds")
    baseline_path = Path("data/final_gate_baseline.json")

    previous_baseline: dict[str, Any] = {}
    if baseline_path.exists():
        try:
            previous_baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
        except Exception:
            previous_baseline = {}

    previous_cases = {
        entry.get("label"): entry
        for entry in (previous_baseline.get("cases") or [])
        if isinstance(entry, dict)
    }

    results = [_check_case(client, case) for case in CASES]
    for result in results:
        prev = previous_cases.get(result["label"], {})
        prev_passed = bool(prev.get("passed", False)) if isinstance(prev, dict) else False
        result["regression"] = bool(prev_passed and not result["passed"])

    failures = [r for r in results if not r["passed"]]
    regressions = [r for r in results if r.get("regression")]

    payload = {
        "timestamp": run_timestamp,
        "summary": {
            "total": len(results),
            "passed": len(results) - len(failures),
            "failed": len(failures),
            "regressions": len(regressions),
        },
        "results": results,
    }

    out_json = Path("data/final_gate_validation.json")
    out_txt = Path("data/final_gate_validation.txt")
    out_json.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    lines = [
        f"Run Timestamp: {run_timestamp}",
        "Final Validation Gate",
        f"Passed {payload['summary']['passed']} / {payload['summary']['total']}",
        f"Regressions: {payload['summary']['regressions']}",
        "",
    ]
    for result in results:
        marker = "PASS" if result["passed"] else "FAIL"
        if result.get("regression"):
            marker = "REGRESSION"
        lines.append(f"[{marker}] {result['label']} ({result['order']})")
        lines.append(
            f"  status={result['status_code']} source={result['source']} recipe_type={result['recipe_type']} "
            f"unit={result['unit_cost']} total={result['total_cost']} partial={result['is_partial']}"
        )
        lines.append(
            "  top_ingredients="
            + ", ".join(
                f"{ing['canonical_id']} x{ing['quantity']}"
                for ing in result["top_level_ingredients"]
            )
        )
        if result["failures"]:
            for failure in result["failures"]:
                lines.append(f"  - {failure}")
        lines.append("")

    lines.append("Regression Baseline Snapshot")
    lines.append(f"Timestamp: {run_timestamp}")
    for result in results:
        status = "PASS" if result["passed"] else "FAIL"
        if result.get("regression"):
            status = "REGRESSION"
        lines.append(
            f"- {result['label']}: {status} | source={result['source']} | "
            f"recipe_type={result['recipe_type']} | unit_cost={result['unit_cost']}"
        )

    run_block = "\n".join(lines)
    if out_txt.exists() and out_txt.read_text(encoding="utf-8").strip():
        out_txt.write_text(out_txt.read_text(encoding="utf-8") + "\n\n" + run_block, encoding="utf-8")
    else:
        out_txt.write_text(run_block, encoding="utf-8")

    baseline_payload = {
        "timestamp": run_timestamp,
        "summary": payload["summary"],
        "cases": [
            {
                "label": result["label"],
                "order": result["order"],
                "passed": result["passed"],
                "source": result["source"],
                "recipe_type": result["recipe_type"],
                "unit_cost": result["unit_cost"],
            }
            for result in results
        ],
    }
    baseline_path.write_text(
        json.dumps(baseline_payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print(str(out_txt))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
