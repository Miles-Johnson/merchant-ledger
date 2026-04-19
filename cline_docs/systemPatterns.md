# System Patterns

## 1) Canonical-first runtime
- All pricing + recipe traversal runs through `canonical_items.id`.
- Resolver and diagnostics must reference canonical IDs (not raw game_code).

## 2) Pricing precedence (AUTHORITATIVE — do not reorder)
- **LR direct price → manual/computed override → recipe decomposition**
- LR wins immediately if present.
- Override wins over any recipe result if: recipe is partial, recipe failed, or recipe cost >= override cost.
- Recipe is only used when neither LR nor override exists, OR when recipe is cheaper than override.
- This order was corrected in session 2026-04-19. Prior docs showing override as final fallback are WRONG.

## 3) Recipe ingestion integrity
- `scripts/parse_recipes_json.py` is authoritative.
- Scans base + mod roots, uses absolute mod cache path, isolates per-file errors.
- Current scale: ~2,139 files, ~22,489 recipes, ~56,564 ingredients.
- `isTool: true` flag in recipe JSON is already handled at ingestion — tool ingredients are excluded from `recipe_ingredients` at parse time for grid recipes.
- Smithing recipes have no tool ingredient by structure (anvil is implicit crafting station).

## 4) Resolver safety + fallback behavior
- Cycle guard is mandatory.
- When a cycle is detected on any ingredient, that entire recipe path is marked invalid (is_partial=True, unit_cost=None).
- Override is checked BEFORE recipe traversal (see Pattern #2).
- Cycle fallback: if all recipe paths are cyclic and override exists, override wins.

## 5) Pricing derivation rules (locked)
- Rock = `IN043 (Giant Quarried Stone) current_price / 216`
- Stone = `rock / 10`
- Sand / Soil / Flint / Salt = stone price
- Drygrass / Brineportion / Needle = `1/64`
- Debarked log = `log_price / 4`
- Parchment = `2 × min(cattail, papyrus) price`
- Iron hoop = `1.4 × iron ingot price`
- Anvils = `10 × parent ingot LR price` (all metal variants)
- gear_rusty = `5.0 CS` (foraged flat rate)
- metalnailsandstrips = `2.0 CS`
- metalnailsandstrips_cupronickel = `2.25 CS`
- Bowl fired = `1 × clay price`
- Support beams = component wood cost
- Bones = primitive fallback
- Driftwood / flotsam = stick price
- Slush = 0

## 6) Pending pricing rules (designed, not yet implemented)
- Pelts = `0.8 × (prepared hide LR current price ÷ stack size)` per size tier (small/medium/large/huge)
- Crushed materials = `ingot_price / 20` (1 nugget = 1/20 ingot)
- Powdered materials = `ingot_price / 40` (1 crushed → 2 powdered)
- Bighook = `ingot_price / 20` (5 units of metal, 1 unit = 5 material, 100 units = 1 ingot)
- These are blocked pending resolver cleanup (deconstruction filter) being confirmed stable first.

## 7) Manual LR linking policy
- Keep explicit targeted mappings in `scripts/apply_manual_lr_links.py`.
- Active links: mushrooms, linen block variants, candle variants, glass slab/item variants.
- Do NOT link `item:metalchain-*` to LR chain rows (those are armor-market rows).
- Do NOT link pipeleaf (out of scope).

## 8) Deconstruction / reverse recipe policy
- Deconstruction recipes (complex item → raw material) must not be used for forward pricing.
- Known confirmed bad recipes: Accessorize eyepatch → flaxfibers (recipes 2750, 2751).
- These are currently still in the DB. Priority fix is override precedence (Pattern #2), which makes them harmless for now. DB cleanup is pending.
- Detection method: structural (output is simpler than inputs). No reliable JSON flag found yet for all cases.
- Diagnostic to detect more bad recipes is pending.

## 9) Tool handling in recipes
- `isTool: true` in raw recipe JSON = non-consumed tool ingredient.
- Parser already excludes these from `recipe_ingredients` at ingestion (confirmed 2026-04-19).
- No `is_tool` column needed in DB — tools are simply never inserted.
- If a tool still appears as a blocker, the recipe file is missing the `isTool` flag (data issue, not code issue).

## 10) Gate + audit interpretation
- Final gate baseline is stale — must be rewritten against current corpus after pricing stabilises.
- Audit script (`audit_pricing_gaps.py`) currently has independent pricing logic (does not call resolver).
- Audit rewrite to call resolver directly is pending — current gap counts are conservative lower bounds.
- Blocker-frequency SQL over-reports false positives; resolver is authoritative.

## 11) Operational pattern
- Run pipeline serially; avoid overlapping sessions.
- Confirm compile before pipeline run.
- Confirm audit numbers after every significant change.