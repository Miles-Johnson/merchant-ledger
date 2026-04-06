# Active Context

## Current Focus
Trim Memory Bank bloat while preserving historical reference.

## What Is Active Right Now
- Keep core memory files concise and current-state oriented.
- Keep historical implementation logs in `cline_docs/deprecated/*_historical.md`.

## Current Runtime Reality
- Active app/runtime path: **Gen 3 only** (`api/app.py` + `scripts/resolver.py` + canonical DB schema).
- Active parser path in pipeline: `scripts/parse_recipes_json.py`.
- Legacy parser/extractor path is deprecated.

## Latest Meaningful Validation Snapshot
- Pipeline/linking stability baseline:
  - `recipes_unlinked = 0`
  - `ingredients_unlinked` stable around low-80s and previously improved from 83 to 81.
- Final-gate trend reached **14/15** with no regressions in latest strong snapshot.
- Known remaining issue: **`Grid: lantern up (iron)` variant intent selection**.

## Immediate Next Steps
1. Keep memory bank lean and non-chronological in core files.
2. If resuming implementation work: target `lantern up (iron)` deterministic variant selection.
3. Maintain final-gate checks after pipeline changes.

## Operational Notes
- Run pipeline stages serially (avoid overlapping runs).
- Clear stale `idle in transaction` PostgreSQL sessions if pipeline/linker deadlocks occur.

## Historical Material
Detailed timeline moved to:
- `cline_docs/deprecated/activeContext_historical.md`

## Update (2026-04-06): Nugget/Bit Manual-Link Fix Pass
- Implemented targeted fixes in `scripts/apply_manual_lr_links.py` only:
  - Cleared incorrect exact `item:metalbit-%` links to LR ingots (preserving manual paths).
  - Added metalbit `/20` ingot-derived override generation with trace note `auto:metalbit_from_ingot`.
  - Added nugget `/20` ingot-derived override generation with trace note `auto:nugget_from_ingot`.
  - Ensured missing `item:nugget-<metal>` canonicals are materialized (`match_tier='manual'`, `variant_family='nugget'`).
  - Added lang-based display-name normalization plus fallback naming for nuggets.
- Validation outcomes from latest run window:
  - Fix-1 safety check: `EXACT_WITH_INGOT_LR_LINK = 0` for `item:metalbit-%`.
  - `/calculate` spot checks now resolve expected values (iron/copper bits, iron/silver nuggets).
  - Searchability evidence verified through alias coverage counts for nugget/bits terms after alias rebuild.
- Final-gate status in current DB state: latest run shows `Passed 4/15`, `Regressions: 0`.
- Important caveat: current broad gate degradation appears outside the specific nugget/bit fixes; no new regressions were introduced by this change set.

## Update (2026-04-06): Pickaxe/Axe Variant Grouping + Search Ranking Stabilization
- Investigated pickaxe variant grouping failure path; DB check confirmed smithing variants already carry `variant_family='pickaxehead'` and material values for concrete metal rows.
- Root runtime issues were in `/search` behavior (`api/app.py`):
  1. Variant inference fallback was narrowly limited to `ingot`/`nugget`.
  2. Family-group creation depended only on direct linked-price flags, excluding recipe-backed smithing families.
- Implemented fixes:
  - Expanded `_infer_variant_from_game_code()` family allowlist to include smithing tool-head and armor families (`pickaxehead`, `axehead`, `shovelhead`, `hoehead`, `swordhead`, `knifeblade`, `arrowhead`, `hammerhead`, `chiselhead`, `sawblade`, `helvehammerhead`, `scythepart`, `javelin`, `metalplate`, and armor body/head/legs chain+plate families).
  - Added `has_recipe` signal in `/search` SQL (`EXISTS recipes.output_canonical_id = ci.id`).
  - Updated grouping gate to `has_any_price OR has_recipe` for family creation and material-chip inclusion.
  - Updated ranking order to prioritize linked-price and recipe-backed entries before similarity.
- Performed scoped variant-family refresh pass (`assign_variant_families()` only) and then immediately ran `python scripts/link_recipes.py` in same session.
- Browser validation passed:
  - Query `pickaxe` returns grouped **Pickaxehead** with expected material chips.
  - Query `axe` returns grouped axe-family result with expected material chips.
- Final gate validated at **14/15**, **Regressions: 0** (known remaining fail: `Grid: lantern up (iron)`).

## Update (2026-04-06): Dual-Price Display (Empire Primary + Crafting Secondary)
- Runtime pricing behavior (`scripts/resolver.py`) now exposes both values simultaneously:
  - Primary price remains `unit_cost` / `source` using precedence `lr_price` -> `fta_price` -> `recipe`.
  - Supplementary recipe economics are attached as `crafting_cost` and `crafting_breakdown`.
