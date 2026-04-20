# Product Context

## Purpose
Price Vintage Story items and orders in Copper Sovereigns using canonical item identity,
empire market (LR) data, and recipe decomposition.

## Core Pricing Workflow (AUTHORITATIVE ORDER)
1. Resolve user input to canonical item ID.
2. Check LR direct market price — use immediately if present.
3. Check manual/computed override — use if present and recipe is worse or absent.
4. Fall back to recipe decomposition only when neither LR nor override exists or recipe is cheaper.

## Key Design Decisions
- User selects metal variant / recipe choice before or after cost calculation — resolver surfaces all valid options, does not auto-select.
- Tools in recipes are non-consumed and invisible to pricing (excluded at ingestion).
- Deconstruction recipes are excluded from pricing traversal.
- LR "Current Price" column is the authoritative market input — updated weekly.
- Computed primitive pricing is pipeline-managed, not ad-hoc.

## Scope
- Active runtime: `api/app.py` + `scripts/resolver.py`
- Authoritative data: JSON recipe ingestion + canonical pipeline
- Out of scope: pipeleaf, br_schematic_banner, cartschematics_carts (admin/schematic items)

## Current Project Status (2026-04-19)
- Resolver priority order corrected (override now evaluated before recipe).
- isTool flag confirmed present in game JSON and handled correctly at ingestion.
- Pricing rules expanded and corrected: dynamic hoops (all metals), dynamic anvils (all metals, 10× ingot), dynamic metalnailsandstrips (ingot/4), gear_rusty flat 5.0 CS, and sand/soil exclusion bug fix.
- UI cleanup completed: FTA/Guild Price removed, Manual Override badge renamed to Set Price, partial warning simplified, applySuggestion spacing fixed, loading skeleton added.
- Audit script still uses independent logic — rewrite to call resolver is pending.
- Open blocker: `parse_recipes_json.py` currently stores wrong `output_qty` for multi-output smithing/casting recipes (e.g. bighook), which blocks safe rollout of Section 6 rule families (pelts/crushed/powdered/hooks).
