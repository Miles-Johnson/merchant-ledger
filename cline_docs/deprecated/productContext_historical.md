# Product Context

## Purpose
- This workspace is a Vintage Story data directory used by the player profile/server setup.
- Current task purpose: identify and extract recipe JSON data for base-game and modded items so the user can import recipe data into a database.

## Problem Being Solved
- Recipe data is spread across unpacked mod/base-game content.
- User needs a reliable way to locate item recipe JSONs and extract them in a structured, repeatable way.

## Expected Behavior
- Locate where base and mod recipe JSON files live in `Cache/unpack`.
- Determine which recipe JSONs correspond to items.
- Prepare extraction approach and output format suitable for database ingestion.

## Update 2026-03-19
- Recipe extraction has been completed for **base game + all unpacked mods**.
- Output workbook generated at: `C:\Users\Kjol\Desktop\vs_recipes.xlsx`.
- Workbook schema (all sheets):
  - `Source Mod`
  - `Recipe Type`
  - `Output Item`
  - `Output Qty`
  - `Ingredients`
- User-confirmed follow-up direction: next task will be loading this Excel data into a local PostgreSQL database.

## Update 2026-03-20
- Product direction clarified:
  - App must calculate total sovereign cost for arbitrary user orders.
  - Example workflow: user enters `4 iron plates, 1 bismuth lantern`, app resolves recursive ingredient chains and computes total crafting cost.
- Pricing behavior requirements:
  - Support selectable settlement pricing context (industrial/market/religious variants).
  - Show both:
    - listed price from Lost Realm sheets
    - separately calculated recipe-derived crafting cost
- Scope decision:
  - Include base game + Lost Realm mod recipes where possible.
  - Build phases:
    1. Data/import + normalized recipe layer
    2. Mapping + recursive cost engine
    3. Browser UI (deferred to next context window)

## Update 2026-03-20 (UI/UX + Pricing Priority)
- UX direction updated for broader audience:
  - UI should be newcomer-friendly and explicitly use "Copper Sovereigns" terminology.
  - Labels, helper text, and table headings should prioritize clarity over developer language.
- Pricing priority rule clarified:
  - If an item has an LR listed price, that price is authoritative and should be used directly.
  - Recipe decomposition is used for cost derivation only when no LR listed price exists.
- Current product gap identified:
  - Users can enter LR-listed items that fail lookup when no recipe alias exists.
  - Example: `iron plate armor` should resolve from LR artisanal goods even without a recipe-output alias match.
- Next product requirement for upcoming task:
  - Add LR-name resolution fallback (and ideally LR-first search behavior) in order parsing.
  - Improve assisted entry (autocomplete) so users can select known items instead of guessing names.

## Update 2026-03-23 (Code Archaeology + Current Product Reality)
- Product purpose remains: help users price Vintage Story item orders in **Copper Sovereigns** using Lost Realm market data and recipe fallback.
- Current product state is split across **two parallel app generations**:
  1. **Gen 2 app path**: Flask + server-rendered UI (`webapp/app.py` + `webapp/templates/index.html`) using `vs_cost_calculator.py` and `vs_recipe_outputs`/`vs_recipe_ingredients` schema.
  2. **Gen 3 app path**: API-first backend (`api/app.py`) + React frontend (`webapp/src/App.jsx`) using `scripts/resolver.py` and canonical recipe schema (`recipes`, `recipe_ingredients`, `canonical_items`, `item_aliases`).
- User-visible capability in both paths is similar (order input + settlement-aware pricing), but technical foundations differ.
- Product risk identified: both generations use a table named `lr_items` with differing assumptions and ingestion paths, which can cause drift or replacement of expected data model if mixed pipelines are run.
- Immediate product direction should prefer one canonical runtime path (Gen 3 appears most structured) and keep other path as legacy fallback until deliberate consolidation.

## Update 2026-03-23 (Canonical Casing/Data Integrity Fix)
- Product-critical data integrity issue was identified and fixed in the canonical pipeline:
  - Mixed-case game codes (`Item:`/`Block:`) were being treated as distinct from lowercase (`item:`/`block:`).
  - This created duplicate canonicals and incorrect recipe link targets (notably candle: `candle` vs `candle_2`).
- Outcome after fix and rebuild:
  - Candle cooking recipe correctly resolves to canonical `candle`.
  - Case-split canonical duplicates from prefix casing were eliminated.
  - Recipe linkage achieved full output linkage (`Recipes unlinked: 0` in validation run).
