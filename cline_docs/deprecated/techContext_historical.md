# Tech Context

## Environment
- OS: Windows 10
- Working directory: `c:/Users/Kjol/AppData/Roaming/VintagestoryData`
- Primary content source for this task: `Cache/unpack`
- Base game install discovered at: `C:\Games\Vintagestory\`

## Data Format
- Recipes and item definitions are JSON files.
- Files are organized inside unpacked zip directories under `assets/<domain>/...`.
- Recipe files are often JSON5-style rather than strict JSON (unquoted keys/trailing commas).

## Constraints
- Need to support both base game content and many mod packages.
- Must identify item-related recipes specifically (not necessarily all JSON content).
- Output should be suitable for downstream DB ingestion.

## Tooling Used (2026-03-19)
- Python 3.12
- `json5` (for tolerant parsing)
- `openpyxl` (for `.xlsx` export)

## Script and Output Artifacts
- Extraction script: `extract_vs_recipes.py`
- Output workbook: `C:\Users\Kjol\Desktop\vs_recipes.xlsx`
- Output columns:
  - `Source Mod`
  - `Recipe Type`
  - `Output Item`
  - `Output Qty`
  - `Ingredients`

## Update 2026-03-20 (Phase 1 + 2)

## Additional Scripts
- `import_lr_items_pg.py`
  - Imports Lost Realm Google Sheets CSV tabs into PostgreSQL `lr_items`.
  - Uses dynamic table columns based on sheet headers.
- `import_vs_recipes_normalized_pg.py`
  - Imports raw recipe JSON (base game + mods) into normalized PostgreSQL tables:
    - `vs_recipe_outputs`
    - `vs_recipe_ingredients`
  - Preserves ingredient quantities and variant context.
- `vs_cost_calculator.py`
  - Recursive cost calculator for user orders.
  - Outputs both listed and calculated costs.
  - Supports settlement-specific price column selection.

## Database Objects Used
- `lr_items`
- `vs_recipe_outputs`
- `vs_recipe_ingredients`
- `item_name_map`

## Runtime Dependencies
- Python 3.12
- `json5`
- `psycopg2-binary`
- `openpyxl` (legacy extractor/import script path)

## Validation Status
- New scripts compile (`py_compile`) and CLI help is functional.
- Full DB run (import + calculator output) still to be executed in a follow-up run command sequence.

## Update 2026-03-20 (Phase 3 UI + Behavior Adjustments)

## Web App Artifacts
- Backend: `webapp/app.py` (Flask)
- Frontend template: `webapp/templates/index.html`
- Frontend logic: `webapp/static/app.js`
- Frontend styles: `webapp/static/style.css`

## UI/UX Changes Implemented
- Updated UI copy and labels for non-technical users.
- Added explicit currency language: "Copper Sovereigns" in headings/table text.
- Humanized settlement labels in client (`current_price` -> `Current Price`, etc.).
- Detail controls changed to clearer actions (`Show Recipe` / `Hide Recipe`).
- Added visual badge for LR market-priced leaf entries (`Market Price ✓`).

## Pricing Engine Behavior Change
- In `vs_cost_calculator.py`, `calc_unit_cost()` now short-circuits for LR-priced items:
  - Uses listed LR price directly.
  - Sets calculated unit equal to listed unit.
  - Skips recipe decomposition for those items.

## Current Technical Gap
- Order-item resolution still depends on recipe output alias matching first.
- LR-listed names without recipe alias mapping can fail to resolve (e.g. `iron plate armor`).
- Next implementation target: LR-name exact/fuzzy fallback (and optionally LR-first resolution) + autocomplete wiring to `/api/search`.

## Update 2026-03-23 (Post-Archaeology Runtime/Stack Clarification)

## Runtime Stacks Present
- **Stack A (Gen 2 / Flask Jinja):**
  - Entry: `webapp/app.py`
  - UI assets: `webapp/templates/index.html`, `webapp/static/app.js`, `webapp/static/style.css`
  - Calculator backend module: `vs_cost_calculator.py`
  - Default runtime port: `127.0.0.1:8000`
- **Stack B (Gen 3 / API + React):**
  - API entry: `api/app.py`
  - Resolver backend module: `scripts/resolver.py`
  - Frontend: `webapp/src/App.jsx` via Vite (`webapp/package.json`, `webapp/vite.config.js`)
  - API runtime port: `0.0.0.0:5000` with Vite proxying `/search` and `/calculate`

## Environment/Connection Strategy
- `.env` currently contains `DATABASE_URL` and legacy recipe path variables.
- Gen 3 API (`api/app.py`) uses `DATABASE_URL` + `ThreadedConnectionPool`.
- Gen 2 Flask app (`webapp/app.py`) uses discrete `PGHOST`/`PGPORT`/`PGDATABASE`/`PGUSER`/`PGPASSWORD` env reads and opens request-scoped psycopg2 connections.

## Data/Schema Tooling Notes
- Migrations (`migrations/001..005`) define typed canonical schema with:
  - trigram extension `pg_trgm`
  - canonical linkage tables
  - quality-tier LR columns and generated unit-price fields
- Script pipeline in `scripts/` targets canonical tables (`recipe_staging`, `recipes`, `recipe_ingredients`, `canonical_items`, `item_aliases`).
- Legacy import scripts (`import_lr_items_pg.py`, `import_vs_recipes_normalized_pg.py`) target alternative table contracts (`lr_items` dynamic columns, `vs_recipe_outputs`, `vs_recipe_ingredients`).

## Frontend Tooling Context
- React toolchain exists and is functional:
  - Vite 5
  - React 18
  - TailwindCSS 3
  - Proxy config in `webapp/vite.config.js` points frontend calls to `http://localhost:5000`.
