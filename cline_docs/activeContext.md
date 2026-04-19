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
- Anvil rule 6k was written as 1× ingot — needs correction to 10× ingot (not yet applied).

### Pending Rule Families (approved, not yet implemented)
- Pelts: 0.8 × (LR prepared hide price ÷ stack size) per size tier
- Crushed materials: ingot_price / 20
- Powdered materials: ingot_price / 40
- Hooks (bighook): ingot_price / 20
- Anvil correction: 10× ingot (all variants)
- gear_rusty: 5.0 CS flat

## Immediate Next Steps
1. Confirm hook recipe raw JSON and chisel isTool status (diagnostic in progress).
2. Confirm deconstruction recipe detection pattern from raw JSON.
3. Implement pending rule families in compute_primitive_prices.py.
4. Rewrite audit to call resolver directly.
5. Rerun full pipeline and measure cascade impact.
6. Rewrite final gate baseline after pricing stabilises.
