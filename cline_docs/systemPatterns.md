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
2. FTA fallback when LR missing.
3. Recipe decomposition when direct price path is unavailable or intentionally bypassed.
4. Manual override path for selected economics corrections.

## 4) Resolver Performance + Safety Pattern
- Request-scoped memoization for recursive subtree reuse.
- Cycle detection guard (`_visited`) on recursion.
- First-success short-circuit behavior for recipe alternatives (default fast path).

## 5) Variant Handling Pattern
- Variant groups carry deterministic primary entries.
- Search supports family grouping (`variant_family`, `variant_material`).
- Calculate path can remap within a variant family via material override.

## 6) Recipe-Type Semantics Pattern
- Grid qty from symbol counts.
- Smithing qty via voxel fill (`ceil(bits/42)`).
- Cooking uses minimum required slots only (`minQuantity`).
- Alloy supports ratio-based ingredient quantities.
- Barrel preserves liquid/solid quantity semantics.

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