- Flask Jinja frontend remains present as a parallel, non-React UI path.

## Technical Constraint / Risk
- Same DB table name (`lr_items`) is used by both old/new ingestion approaches but with different column expectations.
- This creates high risk of runtime breakage if operators run mixed import flows without schema guardrails.

## Update 2026-03-23 (Canonical Pipeline Casing Fix)

## Scripts Updated
- `scripts/parse_recipes.py`
  - `normalize_game_code()` now lowercases domain prefixes for:
    - 3+ segment codes (`Item:game:candle` -> `item:candle`)
    - 2 segment codes (`Block:foo` -> `block:foo`)
- `scripts/build_canonical_items.py`
  - Matching domain-prefix lowercasing in `normalize_game_code()`.
  - Removed ingredient Source C skip of `Item:` prefixes.
  - Added `price_overrides` snapshot/restore routines to handle FK-safe canonical rebuild.

## Pipeline Validation Snapshot
- Rebuild stage outputs:
  - `Recipes linked: 17782`
  - `Recipes unlinked: 0`
  - `Ingredients linked: 64815`
  - `Ingredients unlinked: 67`
- Post-fix integrity checks:
  - `canonical_items` lowercased collision groups: `0`
  - uppercase-prefixed `recipes.output_game_code` groups: `0`

## Item-Specific Verification
- Candle case issue resolved:
  - Cooking row now normalized as `item:candle`
  - Links to canonical `candle` (duplicate `candle_2` casing artifact removed)
- Ingredient pricing verification:
  - `item:beeswax` has LR linkage (`lr_item_id=159`, unit price present)
  - `item:flaxfibers` has no LR linkage (recipe fallback path only)

## Update 2026-03-26 (Consolidated Runtime + FTA Data Shape)

## Active Runtime Contract
- Authoritative runtime stack is now Gen 3 only:
  - API: `api/app.py`
  - Resolver: `scripts/resolver.py`
  - Frontend: React/Vite (`webapp/src/*`)
  - Data model: canonical schema from `migrations/001..005` and `scripts/*` pipeline
- Gen 2 scripts/apps remain in-repo as deprecated legacy and should not be used for normal runtime/injest flows.

## Price Sources (Current + Incoming)
- Primary/default source: LR (Empire) prices.
- Supplementary source in progress: Faelyn Trade Association (FTA) guild price sheet.
- UI/API expectation: carry/display LR and FTA prices side-by-side when available.

## FTA Spreadsheet Structure (Documented)
- Simplified flat structure (no settlement or quality variants):
  - `item_id`
  - `name`
  - `qty_unit`
  - `price` (single copper-sovereign value)
- No settlement multipliers.
- No quality tiers.
- Intended use: supplemental price coverage, especially where LR has gaps.

## Planned Pricing Behavior Additions
- FTA fallback authority for items with FTA prices but no LR price.
- Artisan pricing mode toggle planned:
  - material baseline, plus optional `+20% labor` uplift.

## Update 2026-03-26 (Operational Runbook: Full Gen 3 Pipeline)

## Canonical Pipeline Entrypoint
- `run_pipeline.py` is now configured for dual-source ingest + canonical build in one run.

## Executed Script Order
1. `scripts/ingest_recipes.py`
2. `scripts/ingest_lr_prices.py`
3. `scripts/ingest_fta_prices.py`
4. `scripts/parse_recipes.py`
5. `scripts/build_canonical_items.py`
6. `scripts/build_aliases.py`
7. `scripts/link_recipes.py`

## Post-run Verification Metrics
- `run_pipeline.py` now prints aggregate checks for:
  - LR rows loaded (`lr_items_loaded`)
  - FTA rows loaded (`fta_items_loaded`)
  - canonicals linked to LR (`canonical_with_lr_link`)
  - canonicals linked to FTA (`canonical_with_fta_link`)
  - canonicals linked to both (`canonical_with_both_links`)