- Product relevance:
  - Improves pricing correctness for all affected items, not only candle.
  - Reduces silent data drift caused by inconsistent source casing across imported recipes/mods.

## Update 2026-03-26 (Gen 3 Consolidation + FTA Direction)
- Runtime decision finalized: **Gen 3 is now the sole active runtime path**.
  - Active stack: `api/app.py` + `scripts/resolver.py` + React frontend + canonical schema.
- **Gen 2 is deprecated legacy** and retained only for reference/backfill safety:
  - `webapp/app.py` (Flask/Jinja)
  - `vs_cost_calculator.py`
  - `vs_recipe_outputs` / `vs_recipe_ingredients`-based path
- Pricing source strategy updated:
  - **LR (Empire) prices remain primary/default** across the app.
  - **Faelyn Trade Association (FTA) guild prices** are being integrated as a supplementary source.
  - UI should show LR and FTA side-by-side where available.
  - For items with only FTA coverage (especially food, alcohol, medicinal, dyes, transport), FTA is authoritative.
- Upcoming product feature:
  - Add artisan pricing toggle for **material + 20% labor**.

## Update 2026-03-26 (FTA Integration Completed in Pipeline)
- Gen 3 remains the single active product/runtime path.
- Full canonical pipeline now ingests **both** price sources in one run:
  - LR prices (primary/default)
  - FTA prices (supplementary + authoritative fallback when LR is absent)
- Canonical build now includes FTA linking pass so canonical items can carry LR and FTA links concurrently.
- Product/API expectation is now multi-source aware:
  - search results can return both `price_current` (LR) and `fta_price`
  - calculator returns source-aware pricing with LR-first then FTA fallback behavior.

### Full Pipeline Run Sequence
1. `python run_pipeline.py`
2. `python api/app.py`
3. Validate API responses:
   - `curl "http://localhost:5000/search?q=iron&limit=5"`
   - `curl -X POST "http://localhost:5000/calculate" -H "Content-Type: application/json" -d "{\"order\":\"1 lantern up\",\"settlement_type\":\"current\"}"`

## Update 2026-03-26 (Diagnosis Impact on Product Correctness)
- Diagnosis-only review identified two product-impacting risks in current behavior:
  1. wildcard variant groups may be omitted in costing due to parser/resolver primary-variant mismatch
  2. smithing-derived outputs (e.g. metal plates) may be undercosted because smithing ingredient quantity currently defaults to 1
- Additional practical risk:
  - loss of item/block attribute specificity in extraction (e.g. lantern material/glass) can widen recipe matching and increase resolver branch count.
- Product consequence if unaddressed:
  - inaccurate crafted-cost totals and unstable/slow calculations on highly variant-rich items.
- Priority for upcoming implementation cycle:
  1. fix variant-group selection semantics
  2. add memoized resolver subtree reuse
  3. implement smithing pattern-based quantity derivation
  4. preserve/encode relevant attribute specificity where required for recipe identity.

## Update 2026-03-26 (Resolver Performance Fix Delivered)
- Product-critical performance fix has now been implemented in the active Gen 3 runtime.
- `scripts/resolver.py` now memoizes recursive subtree cost results within a single `/calculate` request.
  - Cache is request-scoped (created once in `process_order`, passed downward), not module-global.
  - Cached reuse supports quantity scaling so repeated canonical subtrees are not recomputed from scratch.
- Recipe alternative behavior updated:
  - default now uses **first successful recipe wins** to reduce unnecessary alternative traversal.
  - optional UI/API opt-in added via `include_all_alternatives=true` when exhaustive alternatives are desired.
- Product validation outcomes for this fix set:
  - `Clothes Nadiya Waist Miner Accessories` calculation completed in `0.258s` (<5s target).
  - `copper ingot` still resolves correctly via LR listed price.
  - representative recipe fallback item (`bismuth lantern`) still returns recipe ingredient breakdown.

## Update 2026-03-26 (Correctness Fixes Delivered: Wildcard Primary + Attributed Inputs)
- Product correctness scope delivered for parser/extractor/linker path:
  1. wildcard/grouped ingredient expansions now retain a deterministic primary variant
  2. attribute-specific ingredient identity is preserved in extracted/parsed recipe inputs
  3. canonical linking supports graceful fallback from attributed code to base code
- User-visible outcome validation:
  - `Clothes Nadiya Waist Miner Accessories` no longer returns empty/zero top-level ingredient breakdown.
  - API result now resolves as recipe with non-zero top-level ingredient costs.
