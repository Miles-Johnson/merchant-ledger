# Progress

## Complete
- Consolidated architecture to **Gen 3 as sole active runtime path**.
- Activated direct JSON parser pipeline (`parse_recipes_json.py`) and retired legacy parse path from active runbook.
- Implemented recipe-family semantics across grid/smithing/knapping/clayforming/alloy/barrel/cooking with unknown-type fallback handling.
- Stabilized canonical linking and kept recipe output unlinked count at zero in validated runs.
- Added/maintained manual pricing correction flows (nuggets, processed ore chain).
- Implemented final validation gate + baseline regression tracking.

## Current State
- Core system is functional end-to-end through pipeline + API.
- Historical implementation detail is preserved in deprecated memory files.
- Core memory bank now focused on active truth, not historical play-by-play.

## Remaining High-Value Work
1. Resolve deterministic variant intent for `lantern up (iron)`.
2. Continue reducing unresolved ingredient count where economically meaningful.
3. Keep final-gate pass rate stable after any parser/resolver/linking changes.

## Operational Acceptance Checks
- Run pipeline: `python run_pipeline.py`
- Run gate: `python scripts/final_gate_validate.py`
- Confirm no regressions in `data/final_gate_validation.json`.

## Historical Material
Detailed milestone timeline moved to:
- `cline_docs/deprecated/progress_historical.md`

## Update (2026-04-06): Nugget/Bit Pricing + Linking Corrections

### Completed in This Pass
- Applied targeted implementation in `scripts/apply_manual_lr_links.py` only (per scope constraint).
- Added deterministic correction flow for fragment economics:
  - `item:metalbit-%` override generation from ingot price (`/20`) with note `auto:metalbit_from_ingot`.
  - `item:nugget-%` override generation from ingot price (`/20`) with note `auto:nugget_from_ingot`.
- Added missing nugget canonical materialization from priced ingots, including variant metadata for family/material grouping.
- Added display-name normalization from lang aliases plus nugget fallback naming.
- Added guard fix that unlinks incorrect exact metalbit→LR ingot matches while preserving manual mappings.
- Rebuilt aliases after canonical additions to keep search discoverability aligned with pricing corrections.

### Validated Outcomes
- Post-fix safety check succeeded: no exact `item:metalbit-%` canonicals remain linked to LR ingot rows.
- `/calculate` spot checks now return expected ingot/20 values for representative bits and nuggets.
- Searchability for bits/nuggets confirmed via alias coverage counts after alias rebuild.
- Final gate run completed with `Regressions: 0`; latest run snapshot in current DB context is `Passed 4/15`.

### Remaining / Follow-Up
1. Investigate broad final-gate degradation (`4/15`) outside nugget/bit fix scope.
2. Retain regression discipline (gate + baseline) when addressing unrelated failing checks.

## Update (2026-04-06): Dual-Price Presentation Refactor

### Completed in This Pass
- Implemented dual-price response model in active resolver path (`scripts/resolver.py`):
  - Primary pricing precedence now explicit: LR first, FTA fallback, recipe fallback.
  - Added `crafting_cost` (supplementary recipe-derived unit cost) alongside primary `unit_cost`.
  - Added `crafting_breakdown` for recipe ingredients when craft path is calculable.
- Removed alloy/cooking forced-recipe early-return logic so LR price can remain primary while still exposing craft economics.
- Enforced current-price-only LR lookup semantics (`unit_price_current`) for this task pass.
- Updated UI table (`webapp/src/App.jsx`) to show **Empire Price** and **Crafting Cost** columns simultaneously.
- Updated final-gate checker to evaluate alloy/recipe ingredient expectations against `crafting_breakdown` when primary source is LR.

### Validation Outcome (Current DB State)
- Target checks verified through resolver output:
  - `384 brass` shows LR primary + crafting cost present.
  - `1 iron ingot` shows LR primary.
  - `1 tin bronze ingot` shows LR primary + crafting cost present.
  - `1 iron pickaxe head` shows recipe primary.
  - `1 candle` shows recipe primary.
- Final gate currently reports **13/15**, **Regressions: 0**.
- Notable caveat: user-provided expected numeric LR values (e.g., brass 8.00 / tin bronze 6.00) do not match current DB snapshot values resolved by runtime (`7.00` / `5.00` respectively).