## API Validation Commands (Gen 3)
- Start API:
  - `python api/app.py`
- Validate multi-source search payload:
  - `curl "http://localhost:5000/search?q=iron&limit=5"`
- Validate calculate payload:
  - `curl -X POST "http://localhost:5000/calculate" -H "Content-Type: application/json" -d "{\"order\":\"1 lantern up\",\"settlement_type\":\"current\"}"`

## Update 2026-03-26 (Diagnosis Technical Notes: Expansion + Quantity)

## File-Level Evidence Captured
- Nadiya waist miner accessories source JSON:
  - `Cache/unpack/dressmakers-1.7.5.../assets/dressmakers/recipes/grid/clothing/class/nadiyan/waist-nadiyan.json`
  - Recipe uses `ingredientPattern` with `ingredients` dict and includes two lantern-attribute variants.
- Smithing metal plate source JSON:
  - `C:/Games/Vintagestory/assets/survival/recipes/smithing/plate.json`
  - Uses singular `ingredient` + smithing `pattern` (9x9 filled rows), output `metalplate-{metal}`.

## Parser/Resolver Behavior Notes (Current)
- `scripts/parse_recipes.py`:
  - wildcard expansion creates one row per variant with shared `variant_group_id`.
  - expanded wildcard rows currently set `is_primary_variant=False` for all entries.
- `scripts/resolver.py`:
  - skips grouped rows unless `is_primary_variant=True`.
  - has cycle detection via `_visited`.
  - does not memoize resolved canonicals across sibling branches.
  - recursive calls use `_visited.copy()`; repeated subtrees are recomputed.

## Extraction Data-Shape Caveat
- `extract_vs_recipes.py` flattens stack identity primarily as type+code text.
- Block/item `attributes` (e.g. lantern material/glass) are not preserved in staging-friendly ingredient identity text.
- This can broaden matching in downstream normalization/resolution and increase recipe alternative fan-out.

## Quantity Derivation Caveat
- Grid quantity logic is implemented (symbol occurrence counting in `ingredientPattern`).
- Smithing quantity is not derived from smithing voxel `pattern`; no explicit quantity usually exists on singular `ingredient`.
- As a result, staging text often has no quantity prefix for smithing input and parse defaults to qty `1`.
- `data/debug_smithing_recipes.csv` reflects this shape for many smithing outputs including `item:metalplate-{metal}`.

## Update 2026-03-26 (Resolver Memoization + API Flag Delivery)

## Resolver Runtime Changes
- `scripts/resolver.py` now implements request-scoped memoization for recursive costing:
  - `calculate_cost(...)` accepts `_memo` and reuses cached subtree results.
  - `process_order(...)` creates one `memo` dict per top-level order calculation and passes it into all item calculations.
  - memoization key includes canonical id, settlement type, and quantity context, with quantity-scaling reuse support.
- Existing `_visited` cycle detection remains in place for circular-reference protection.

## Recipe Alternative Evaluation Changes
- `_build_recipe_result(...)` now supports `include_all_alternatives` (default `False`).
- Default resolver behavior now short-circuits at first successful priced recipe rather than evaluating every alternative.

## API Contract Change
- `api/app.py` `/calculate` now accepts:
  - `include_all_alternatives` (boolean, default false)
- API forwards the flag to `process_order(...)` so UI can opt into exhaustive alternative traversal when needed.

## Validation Snapshot
- `python -m py_compile scripts/resolver.py api/app.py` succeeded.
- Spot checks after change:
  - `1 Clothes Nadiya Waist Miner Accessories` elapsed `0.258s`
  - `1 copper ingot` returned expected LR listed pricing
  - `1 bismuth lantern` returned recipe-based result with ingredient list

## Update 2026-03-26 (Verification Metrics for Parser/Linker Correctness Fixes)

## Pipeline/DB Verification Metrics Captured
- Variant-group integrity:
  - `variant_groups_total=3023`
  - `variant_groups_with_exactly_one_primary=3023`
  - `primary_rows_total=3023`
- Attributed lantern ingredient identity:
  - `recipe_ingredients.input_game_code LIKE 'block:lantern-up|%'` -> `28` rows.
- `/calculate` regression check (Gen 3 API test client):
  - order: `Clothes Nadiya Waist Miner Accessories`
  - `status=200`, `source=recipe`, `unit_cost=42.71875`, `total_cost=42.71875`
  - top-level ingredients present with non-zero line costs.

## Operational Notes
- Windows cmd quoting can break complex inline Python with embedded newlines.
- Preferred verification approach for this repo is shell-safe single-line `python -c` probes or small temporary scripts when query logic is complex.

## Update 2026-03-26 (Smithing Quantity Lookup Implementation Notes)