- Current product state note:
  - This item remains partially resolved overall due to unrelated deep-chain unresolved materials; this is now tracked as a separate completeness-coverage concern rather than a wildcard/attribute identity bug.

## Update 2026-03-26 (Smithing Quantity Correctness via Manual Lookup)
- Product-critical smithing undercount risk has been mitigated with a pragmatic manual mapping approach.
- Implemented behavior:
  - smithing outputs now use quantity overrides from `data/smithing_quantities.json`
  - parser falls back safely to qty=1 when output is not yet mapped
  - unmapped smithing outputs emit warnings for iterative coverage improvements
- Confirmed correctness outcome for target case:
  - `item:metalplate-iron` ingredient requirement is now `2x item:ingot-iron` in canonical recipe tables (previously defaulted to 1)
- Product impact:
  - improves crafted-cost accuracy for mapped smithing items immediately
  - establishes maintainable path for incremental smithing quantity coverage without implementing full voxel-bit math
- Operational caveat captured:
  - concurrent pipeline/link reruns can deadlock; clean serial pipeline execution is required for stable verification.

## Update 2026-03-27 (Direct-Price Suppression + Gold/Awlthorn Correctness)
- Product behavior correction delivered:
  - direct-priced items (LR/FTA) now return market price without recipe-alternative breakdown payload.
  - UI no longer presents recipe details for directly priced entries (e.g. Gold, Iron Ingot).
- Canonical-linking correctness improved for Gold-family outputs:
  - template placeholder matching was tightened to avoid broad matches over hyphenated outputs.
  - `item:awlthorn-gold` remains linked to `Awlthorn Gold`, not generic `Gold`.
- Validation snapshot:
  - `Gold` resolves to LR 11.00 with no breakdown payload.
  - `Clothes Nadiya Waist Miner Accessories` remains recipe-resolved with ingredient breakdown.
  - `Metal Plate Iron` resolves via recipe using `2x Iron` ingredient.
- Data-state note:
  - In current DB, `Bread` and `Iron Plate` both have LR-linked pricing and therefore resolve LR-first by policy.

## Update 2026-03-27 (Nugget Unit Pricing Corrected)
- Product scope addition: individual nugget pricing is now supported where nugget canonicals exist and LR ingot baseline is available.
- Pricing rule (user-confirmed):
  - `1 nugget = 5 material units`
  - `1 ingot = 100 material units`
  - therefore `20 nuggets = 1 ingot` and `nugget_unit = ingot_unit / 20`.
- Product behavior correction:
  - prior intermediate implementation used `/5` and was corrected to `/20`.
  - nugget values are now economically consistent with ingot totals.
- Validation example (Empire baseline):
  - Copper ingot = `6.00`
  - Copper nugget = `0.30`
  - `20x` copper nuggets total `6.00`.

## Update 2026-04-04 (Recipe Architecture Decision: Direct JSON Parsing)
- Product direction clarified after architecture review:
  - Keep Gen 3 canonical runtime and pricing model.
  - Replace lossy recipe ingestion path (`extract_vs_recipes.py` + workbook + text re-parse) with direct JSON parser.
- Product rationale:
  - Current gap is recipe semantic fidelity (by recipe type), not canonical/runtime structure.
  - Accurate crafted-cost decomposition requires preserving recipe-type semantics end-to-end.
- User-approved implementation strategy:
  - Execute one recipe type at a time (incremental and testable).
  - Cooking pricing policy for now: **minimum viable ingredient set** using `minQuantity`.
  - Future enhancement retained: user-configurable add-ins/extra ingredients for cooking cost customization.

### Planned Product Delivery Sequence
1. Build direct parser scaffold (`scripts/parse_recipes_json.py`) with source discovery + typed handler stubs.
2. Implement and validate handlers in order:
   - grid
   - smithing
   - knapping + clayforming
   - alloy
   - barrel
   - cooking (minimum-only policy)
   - mod catch-all
3. Integrate parser into canonical pipeline (`run_pipeline.py`) replacing old text intermediary path.
4. Validate linking + pricing regression set across representative recipe families.
5. Deprecate legacy extractor/text-parser scripts (retain for reference).

## Update 2026-04-04 (Step 1.0 Completed)
- Delivered the first approved milestone in the direct-JSON parser rollout:
  - `scripts/parse_recipes_json.py` scaffold is implemented.
