# Active Context

## Current State (2026-04-19)

### Resolver
- Priority order corrected: LR → Override → Recipe (was LR → Recipe → Override).
- Cycle handling hardened: cyclic recipe paths now return is_partial=True, not a spurious cost.
- Override now evaluated before recipe traversal.
- Confirmed working via direct resolver test: flaxfibers returns override 0.015625 (was 1.03125 from bad recipe).

### Audit
- Audit script JSON schema restored (all scalar summary keys present).
- Audit still uses independent pricing logic — does NOT call resolver.
- Current numbers are conservative lower bounds until audit rewrite.

### Current Metrics (post resolver fix)
- Total canonicals: 14,210
- Priced: 7,011 (49.3%)
- Gaps: 7,449 (52.4%)
  - no_lr_no_recipe: 2,271
  - no_lr_recipe_incomplete: 4,928
  - no_lr_no_price_override: 250
- Ignored tool edges: 1,110

### Known Issues
- Bad deconstruction recipes still in DB (eyepatch → flaxfibers, recipes 2750/2751). Harmless due to override priority fix but not yet deleted.
- Audit does not call resolver — gap counts are not fully accurate.
- hook_copper shows chisel as blocker — chisel likely missing isTool flag in that mod's recipe JSON (data issue).
- Parser bug: `parse_recipes_json.py` currently writes incorrect `recipes.output_qty` for multi-output smithing/casting outputs (e.g. bighook should be 4 per ingot but DB shows 1).

### Pending Rule Families (approved, not yet implemented)
- Pelts: 0.8 × (LR prepared hide price ÷ stack size) per size tier
- Crushed materials: ingot_price / 20
- Powdered materials: ingot_price / 40
- Hooks (bighook): ingot_price / 20
- gear_rusty: 5.0 CS flat

## Immediate Next Steps
1. Fix `parse_recipes_json.py` multi-output quantity parsing for smithing/casting recipes and re-ingest recipes.
2. Verify known examples (e.g. bighook) now persist correct `output_qty` values in DB.
3. Re-evaluate and then implement pending Section 6 rule families (pelts/crushed/powdered/hooks).
4. Confirm hook recipe raw JSON and chisel isTool status where blockers remain.
5. Confirm deconstruction recipe detection pattern from raw JSON.
6. Rewrite audit to call resolver directly.
7. Rerun full pipeline and measure cascade impact.
8. Rewrite final gate baseline after pricing stabilises.