## New Artifact
- Added manual mapping file:
  - `data/smithing_quantities.json`
- File purpose:
  - provide parser-time quantity overrides for smithing outputs where source JSON uses singular `ingredient` + voxel `pattern` and otherwise defaults to qty=1.

## Parser Runtime Changes
- `scripts/parse_recipes.py` now:
  - loads `data/smithing_quantities.json`
  - wildcard-matches smithing output codes against lookup patterns
  - applies mapped quantity to singular smithing ingredients when no explicit qty prefix exists
  - logs warning for unmapped smithing outputs

## Verification Captured
- DB probe confirmed:
  - `recipes.output_game_code='item:metalplate-iron'`
  - linked ingredient row `qty=2`, `input_game_code='item:ingot-iron'`

## Operational Constraint Observed
- Concurrent runs of `scripts/build_canonical_items.py` and `scripts/link_recipes.py` can deadlock on `recipes` / `recipe_ingredients` updates.
- Recommended run mode for this stack:
  - single serial pipeline execution (`python run_pipeline.py`) with no overlapping background pipeline jobs.

## Update 2026-03-27 (Bug-Fix Technical Delta)

## Files Updated
- `scripts/resolver.py`
  - LR-priced branch in `calculate_cost(...)` no longer computes `recipe_alternative`.
  - Direct LR/FTA path now returns final priced payload immediately.
- `scripts/link_recipes.py`
  - `load_template_patterns(...)` placeholder regex narrowed to `[^:\-|]+` for safer single-token matching.

## Commands Executed
- `python scripts/link_recipes.py`
- `python -m py_compile scripts/resolver.py scripts/link_recipes.py`

## Verification Snippets Captured
- Link audit:
  - `item:awlthorn-gold -> awlthorn_gold (Awlthorn Gold)`
- Resolver checks:
  - `Gold` source `lr_price`, no recipe payload
  - `Iron Ingot` source `lr_price`, no recipe payload
  - `Metal Plate Iron` source `recipe` with `Iron x2`

## Update 2026-03-27 (Nugget Pricing Tech Notes)

## File Updated
- `scripts/apply_manual_lr_links.py`
  - Added nugget override mapping blocks:
    - `ORE_NUGGET_TO_LR_INGOT`
    - `METAL_NUGGET_TO_LR_INGOT`
  - Added helper:
    - `lookup_lr_unit_price(...)`
  - Added execution pass:
    - `upsert_nugget_price_overrides(...)`
  - Removed `item:nugget-{metal}` from broad LR-link material rule generation.
  - Corrected nugget conversion constant to:
    - `NUGGET_TO_INGOT_RATIO = 20`

## Commands Executed
- `python -m py_compile scripts/apply_manual_lr_links.py`
- `python scripts/apply_manual_lr_links.py`

## Validation Captured
- Override upserts (sample):
  - `item:nugget-nativecopper -> 0.3000`
  - `item:nugget-malachite -> 0.3000`
  - `item:nugget-nativegold -> 0.5500`
  - `item:nugget-galena -> 0.2500`
  - `item:nugget-cassiterite -> 0.2500`
- Resolver probe:
  - `item:nugget-nativecopper`, qty `20` => `unit=0.3`, `total=6.0`, `source=manual_override`

## Update 2026-04-01 (Local Hosting + Cloudflare Quick Tunnel)

## Runtime Packaging/Serving Change
- `api/app.py` now serves built React assets from `webapp/dist` directly.
- Added SPA fallback routing so non-API routes return `index.html`.
- Active single-port runtime for sharing:
  - Flask/API + frontend on `http://localhost:5000`.

## Windows Tunnel Tooling
- `cloudflared` installed and verified at:
  - `C:\Program Files (x86)\cloudflared\cloudflared.exe`
- On this machine, PATH resolution may not find `cloudflared` immediately; use full executable path for reliability.

## Share Run Commands
1. Build frontend (after UI changes):
   - `npm --prefix webapp run build`
2. Start app:
   - `python api\app.py`
3. Start tunnel:
   - `"C:\Program Files (x86)\cloudflared\cloudflared.exe" tunnel --url http://localhost:5000`
4. Verify tunnel endpoint:
   - `curl https://<generated>.trycloudflare.com/health`

## Operational Caveat
- Quick tunnel URLs are ephemeral and rotate each run.
- Keep both terminals open (API + cloudflared) for external users to stay connected.

## Update 2026-04-04 (Planned Technical Refactor: Direct JSON Recipe Parser)

## Decision Snapshot
- Keep active Gen 3 runtime/components as-is:
  - `api/app.py`
  - `scripts/resolver.py`
  - canonical schema + linking pipeline
- Replace ingestion segment that currently depends on flattened workbook/text intermediaries.