- Current delivered behavior:
  - discovers base + mod recipe JSON files
  - parses with JSON5
  - detects recipe type from path
  - truncates `recipes` + `recipe_ingredients` at startup
  - includes shared helpers + per-type stubs
  - reports per-type discovery summary
- Validation result from run:
  - discovery and summary reporting complete
  - zero inserts by design (handler stubs)
  - clean script exit
- Product implication:
  - architecture transition is now active in codebase and ready for Step 1.1 (grid semantics) without changing runtime resolver/API yet.

## Update 2026-04-04 (Step 1.1 Completed: Grid Semantics Live)
- Direct JSON parser now includes a working `grid` handler in `scripts/parse_recipes_json.py`.
- Delivered grid product semantics:
  - ingredient quantity from `ingredientPattern` symbol occurrence counting
  - per-slot quantity multiplier support (`quantity` / `stacksize` / `stackSize`)
  - wildcard variant expansion via `allowedVariants` + ingredient `name` correlation
  - template substitution in outputs/ingredients where `{placeholder}` appears
  - tool exclusion (`isTool=true`)
- Validation against user-requested samples passed:
  - `lantern-up` iron variant resolves expected ingredient set and quantities
  - `chest` resolves expected plank/nails counts
  - plate armour sample resolves expected chain + plate counts
- Product state now:
  - Step 1.0 + 1.1 complete
  - next product milestone is Step 1.2 smithing quantity semantics (`ceil(bits/42)`) in direct parser.

## Update 2026-04-04 (Step 1.3 Completed: Knapping + Clayforming Semantics)
- Direct JSON parser now includes working `knapping` and `clayforming` handlers in `scripts/parse_recipes_json.py`.
- Delivered product semantics for both types:
  - singular `ingredient` + `pattern` structure parsed directly
  - `allowedVariants` expansion aligned with smithing behavior
  - output/ingredient template substitution by ingredient `name` placeholder
  - fixed input quantity policy:
    - knapping always consumes `1x` source item
    - clayforming always consumes `1x` clay ball
- Validation outcome:
  - `item:knifeblade-flint` resolves with `1x` flint-family input
  - clay bowl raw outputs (`block:bowl-*-raw`) resolve with `1x` color clay input.
- Product state now:
  - Step 1.0, 1.1, 1.2, 1.3 complete
  - next product milestone is Step 1.4 alloy semantics in direct parser.

## Update 2026-04-04 (Step 1.4 Completed: Alloy Semantics)
- Direct JSON parser now includes a working `alloy` handler in `scripts/parse_recipes_json.py`.
- Delivered alloy product semantics:
  - one `recipes` row per alloy recipe (`recipe_type='alloy'`, output qty baseline `1`)
  - one `recipe_ingredients` row per alloy ingredient with:
    - `ratio_min` from JSON `minratio`
    - `ratio_max` from JSON `maxratio`
    - `qty` as midpoint per 1 output ingot: `(ratio_min + ratio_max) / 2`
  - invalid/empty alloy ingredient sets are guarded by skipping ingredient rows and removing orphan recipe rows.
- Validation outcome:
  - `item:ingot-tinbronze` alloy row resolves as expected:
    - tin `0.08–0.12` -> midpoint `0.10`
    - copper `0.88–0.92` -> midpoint `0.90`
- Product state now:
  - Step 1.0, 1.1, 1.2, 1.3, 1.4 complete
  - next product milestone is Step 1.5 barrel semantics in direct parser.

## Update 2026-04-04 (Step 1.5 Completed: Barrel Semantics)
- Direct JSON parser now includes a working `barrel` handler in `scripts/parse_recipes_json.py`.
- Delivered barrel product semantics:
  - one `recipes` row per barrel output variant
  - one `recipe_ingredients` row per ingredient line
  - liquid ingredient quantity uses `consumeLitres` (or lowercase `consumelitres`) when present, otherwise `litres`
  - solid ingredient quantity uses `quantity`
  - `sealHours` is treated as process metadata and ignored for cost rows
  - output quantity uses `stackSize`/`stacksize` (fallbacks: `quantity`, `litres`)
- Validation outcome for user target case:
  - `item:leather-normal-plain` (small hide variant) resolves as expected:
    - `item:strongtanninportion x2` (litres consumed)
    - `item:hide-prepared-small x1`
    - output qty `1`
- Product state now:
  - Step 1.0, 1.1, 1.2, 1.3, 1.4, 1.5 complete
  - next product milestone is Step 1.6 cooking semantics (minimum-only policy).

