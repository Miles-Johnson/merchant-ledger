# System Patterns

## 1) Canonical-First Architecture Pattern
- Normalize diverse game/mod data into canonical identities.
- Resolve all pricing and recipe traversal from canonical IDs.
- Keep alias search and canonical linkage as first-class components.

## 2) Direct JSON Recipe Parsing Pattern
- Parse recipe JSON/JSON5 directly from base + mod content.
- Insert typed outputs/ingredients directly into `recipes` + `recipe_ingredients`.
- Avoid lossy text/workbook intermediary parsing in active pipeline.

## 3) Price Source Precedence Pattern
1. LR direct price first.
2. Recipe decomposition when LR direct pricing is unavailable.
3. Manual override path applied last for selected economics corrections.

## 4) Resolver Performance + Safety Pattern
- Request-scoped memoization for recursive subtree reuse.
- Cycle detection guard (`_visited`) on recursion.
- First-success short-circuit behavior for recipe alternatives (default fast path).

## 5) Variant Handling Pattern
- Variant groups carry deterministic primary entries.
- Search supports family grouping (`variant_family`, `variant_material`).
- Calculate path can remap within a variant family via material override.
- Resolver includes `game_code` inference fallback when direct mapping is incomplete.
- Recipe variant selection is material-aware to preserve deterministic intent (e.g., lantern/plate material correctness).

## 6) Recipe-Type Semantics Pattern
- Grid qty from symbol counts.
- Smithing qty via voxel fill (`ceil(bits/42)`).
- Cooking uses minimum required slots only (`minQuantity`).
- Alloy supports ratio-based ingredient quantities.
- Alloy output quantity is parsed from recipe JSON output metadata.
- Barrel preserves liquid/solid quantity semantics.

## 12) Parser Fail-Fast Integrity Pattern
- Recipe parse pipeline must fail hard (non-zero exit) on any parse or insert failure.
- Silent partial-success behavior is explicitly disallowed.
- Pipeline automation should treat parser non-zero exits as corpus/data integrity failures.

## 13) Multi-Placeholder Expansion Pattern
- Recipes containing multiple placeholders are expanded via Cartesian product materialization.
- Expanded variants are inserted as discrete recipe rows to preserve complete ingredient chains.
- Missing expansions are treated as corpus completeness defects.

## 14) Structured API Error Mapping Pattern
- `/calculate` distinguishes client vs domain vs server failures with stable status mapping:
  - `400` invalid request/input
  - `404` unresolved/not found
  - `200` with warning/flag for recoverable partial states
  - `500` unexpected internal error
- Error semantics are part of client contract and must not collapse to blanket `500`.

## 7) Manual Economics Correction Pattern
- Nugget pricing derived from ingot economics (`/20` rule).
- Processed ore chain pricing uses deterministic override generation, with fallback ratios when source ratio is unavailable.
- All manual corrections are traceable in `price_overrides` notes.

## 8) Validation Gate Pattern
- Keep a repeatable final gate (`scripts/final_gate_validate.py`).
- Persist baseline (`data/final_gate_baseline.json`).
- Detect regressions explicitly rather than relying on ad-hoc checks.

## 9) Operational Reliability Pattern
- Run pipeline stages serially.
- Avoid overlapping parser/build/link sessions.
- Clear stale idle transactions when lock/deadlock symptoms appear.

## Historical Material
Detailed evolution history moved to:
- `cline_docs/deprecated/systemPatterns_historical.md`

## 10) Fragment-Derived Override Pattern (Nuggets/Bits)
- When fragment canonicals (`item:nugget-%`, `item:metalbit-%`) require stable economics, derive unit prices from linked ingot economics using the deterministic `/20` rule.
- Materialize missing nugget canonicals from priced ingot canonicals when absent, and stamp variant metadata (`variant_family='nugget'`, `variant_material=<metal>`).
- Enforce provenance in `price_overrides.note` with explicit machine-readable notes:
  - `auto:nugget_from_ingot`
  - `auto:metalbit_from_ingot`
- Prevent false LR exact-link contamination by clearing `item:metalbit-%` exact links that point to LR ingot rows; preserve manual mappings.
- After creating/linking new canonicals, regenerate aliases so search can resolve new priced entities consistently.

## 11) Path B Deterministic LR Linking Pattern
- Treat `data/lr_item_mapping.json` as authoritative linkage input (`_status="active"`).
- Use mapping-first canonical linking in `build_canonical_items.py` before fuzzy fallback.
- Preserve explicit exclusions through `_force_unlinked` for known non-authoritative families (e.g., `metalchain`, `metalbit`).
- Constrain linkage provenance with explicit tiers:
  - `mapped` (authoritative mapping)
  - `manual`
  - `exact` / `high` / `low` (fuzzy fallback)
  - `unmatched` / `none` (no robust link)
- Persist mapping hygiene output in `data/lr_mapping_warnings.json`; treat non-empty `missing_lr_item_ids`, `duplicate_game_codes`, or `invalid_entries` as curation blockers.
- Resolver guardrail exception: allow `match_tier='mapped'` metalplates to bypass plate-family ambiguity checks while emitting warning logs.
- Alias-generation guardrail: keep armor plate aliases isolated from metalplate material aliases to prevent cross-family collisions.