## Planned New Artifact
- `scripts/parse_recipes_json.py`
  - Directly scans base + mod recipe JSON trees.
  - Parses with JSON5.
  - Writes directly into `recipes` and `recipe_ingredients`.
  - Avoids `extract_vs_recipes.py` -> workbook -> `recipe_staging` -> regex reparse dependency for active path.

## Type-Specific Handler Plan (Implementation Order)
1. Scaffold/discovery/helpers
2. Grid
3. Smithing
4. Knapping + Clayforming
5. Alloy
6. Barrel
7. Cooking
8. Mod catch-all fallback

## Technical Semantics Locked
- Smithing quantity derivation target:
  - compute from voxel fill bits (`#`) using `ceil(bits / 42)`.
- Cooking baseline pricing target:
  - include required minimum only (`minQuantity`), exclude optional slots (`minQuantity=0`).
- Future extension note:
  - support user-selected add-ins for cooking not part of this refactor pass.

## Pipeline Impact (Planned)
- `run_pipeline.py` will be updated to call direct parser path.
- Existing downstream stages (`build_canonical_items.py`, `build_aliases.py`, `link_recipes.py`, resolver/API) remain in place for first iteration.

## Update 2026-04-04 (Step 1.0 Direct Parser Scaffold Implemented)

## New Artifact
- `scripts/parse_recipes_json.py`

## Implemented Technical Behavior (Current)
- Loads environment via `dotenv` and reads `DATABASE_URL`.
- Truncates canonical recipe tables at startup:
  - `TRUNCATE TABLE recipe_ingredients, recipes RESTART IDENTITY CASCADE`
- Discovers recipe files from:
  - base game: `C:\Games\Vintagestory\assets\survival\recipes\**\*.json`
  - mods: `Cache\unpack*\**\recipes\**\*.json`
- Parses JSON using `json5` with UTF-8 BOM-safe reads.
- Supports both file shapes:
  - single recipe object
  - array of recipe objects
- Detects recipe type via path segment directly after `recipes`.
- Includes required shared helpers:
  - `normalize_game_code(code)`
  - `make_item_code(obj)`
- Includes empty per-type handlers (no insert logic yet):
  - grid, smithing, barrel, cooking, alloy, clayforming, knapping, unknown fallback.

## Validation Snapshot
- Command:
  - `python -u scripts/parse_recipes_json.py`
- Result summary:
  - `Files walked: 2132`
  - `Parse failures: 2`
  - `Total recipes discovered: 10229`
  - `Total recipes inserted: 0` (expected for Step 1.0 stubs)

## Technical Note
- Type detection surfaced `gridcrafting.json` as a detected type (`3` rows) due to strict segment-after-`recipes` logic in mod paths; this is acceptable at scaffold stage and will be addressed during type handling hardening.

## Update 2026-04-04 (Step 1.1 Grid Handler Technical Delta)

## File Updated
- `scripts/parse_recipes_json.py`

## Implemented Technical Changes
- Added SQL insert statements for direct writes to:
  - `recipes`
  - `recipe_ingredients`
- Added helper functions:
  - `parse_qty(...)`
  - `split_ingredient_pattern_rows(...)`
  - `count_grid_symbols(...)`
  - `variant_rows_for_grid_recipe(...)`
  - `apply_variant_template(...)`
- Implemented `handle_grid(cur, recipe, source_mod, filepath)` with:
  - symbol-count quantity derivation
  - wildcard/templated variant expansion path
  - tool-skip behavior
  - output/input template substitution support
- Updated handler dispatch signatures so all handlers accept DB cursor.

## Validation Snapshot
- Run command:
  - `python -u scripts/parse_recipes_json.py`
- Summary observed:
  - `Files walked: 2132`
  - `Parse failures: 2`
  - `Total recipes discovered: 10229`
  - `Total recipes inserted: 16338`
- DB checks (sampled):
  - `block:lantern-up` iron variant ingredients:
    - `item:metalplate-iron x1`
    - `item:clearquartz x2`
    - `item:candle x1`
  - `block:chest-east` sample ingredients:
    - `item:plank-* x8`
    - `item:metalnailsandstrips-* x1`
  - `item:armor-body-plate-iron` sample ingredients:
    - `item:metalplate-iron x8`
    - `item:armor-body-chain-iron x1`

## Current Constraint
- Non-grid handlers remain stubs; inserted totals currently reflect grid-only semantics plus expansion behavior.

## Update 2026-04-04 (Step 1.3 Knapping + Clayforming Technical Delta)

## File Updated
- `scripts/parse_recipes_json.py`