## Update 2026-04-04 (Step 1.6 Completed: Cooking Semantics)
- Direct JSON parser now includes a working cooking handler in `scripts/parse_recipes_json.py`.
- Delivered cooking product semantics:
  - baseline ingredient qty uses `minQuantity`
  - optional slots (`minQuantity=0`) are excluded
  - each required slot's `validStacks` is stored as an interchangeable variant group in `recipe_ingredients`
  - one recipe row per cooking recipe, ingredient rows grouped by slot
- Additional correctness fix delivered:
  - meal-style cooking recipes that omit `cooksInto` now resolve output as `item:meal-<recipe.code>`.
- Validation outcomes for user-target checks:
  - `candle` resolves to required minimum ingredients `3x beeswax + 1x flaxfibers`
  - `meatystew` resolves to `item:meal-meatystew` with only required protein slot included (optional add-ins excluded).

## Update 2026-04-04 (Step 1.7 Completed: Mod Catch-all + Pipeline Switch)
- Direct-JSON parser rollout milestone completed and validated end-to-end.
- Product behavior change:
  - pipeline no longer fails hard on unknown/mod recipe schemas.
  - unknown recipe shapes now use best-effort extraction so recipe coverage improves without crash loops.
- Catch-all product semantics now active in `scripts/parse_recipes_json.py`:
  - attempts extraction from `output`, `ingredient`, and `ingredients`
  - inserts recipe rows when output is available
  - inserts extractable ingredient rows with best-effort quantity parsing
  - warns with recipe type + filepath context
  - suppresses duplicate unknown-type warnings per `(type, filepath)` to reduce log flood
  - per-recipe errors are isolated via dispatch `try/except` and do not abort the full run
- Pipeline architecture change now active in `run_pipeline.py`:
  - removed old parser path (`scripts/ingest_recipes.py` + `scripts/parse_recipes.py`)
  - active parser stage is now `scripts/parse_recipes_json.py`
  - remaining canonical/linking stages preserved (`ingest_lr_prices`, `ingest_fta_prices`, `build_canonical_items`, `build_aliases`, `link_recipes`, `apply_manual_lr_links`)
- Operational stability fix:
  - completion output switched to ASCII status tags (`[OK]` / `[ERROR]`) to avoid Windows cp1252 emoji encoding crashes.
- End-to-end validation snapshot:
  - pipeline completed with `[OK] Pipeline + verification complete.`
  - `lr_items_loaded: 475`
  - `fta_items_loaded: 277`
  - `canonical_with_lr_link: 1089`
  - `canonical_with_fta_link: 277`
  - `canonical_with_both_links: 258`
  - recipe row growth after Step 1.7:
    - `recipes: 18915 -> 19364`
    - `recipe_ingredients: 47242 -> 47281`

## Update 2026-04-04 (Linkage Audit Outcome)
- Product-level linkage quality checkpoint executed after full pipeline run.
- Requested acceptance criteria status:
  - Recipe output linkage target: **met** (`0` unlinked).
  - Ingredient linkage regression check: **passed** (`81` unlinked vs baseline `83`; improved by 2).
- User-requested item validations all passed:
  - `metalplate-iron` links correctly and retains smithing ingredient quantity `2x ingot-iron`.
  - `candle` links correctly with baseline cooking inputs (`3x beeswax`, `1x flaxfibers`).
  - `lantern-up` links correctly; validated rows include `metalplate-iron` variant path.
  - `leather-normal-plain` links correctly with expected tannin/hide barrel inputs.
- Smithing quantity policy confirmation:
  - Active product path uses direct JSON smithing voxel math (`ceil(bits/42)`) and does **not** depend on `smithing_quantities.json`.

## Update 2026-04-04 (Final Validation Gate Status)
- Final-gate API validation was executed for required recipe families (grid/smithing/barrel/cooking/alloy/knapping/multi-step).
- Gate artifact outputs added:
  - `scripts/final_gate_validate.py`
  - `data/final_gate_validation.json`
  - `data/final_gate_validation.txt`
- Current product status at gate:
  - **5/9 pass**.
  - pass: smithing (`metal plate iron`, `pickaxe head iron`), cooking (`candle`), alloy (`tin bronze ingot`), multi-step (`plate body armor iron`).
  - fail: `lantern up`, `chest`, `leather`, `flint knife blade`.