### Remaining / Follow-Up
1. Investigate DB-side LR current-price mismatch vs expected brass/tin-bronze values if those numbers are intended to be authoritative.
2. Continue lantern variant intent work (`Grid: lantern up (iron)`) and restore gate toward prior 14/15+ baseline.

## Update (2026-04-06): LR Non-Tiered Column Offset Fix + Validation

### Completed in This Pass
- Fixed LR non-tiered ingestion mapping in `scripts/ingest_lr_prices.py`:
  - `price_current` shifted from col `5` -> `6`
  - settlement columns shifted from `6..11` -> `7..12`
  - applied in both non-tiered `parse_standard_row()` and non-tiered `parse_artisanal_row()`
- Left tiered parsing paths unchanged (already correct).
- Added header drift warning guard (`warn_if_current_price_header_shifted`) and wired it into `parse_rows()` to detect future sheet-layout changes.
- Re-ran required data refresh sequence without canonical/alias rebuild:
  1. `python scripts/ingest_lr_prices.py`
  2. `python scripts/ingest_fta_prices.py`
  3. `python scripts/apply_manual_lr_links.py`
  4. `python scripts/link_recipes.py`

### Validated Outcomes
- DB spot check now matches expected current prices:
  - `IN002 Brass=8`
  - `IN003 Copper=6`
  - `IN007 Iron=8`
  - `IN016 Tin Bronze=6`
  - `IN017 Black Bronze=9`
- `unit_price_current` values align with corrected `price_current` values for those rows.
- Settlement alignment check (`IN007`) confirmed:
  - `price_current=8`, `price_industrial_town=10`, `price_market_town=5`.
- Runtime/API checks confirm corrected LR-primary pricing:
  - `1 iron ingot` -> `8.0`
  - `1 brass ingot` -> `8.0` (with crafting cost present)
  - `1 copper ingot` -> `6.0`
- Final gate latest run: **14/15**, **Regressions: 0**.

### Remaining / Follow-Up
1. Keep monitoring mixed sheet header layouts (agricultural sheet currently reports `Current Price` at index `5`).
2. Continue work on known remaining fail: `Grid: lantern up (iron)` variant intent.

## Update (2026-04-06): Header-Detected Non-Tiered LR Mapping Fix

### Completed in This Pass
- Replaced hardcoded non-tiered standard price offsets in `scripts/ingest_lr_prices.py` with header-based detection:
  - Added `detect_standard_price_col_map()` for `Current Price` + settlement columns.
  - Updated `parse_standard_row()` non-tiered branch to consume detected index map.
- Added section-consistency guard for repeated headers:
  - First matching section header is canonical.
  - Subsequent section headers must match canonical positions.
  - Missing/inconsistent required headers now trigger warnings and skip category ingestion to prevent silent misalignment.
- Kept artisanal tiered parsing untouched as requested.
- Executed required run sequence:
  1. `python scripts/ingest_lr_prices.py`
  2. `python scripts/apply_manual_lr_links.py`
  3. `python scripts/link_recipes.py`

### Validated Outcomes
- Target row checks match expected values:
  - `AG001`: `price_current=12`, `price_industrial_town=8`
  - `AG002`: `price_current=8`, `price_industrial_town=5`
  - `AG003`: `price_current=15`, `price_industrial_town=10`
  - `IN007`: `price_current=8`, `price_industrial_town=10`
- Final gate latest run remains stable:
  - `Passed 14/15`, `Regressions: 0`
  - Known outstanding fail unchanged: `Grid: lantern up (iron)`.


## Update (2026-04-06): Move to Clean Directory + GitHub

### Completed in This Pass
- Moved project into clean workspace: `C:/Users/Kjol/projects/merchant-ledger`.
- Created repo-level `.gitignore` including logs (`*.log`) and temp files (`data/_tmp_*`).
- Added root `README.md` with stack/run instructions.
- Initialized git and created first commit.
- Published public GitHub repo and pushed initial history.
- Removed migrated project files from old `VintagestoryData` location after explicit confirmation.

### Current Canonical Repo
- https://github.com/Miles-Johnson/merchant-ledger