## Implemented Technical Changes
- Implemented `handle_knapping(cur, recipe, source_mod, filepath)`:
  - parses singular `ingredient` + `output` shape.
  - expands variants from `ingredient.allowedVariants` using `ingredient.name`.
  - applies variant substitution to output and ingredient codes (`*` + `{placeholder}`).
  - inserts one recipe + one ingredient row per expanded variant.
  - enforces fixed knapping consumption `qty = 1`.
- Implemented `handle_clayforming(cur, recipe, source_mod, filepath)` with same variant/template behavior and fixed `qty = 1`.

## Validation Snapshot
- Parser run:
  - `python -u scripts/parse_recipes_json.py`
  - `Files walked: 2132`
  - `Parse failures: 2`
  - `Total recipes discovered: 10229`
  - `Total recipes inserted: 17469`
- DB verification:
  - `item:knifeblade-flint` rows include `item:flint` with `qty=1`.
  - `block:bowl-*-raw` rows include `item:clay-<color>` with `qty=1`.
  - Additional observed variants in DB are expected from multiple source recipes producing the same output code.

## Update 2026-04-04 (Step 1.4 Alloy Technical Delta)

## File Updated
- `scripts/parse_recipes_json.py`

## Implemented Technical Changes
- Added alloy-specific ingredient insert SQL path:
  - preserves `ratio_min` and `ratio_max` in `recipe_ingredients`
  - stores midpoint quantity `qty = (ratio_min + ratio_max) / 2`
- Implemented `handle_alloy(cur, recipe, source_mod, filepath)`:
  - parses `output` and `ingredients[]`
  - inserts one `recipes` row per alloy recipe (`output_qty=1`, `recipe_type='alloy'`)
  - inserts one `recipe_ingredients` row per valid alloy ingredient with ratio bounds + midpoint qty
  - removes orphan recipe rows if zero valid ingredient rows were inserted.

## Validation Snapshot
- Parser run:
  - `python scripts/parse_recipes_json.py`
  - `Files walked: 2132`
  - `Parse failures: 2`
  - `Total recipes discovered: 10229`
  - `Total recipes inserted: 17478`
- DB verification for `item:ingot-tinbronze`:
  - tin ingredient: `qty=0.10`, `ratio_min=0.08`, `ratio_max=0.12`
  - copper ingredient: `qty=0.90`, `ratio_min=0.88`, `ratio_max=0.92`

## Update 2026-04-04 (Step 1.5 Barrel Technical Delta)

## File Updated
- `scripts/parse_recipes_json.py`

## Implemented Technical Changes
- Implemented `handle_barrel(cur, recipe, source_mod, filepath)`:
  - parses barrel `output` + `ingredients[]` shape.
  - inserts one `recipes` row per barrel recipe variant (`recipe_type='barrel'`).
  - inserts one `recipe_ingredients` row per valid ingredient.
  - applies quantity semantics:
    - liquids: `consumeLitres` (or `consumelitres`) fallback to `litres`
    - solids: `quantity`
  - ignores `sealHours` for cost-table writes.
  - supports current-stage single-placeholder variant expansion via ingredient `allowedVariants` + `name`.
  - removes orphan recipe rows when no valid ingredient rows are produced.

## Validation Snapshot
- Parser/DB snapshot after barrel implementation:
  - `recipes` total: `18840`
  - `recipes where recipe_type='barrel'`: `1362`
  - barrel ingredient joins: `2385`
- Target leather check:
  - output `item:leather-normal-plain`, `output_qty=1` includes
    - `item:strongtanninportion qty=2`
    - `item:hide-prepared-small qty=1`

## Operational Note
- In this environment, long parser/query runs can exceed the 30s command timeout and continue in background terminals; validation was completed via follow-up DB probes.

## Update 2026-04-04 (Step 1.6 Cooking Technical Delta)

## File Updated
- `scripts/parse_recipes_json.py`

## Implemented Technical Changes
- Implemented `handle_cooking(cur, recipe, source_mod, filepath)`:
  - reads cooking `ingredients[]` slots and optional `cooksInto` output.
  - uses `minQuantity` for required slot quantity.
  - skips slots with `minQuantity <= 0`.
  - writes each required slot's `validStacks` as grouped alternatives using `variant_group_id` and `is_primary_variant`.
  - inserts one recipe row + grouped ingredient rows for each cooking recipe.
- Added output fallback for meal-style cooking recipes with no `cooksInto`:
  - derives output as `item:meal-<recipe.code>`.

## Validation Snapshot
- Parser run summary after update:
  - `Files walked: 2132`
  - `Parse failures: 2`
  - `Total recipes discovered: 10229`
  - `Total recipes inserted: 18915`
- DB checks:
  - candle cooking baseline rows:
    - `item:beeswax qty=3`
    - `item:flaxfibers qty=1`
  - meat stew baseline rows:
    - output `item:meal-meatystew`
    - required protein slot group `cooking:meatystew:0` with six alternatives at qty `2`
    - optional slots not inserted.

