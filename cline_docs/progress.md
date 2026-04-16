# Progress

## Complete
- Consolidated architecture to **Gen 3 as sole active runtime path**.
- Activated direct JSON parser pipeline (`parse_recipes_json.py`) and retired legacy parse path from active runbook.
- Implemented recipe-family semantics across grid/smithing/knapping/clayforming/alloy/barrel/cooking with unknown-type fallback handling.
- Stabilized canonical linking and kept recipe output unlinked count at zero in validated runs.
- Added/maintained manual pricing correction flows (nuggets, processed ore chain).
- Implemented final validation gate + baseline regression tracking.
- Completed **Path B deterministic LR linking** rollout:
  - authoritative mapping file active (`data/lr_item_mapping.json`)
  - mapping-first linkage in `build_canonical_items.py`
  - `_force_unlinked` support
  - mapping warnings persistence (`data/lr_mapping_warnings.json`)
  - resolver mapped-tier metalplate guardrail bypass + warning logging
  - alias collision hardening for armor plate vs metalplate families
- Completed **Task 0 — FTA/Guild pricing removed** (pricing stack simplified; dead runtime code removed).
- Completed **Task 1 — Price precedence fixed** (manual overrides applied last; LR tried first).
- Completed **Task 2 — Silent parse failures fixed** (parser exits non-zero on parse/insert failure).
- Completed **Task 3 — Lantern variant intent fixed** (resolver inference fallback + material-aware variant selection).
- Completed **Task 4 — Alloy output quantity fixed** (output qty parsed from recipe JSON).
- Completed **Task 5 — Multi-placeholder recipe expansion fixed** (+72 previously missing recipe rows).
- Completed **Task 6 — Structured API error handling** (`/calculate` now returns 400/404/200+flag/500 appropriately).

## Current State
- Core system is functional end-to-end through pipeline + API.
- Historical implementation detail is preserved in deprecated memory files.
- Core memory bank now focused on active truth, not historical play-by-play.
- Final gate target has reached **15/15** per latest task bundle (lantern variant intent resolved).
- Mapping hygiene is clean: unresolved LR item IDs = 0 and mapping warnings empty.
- Mapping coverage snapshot: **29 mapped LR item_ids out of 475 scaffold IDs** (446 remaining for curation).
- Triage snapshot for remaining 446 scaffold IDs:
  - row-level linked canonicals: `exact=52`, `high=0`, `low=9`, `unmatched=0`, `manual=80`, `none/null=422`
  - per-LR-item best-tier: `exact=34`, `high=0`, `low=7`, `unmatched=0`, `manual=26`, `none_or_null=379`

## Remaining High-Value Work
1. Continue LR mapping curation for remaining scaffold IDs with priority:
   - `unmatched` pricing gaps
   - `high`/`low` fuzzy-risk candidates
   - `exact` fuzzy survivors (lower risk)
2. Continue reducing unresolved ingredient count where economically meaningful.
3. Keep final-gate pass rate stable after any parser/resolver/linking changes.

## Operational Acceptance Checks
- Run pipeline: `python run_pipeline.py`
- Run gate: `python scripts/final_gate_validate.py`
- Confirm no regressions in `data/final_gate_validation.json`.

## Historical Material
Detailed milestone timeline moved to:
- `cline_docs/deprecated/progress_historical.md`
