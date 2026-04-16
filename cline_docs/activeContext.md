# Active Context

## Current Focus
Path B remains stable; current focus is maintaining the simplified LR-first pricing/resolution stack and preserving 15/15 gate behavior.

## What Is Active Right Now
- Keep Gen 3 runtime and pipeline authoritative.
- Maintain Path B deterministic LR-linking behavior as locked baseline.
- Keep parser fail-fast guarantees active so pipeline catches corpus corruption.
- Preserve corrected resolver variant-intent behavior and structured API error semantics.

## Current Runtime Reality
- Active app/runtime path: **Gen 3 only** (`api/app.py` + `scripts/resolver.py` + canonical DB schema).
- Active parser path in pipeline: `scripts/parse_recipes_json.py`.
- Legacy parser/extractor path is deprecated.

## Latest Meaningful Validation Snapshot
- Pipeline/linking stability baseline:
  - `recipes_unlinked = 0`
  - `ingredients_unlinked` stable around low-80s and previously improved from 83 to 81.
- Final gate intent is now **15/15** per latest task bundle (lantern variant issue resolved).

## Update (2026-04-16): Task Bundle 0–6
- **Task 0 — FTA/Guild pricing removed:** Runtime pricing simplified to `LR → recipe → override`; dead code removed and resolver path cleaned.
- **Task 1 — Price precedence fixed:** Manual overrides now apply **last**; LR is always attempted before recipe decomposition/override fallback.
- **Task 2 — Silent parse failures fixed:** Parser now exits non-zero when any recipe fails parse or insert, surfacing corpus corruption to pipeline automation.
- **Task 3 — Lantern variant intent fixed:** Added resolver `game_code` inference fallback and material-aware variant selection; target validation reached.
- **Task 4 — Alloy output quantity fixed:** Alloy output quantity now parsed from recipe JSON (latent correctness fix; important for mod recipes).
- **Task 5 — Multi-placeholder expansion fixed:** Cartesian expansion added **72 missing recipe rows**, restoring previously missing ingredient chains.
- **Task 6 — Structured API error handling:** `/calculate` now returns meaningful `400/404/200+flag/500` outcomes instead of flattening to `500`.

## Path B Completion Snapshot (2026-04-09)
- `data/lr_item_mapping.json` active with `_force_unlinked` enabled.
- Curated mapping entries: **29 LR item_ids** (authoritative mapping file), yielding **34 `match_tier='mapped'` canonicals.
- `data/lr_mapping_warnings.json`: clean (`missing_lr_item_ids=[]`, `duplicate_game_codes={}`, `invalid_entries=[]`).
- `scripts/final_gate_validate.py` expectation updated for `Smithing: metal plate iron` to `expected_source='lr_price'` while still validating smithing ingredient structure via `crafting_breakdown` (`ingot_iron x2.0`).

## Unmapped Scaffold Triage Snapshot
- Remaining scaffold LR item_ids: **446** (`475 total - 29 mapped`).
- Canonicals linked to those 446 IDs (row-level):
  - `exact: 52`
  - `high: 0`
  - `low: 9`
  - `unmatched: 0`
  - `manual: 80`
  - `none/null: 422`
- Per-LR-item best-tier view across the same 446 IDs:
  - `exact: 34`, `high: 0`, `low: 7`, `unmatched: 0`, `manual: 26`, `none_or_null: 379`

## Immediate Next Steps
1. Continue mapping curation in priority order:
   - `unmatched` pricing gaps
   - `high`/`low` fuzzy risk surface
   - `exact` fuzzy survivors (lower risk)
2. Keep final-gate behavior stable at **15/15** after parser/resolver/linking changes.
3. Re-run collision diagnostics periodically to track tier movement as mappings are promoted.

## Update (2026-04-09): LR Price Ingestion Source Migration
- `scripts/ingest_lr_prices.py` now ingests from local workbook `data/raw/lr_economy_workbook.xlsx` via `openpyxl` (`data_only=True`).
- Previous Google Sheets CSV fetch path was removed.
- Raw CSV snapshots are still generated for auditability (`data/raw/lr_*_parsed.csv`).
- Industrial workbook duplicates (`IN067`, `IN068`) are now deduped deterministically (first occurrence kept) with warnings.
- Validation after migration:
  - `python run_pipeline.py` completed successfully.
  - `python scripts/final_gate_validate.py` remains part of acceptance checks.

## Operational Notes
- Run pipeline stages serially (avoid overlapping runs).
- Clear stale `idle in transaction` PostgreSQL sessions if pipeline/linker deadlocks occur.

## Historical Material
Detailed timeline moved to:
- `cline_docs/deprecated/activeContext_historical.md`