- Product-impacting behavior still requiring remediation:
  1. variant path selection can choose unexpected material branch (`lantern up` -> tin bronze plate instead of iron plate)
  2. alias/display-name coverage gaps can yield unresolved plain-name inputs (`chest`)
  3. disambiguation may pick non-target recipe family (`leather` -> grid panel path instead of barrel tanning)
  4. knapping item name-to-canonical resolution remains incomplete for user phrasing (`flint knife blade`).

## Update 2026-04-04 (Legacy Script Deprecation Headers Applied)
- Legacy recipe extraction/staging parser scripts are now explicitly marked deprecated in-file.
- Files updated with top-of-file deprecation headers:
  - `extract_vs_recipes.py`
  - `scripts/ingest_recipes.py`
  - `scripts/parse_recipes.py`
  - `scripts/ingest_recipes_json.py`
- Header message standard:
  - `DEPRECATED — superseded by parse_recipes_json.py as of 2026-04-04`
  - `Retained for reference only. Do not run as part of the pipeline.`
- Product implication:
  - Reduces risk of operators accidentally executing retired ingest paths.
  - Reinforces direct JSON parser (`scripts/parse_recipes_json.py`) as the canonical recipe ingestion path.

## Update 2026-04-04 (Low-Tier LR Display-Name Inheritance Rule Fix)
- Product regression addressed in canonical naming:
  - low-confidence LR matches now inherit LR display name only when the LR name actually overlaps the game-code tail.
- Rule behavior (low tier only):
  - extract LR words longer than 3 chars
  - normalize plural trailing `s`
  - if any normalized LR word appears in game-code tail -> keep LR name
  - else fallback to game-code-derived display name
- Product outcomes validated:
  - `item:ingot-tinbronze` keeps `Tin Bronze`
  - `item:feather` no longer inherits `Leather` (shows `Feather`)
- End-to-end run status for this fix cycle:
  - `python run_pipeline.py` succeeded
  - `python scripts/final_gate_validate.py` ran successfully (current gate snapshot: 3/9).

## Update 2026-04-04 (Final Gate Expansion + Persistent Regression Baseline)
- Product validation harness scope expanded from 9 to 15 checks in `scripts/final_gate_validate.py`.
- Product-acceptance adjustment for plate armor pricing paths:
  - strict ingredient identity requirement for `plate body armor iron` removed.
  - accepted outcomes now include both:
    - recipe/grid cheapest-path result,
    - LR direct-price result (authoritative for armor market pricing when resolver returns LR).
- Added spot-check coverage to reduce blind regression risk in fixed families:
  - bismuth bronze ingot
  - copper ingot
  - flint arrowhead
  - iron axe head
  - tannin
  - iron ingot
- Added persistent baseline/regression signaling artifacts:
  - baseline state file: `data/final_gate_baseline.json`
  - human report append mode: `data/final_gate_validation.txt`
  - machine report includes per-case `regression` flag: `data/final_gate_validation.json`
- Current product validation snapshot after expansion:
  - `Passed 9 / 15`
  - `Regressions: 0` (first baseline initialization run for expanded set).

## Update 2026-04-04 (Leather Alias Injection + Resolver Ranking Adjustment)
- Product disambiguation remediation was applied to improve plain-query routing for leather family lookups.
- Alias-layer change delivered in `scripts/build_aliases.py`:
  - targeted short aliases now injected for barrel output canonical:
    - `item:leather-normal-plain` gains `leather` and `leathers` aliases.
- Resolver ranking change delivered in `scripts/resolver.py` (`resolve_canonical_id`):
  - recipe-family rank moved earlier in ORDER BY chains (after similarity) for alias and display-similarity selection stages.
  - recipe-family ordering currently encoded as:
    - alloy=0, smithing=1, barrel=2, grid=3, cooking=4, knapping=5, clayforming=5, else=6.
- Validation cycle executed:
  - `python run_pipeline.py` completed with `[OK] Pipeline + verification complete.`
  - `python scripts/final_gate_validate.py` produced current snapshot `Passed 3 / 9` for this run profile.
- Product-behavior spot checks from this run:
  - `leather` now resolves to canonical `leather_normal_plain` (identity fix applied), but chosen recipe branch remains `grid` in current resolver selection.
  - `leather panel` still resolves to panel/grid canonical (`panel_leather_type`), confirming no overreach from direct leather alias injection.
  - `tin bronze ingot` resolved as recipe/grid in this snapshot (not alloy-path expectation), indicating existing recipe-branch selection behavior still dominates post-resolution.