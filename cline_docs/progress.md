# Progress

## Session 2026-04-18
- parse_recipes_json.py fixed for broader corpus ingestion.
- compute_primitive_prices.py added to pipeline.
- Primitive rules added: rock, stone, sand, soil, flint, salt, drygrass, brineportion, needle, iron hoop, parchment, bowl fired, debarked log, support beams, bones, driftwood/flotsam, slush, metalnailsandstrips, metalnailsandstrips_cupronickel, anvil_copper (WRONG PRICE — needs correction to 10×), driftwood, slush, gear_rusty (pending), anvil_meteoriciron (pending).
- Manual LR links added: mushrooms, linen, candles, glass.
- Audit script JSON schema fixed (scalar summary keys restored).

## Session 2026-04-19
- Resolver priority order corrected: LR → Override → Recipe.
- Cycle handling hardened: cyclic paths now invalid, not partially priced.
- Confirmed flaxfibers now resolves via override (0.015625) not bad recipe (was 1.03125).
- Confirmed isTool flag is present in game recipe JSON and already handled at parse time.
- Confirmed smithing recipes have no tool ingredient by structure.
- Identified deconstruction recipe problem (eyepatch → flaxfibers) — not yet deleted.
- Identified anvil rule 6k is wrong (1× ingot, should be 10×).
- Identified hook_copper chisel blocker as likely missing isTool flag in mod recipe.
- Memory bank updated to reflect correct system state.

## Current Snapshot (2026-04-19)
- Canonicals: 14,210
- Priced: 7,011 (49.3%)
- Gaps: 7,449
  - no_lr_no_recipe: 2,271
  - no_lr_recipe_incomplete: 4,928
  - no_lr_no_price_override: 250

## Known Debt
- Audit does not call resolver — numbers are conservative lower bounds.
- Final gate baseline is stale — needs rewrite after pricing stabilises.
- Bad deconstruction recipes in DB (recipes 2750, 2751) — cleanup pending.
- Anvil rule 6k price is wrong — correction pending.
- Pending rule families: pelts, crushed, powdered, hooks, anvil correction, gear_rusty.