- Removed alloy/cooking forced-recipe override so LR remains primary when present, including alloy outputs.
- Enforced current-price-only LR lookup (`unit_price_current`) for this pass (settlement selection intentionally ignored for LR lookup semantics per task clarification).
- UI (`webapp/src/App.jsx`) updated to show separate `Empire Price` and `Crafting Cost` columns in results table.
- Final gate harness updated to accept LR-primary alloy cases and validate recipe ingredient expectations from `crafting_breakdown` when present.
- Latest gate run after this change set: **13/15**, **Regressions: 0**.
- Known remaining failures in current DB state:
  1. `Grid: lantern up (iron)` variant intent (pre-existing known issue).
  2. `Alloy: tin bronze ingot` recipe-type expectation path still selecting non-alloy craft breakdown in current data state.

## Update (2026-04-06): LR Current-Price Column Offset Fix + Re-Ingest
- Implemented targeted fix in `scripts/ingest_lr_prices.py` for **non-tiered** parsing paths only:
  - `parse_standard_row()` non-tiered mapping shifted from cols `5..11` to `6..12`.
  - `parse_artisanal_row()` non-tiered mapping shifted from cols `5..11` to `6..12`.
  - Tiered parsing paths were left unchanged.
- Added defensive header validation:
  - New `warn_if_current_price_header_shifted()` scans CSV header rows for `Current Price` and warns if index differs from expected (`6`) or header is missing.
  - Validation is called at start of `parse_rows()` per category to surface sheet-layout drift immediately.
- Re-ran required ingestion/link sequence (without canonical/alias rebuild):
  1. `python scripts/ingest_lr_prices.py`
  2. `python scripts/ingest_fta_prices.py`
  3. `python scripts/apply_manual_lr_links.py`
  4. `python scripts/link_recipes.py`
- DB validation (post-fix) confirmed expected LR values:
  - `IN002 Brass` -> `price_current=8`, `unit_price_current=8.0`
  - `IN003 Copper` -> `price_current=6`, `unit_price_current=6.0`
  - `IN007 Iron` -> `price_current=8`, `unit_price_current=8.0`
  - `IN016 Tin Bronze` -> `price_current=6`, `unit_price_current=6.0`
  - `IN017 Black Bronze` -> `price_current=9`, `unit_price_current=9.0`
- Settlement spot-check for `IN007` confirmed corrected alignment:
  - `price_current=8`, `price_industrial_town=10`, `price_market_town=5`.
- Runtime/API spot checks confirmed LR-primary values after re-ingest:
  - `1 iron ingot` -> `unit_cost=8.0`, source `lr_price`
  - `1 brass ingot` -> `unit_cost=8.0`, source `lr_price`, `crafting_cost=5.65`
  - `1 copper ingot` -> `unit_cost=6.0`, source `lr_price`
- Gate status after fix pass:
  - `final_gate_validate` latest run: **Passed 14/15, Regressions 0**.
  - Remaining known fail unchanged: `Grid: lantern up (iron)`.
- Important operational note from new header warnings:
  - `agricultural_goods` currently reports `Current Price` at column index `5` (not `6`), indicating mixed sheet layouts across categories and requiring ongoing monitoring.

## Update (2026-04-06): Header-Based Non-Tiered LR Column Detection (Cross-Section Safe)
- Implemented root fix in `scripts/ingest_lr_prices.py` for non-tiered standard parsing:
  - Added `detect_standard_price_col_map()` to detect actual header positions for:
    - `Current Price`, `Industrial Town`, `Industrial City`, `Market Town`, `Market City`, `Religious Town`, `Temple City`.
  - `parse_standard_row()` non-tiered path now uses detected header indices instead of hardcoded columns.
- Multi-section safety behavior:
  - First section header containing exact `Current Price` is treated as canonical map.
  - Repeated section headers are validated against canonical map.
  - If required headers are missing or any section map differs, category is skipped with clear warning (prevents silent mis-ingestion).
- Confirmed layout assumptions in current raw CSVs:
  - `industrial_goods`: `Current Price` consistently index `6` across repeated section headers.
  - `agricultural_goods`: `Current Price` consistently index `5` across repeated section headers.
- Re-ran required sequence:
  1. `python scripts/ingest_lr_prices.py`
  2. `python scripts/apply_manual_lr_links.py`
  3. `python scripts/link_recipes.py`
- DB validation query for `AG001`, `AG002`, `AG003`, `IN007` matches expected:
  - `AG001 Cabbage`: `price_current=12`, `price_industrial_town=8`
  - `AG002 Carrot`: `price_current=8`, `price_industrial_town=5`
  - `AG003 Cassava`: `price_current=15`, `price_industrial_town=10`
  - `IN007 Iron`: `price_current=8`, `price_industrial_town=10`
- Final gate after this pass:
  - `Passed 14/15`, `Regressions: 0`.
  - Remaining known fail unchanged: `Grid: lantern up (iron)`.


## Update (2026-04-06): Project Relocation + GitHub Publish
- Project root moved from `c:/Users/Kjol/AppData/Roaming/VintagestoryData` to **`C:/Users/Kjol/projects/merchant-ledger`**.
- Repository initialized and first commit created in new root.
- Public GitHub remote published and synced.
- Old mixed game-data location was cleaned of project files after confirmation.
