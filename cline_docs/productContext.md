# Product Context

## Purpose
Price Vintage Story items and orders in Copper Sovereigns using canonical item identity, LR market data, manual/computed overrides, and recipe decomposition.

## Core Pricing Workflow (AUTHORITATIVE ORDER)
1. Resolve user input to canonical item ID.
2. Check LR direct market price — use immediately if present.
3. Check manual/computed override.
4. Evaluate recipe decomposition.
5. Use the cheapest valid non-partial result between override and recipe when LR is absent.

## Key Design Decisions
- User selects metal variant / recipe choice before or after calculation — resolver surfaces valid options and does not auto-select.
- Tools are non-consumed and excluded at ingestion; resolver never prices tool usage.
- Reverse/deconstruction recipe contamination is handled by targeted DB cleanup of known-bad rows (not broad recipe-class filtering).
- LR `Current Price` column is authoritative market input.
- Computed primitive and special-case pricing rules are pipeline-managed, not ad-hoc.

## Armor Set Policy (Current)
- Do **not** duplicate canonical entries for set-vs-piece behavior.
- Individual armor pieces are priced via recipe decomposition.
- Full armor sets are priced via manual LR links in `scripts/apply_manual_lr_links.py` mapped to LR set rows.
- Resulting UX: searching a full set returns LR set price; searching a specific piece returns crafting cost.

## Scope
- Active runtime: `api/app.py` + `scripts/resolver.py`
- Authoritative data path: JSON recipe ingestion + canonical pipeline + manual LR linking
- Out of scope: pipeleaf, `br_schematic_banner`, `cartschematics_carts` (admin/schematic items)

## Current Project Status (2026-04-20)
- Resolver hardened: precedence and cycle handling corrected.
- `crafting_breakdown` partial-flag bug fixed.
- `_is_reverse_recipe` broad general filter was removed after regressions (rope/flaxtwine breakage).
- Known bad reverse recipes are addressed via targeted DB deletion.
- Pricing updates in place: anvils (10× ingot), metalnailsandstrips (ingot/4), gear_rusty (5 CS), pelts (0.8× prepared hide LR), crushed/powdered materials.
- Dynamic hoops rule was tested and removed as unnecessary (recipe behavior already correct).
- UI cleanup complete: FTA/Guild removed, Set Price badge, loading skeleton, spacing fix, partial-cost badge fix.
- Railway workflow established: code deploy via GitHub + DB sync using `scripts/sync_railway.py` (partial sync script included).