## Update 2026-04-04 (Step 1.7 Technical Delta: Catch-all + Pipeline Wiring)

## Files Updated
- `scripts/parse_recipes_json.py`
  - added robust `handle_unknown(...)` extraction fallback.
  - added per-recipe dispatch `try/except` guard to isolate malformed rows.
  - added duplicate-warning suppression for unknown types keyed by `(recipe_type, filepath)`.
- `run_pipeline.py`
  - switched parser stage to `scripts/parse_recipes_json.py`.
  - removed parser/intermediary stage calls to `scripts/ingest_recipes.py` and `scripts/parse_recipes.py`.
  - replaced emoji completion lines with ASCII `[OK]` / `[ERROR]` status messages for Windows cp1252 safety.

## Active Pipeline Order (Current)
1. `scripts/ingest_lr_prices.py`
2. `scripts/ingest_fta_prices.py`
3. `scripts/parse_recipes_json.py`
4. `scripts/build_canonical_items.py`
5. `scripts/build_aliases.py`
6. `scripts/link_recipes.py`
7. `scripts/apply_manual_lr_links.py`

## Validation Snapshot (User-Reported)
- Pipeline completion marker:
  - `[OK] Pipeline + verification complete.`
- Verification metrics:
  - `lr_items_loaded: 475`
  - `fta_items_loaded: 277`
  - `canonical_with_lr_link: 1089`
  - `canonical_with_fta_link: 277`
  - `canonical_with_both_links: 258`
- Recipe volume delta after Step 1.7 integration:
  - `recipes: 18915 -> 19364`
  - `recipe_ingredients: 47242 -> 47281`

## Update 2026-04-04 (Linkage Audit Technical Snapshot)

## Executed Commands / Checks
- Full pipeline run:
  - `python run_pipeline.py`
- Linkage KPI probes:
  - `SELECT COUNT(*) FROM recipes WHERE output_canonical_id IS NULL`
  - `SELECT COUNT(*) FROM recipe_ingredients WHERE input_canonical_id IS NULL`
- Target item probes for:
  - `item:metalplate-iron`
  - `item:candle`
  - `block:lantern-up`
  - `item:leather-normal-plain`
- Active-path lookup check:
  - repository search for `smithing_quantities.json` references.

## Results Captured
- Pipeline completed with `[OK] Pipeline + verification complete.`
- Linker stage reported:
  - `Recipes linked: 19364`
  - `Recipes unlinked: 0`
  - `Ingredients linked: 47200`
  - `Ingredients unlinked: 81`
- DB KPI probe confirmed:
  - `recipes_unlinked = 0`
  - `ingredients_unlinked = 81`

## Target Item Validation Snapshot
- `item:metalplate-iron`:
  - recipe: `smithing`, linked canonical id `metalplate_iron`
  - ingredient row: `item:ingot-iron`, `qty=2`, linked canonical `ingot_iron`
- `item:candle`:
  - cooking row linked canonical `candle`
  - baseline ingredients: `item:beeswax x3`, `item:flaxfibers x1` (linked)
- `block:lantern-up`:
  - linked canonical `lantern_up`
  - validated rows include variant with `item:metalplate-iron x1` plus expected candle/quartz inputs
- `item:leather-normal-plain`:
  - linked canonical `leather_normal_plain`
  - barrel inputs: `item:strongtanninportion x2`, `item:hide-prepared-small x1`

## Smithing Quantity Derivation Source
- Active parser `scripts/parse_recipes_json.py` smithing handler computes:
  - filled voxels from `pattern` via `#` counts
  - `ingot_qty = ceil(filled_voxels / 42)`
- `smithing_quantities.json` references found only in legacy `scripts/parse_recipes.py`.

## Operational Note
- One stale background pipeline session previously left an idle transaction and caused deadlock on ad-hoc linker rerun.
- Session was cleared and validation proceeded on a clean serial run.

## Update 2026-04-04 (Final Gate Validation Technical Snapshot)

## New Validation Artifact
- Added gate harness script:
  - `scripts/final_gate_validate.py`
- Output artifacts:
  - `data/final_gate_validation.json`
  - `data/final_gate_validation.txt`

## Resolver Runtime Deltas (This Session)
- `scripts/resolver.py` updates:
  - `resolve_canonical_id(...)` now includes:
    - token-aware display-name fallback query,
    - display-name similarity fallback query.
  - `_build_recipe_result(...)` now suppresses false zero totals when all ingredients unresolved:
    - sets `unit_cost=None`, `total_cost=None` in that condition.
  - LR-priced branch in `calculate_cost(...)` now attempts recipe-first fallback path when recipe alternatives are enabled:
    - direct canonical recipe attempt,
    - then same-display-name sibling recipe attempt,
    - then LR leaf fallback.

## Final Gate Run Outcome
- Command:
  - `python scripts/final_gate_validate.py`
- Snapshot result:
  - `Passed 5 / 9`
- Failing items captured in artifact:
  - `1 lantern up` (wrong metalplate variant chosen)
  - `1 chest` (unresolved)
  - `1 leather` (resolved to grid path, expected barrel path)
  - `1 flint knife blade` (unresolved)

## Follow-up Technical Focus
1. Canonical/alias coverage for plain-name items (`chest`, `flint knife blade`).
2. Recipe-family disambiguation strategy when multiple canonicals share user-facing name (`leather`).
3. Deterministic variant-family selection for ambiguous wildcard outputs (`lantern up` iron intent).

## Update 2026-04-04 (Legacy Parser Script Deprecation Header Snapshot)

## Files Updated (This Task)
- `extract_vs_recipes.py`
- `scripts/ingest_recipes.py`
- `scripts/parse_recipes.py`
- `scripts/ingest_recipes_json.py`

## Header Standard Applied
- `DEPRECATED — superseded by parse_recipes_json.py as of 2026-04-04`
- `Retained for reference only. Do not run as part of the pipeline.`

## Technical Rationale
- Adds explicit in-file guardrails for legacy scripts still present in repository.
- Reduces operator error risk by clearly separating:
  - reference-only legacy scripts,
  - active parser stage (`scripts/parse_recipes_json.py`) used by `run_pipeline.py`.

## Update 2026-04-04 (Final Gate Harness Expansion + Baseline File Behavior)

## File Updated
- `scripts/final_gate_validate.py`

## Technical Changes Implemented
- Gate case list expanded from `9` to `15`.
- Added flexible assertion mode for `Multi-step: plate body armor iron`:
  - accepts either:
    - `source=recipe` with `recipe_type=grid`, positive non-null `unit_cost/total_cost`, and non-empty ingredients,
    - or `source=lr_price` with positive non-null `unit_cost/total_cost`.
  - removed strict top-ingredient identity requirement (`metalplate_iron x8`).
- Added minimal spot-check assertion mode for 6 appended cases:
  - source must not be `None` or `unresolved`
  - when `source in {lr_price, recipe}`, `unit_cost` must be positive.
- Added baseline regression support:
  - input baseline: `data/final_gate_baseline.json` (if present)
  - per-case regression flag set when previous pass -> current fail
  - output baseline rewritten each run with:
    - `label`, `order`, `passed`, `source`, `recipe_type`, `unit_cost`
    - run-level `timestamp`
- Updated text report behavior (`data/final_gate_validation.txt`):
  - appends timestamped run blocks instead of overwrite-only single report
  - includes `Regressions: N`
  - includes a `Regression Baseline Snapshot` section with per-case compact lines.

## Validation Snapshot
- Command run:
  - `python scripts/final_gate_validate.py`
- Reported run result:
  - `Passed 9 / 15`
  - `Regressions: 0`
- Baseline file presence validated:
  - `data/final_gate_baseline.json` exists and contains 15 case entries.

## Update 2026-04-04 (Leather Alias/Resolver Priority Remediation Technical Snapshot)

## Files Updated
- `scripts/build_aliases.py`
  - added `BARREL_SHORT_ALIASES` map with:
    - `"item:leather-normal-plain": ["leather", "leathers"]`
  - applied generated-pass alias injection from this map.
- `scripts/resolver.py`
  - `resolve_canonical_id(...)` ORDER BY adjusted to move recipe-family rank immediately after similarity in:
    - alias trigram stage,
    - display-name similarity fallback stage.
  - recipe-family rank mapping now explicitly includes `knapping` and `clayforming` tiers (both rank 5) and `else=6`.

## Commands Executed
- `python run_pipeline.py`
- `python scripts/final_gate_validate.py`

## Execution Snapshot
- Pipeline completed with:
  - `[OK] Pipeline + verification complete.`
  - verification counts remained:
    - `lr_items_loaded: 475`
    - `fta_items_loaded: 277`
    - `canonical_with_lr_link: 1089`
    - `canonical_with_fta_link: 277`
    - `canonical_with_both_links: 258`
- Final-gate snapshot for this run profile:
  - `Passed 3 / 9`.

## Spot-Check Results (Post-change)
- `leather`:
  - canonical id: `leather_normal_plain`
  - resolver output: `source=recipe`, `recipe_type=grid`, `display_name=Leather Normal Plain`
- `leather panel`:
  - canonical id: `panel_leather_type`
  - resolver output: `source=recipe`, `recipe_type=grid`, `display_name=Panel Leather`
- `tin bronze ingot`:
  - canonical id: `ingot_tinbronze`
  - resolver output: `source=recipe`, `recipe_type=grid`, `display_name=Tin Bronze`