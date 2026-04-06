# Tech Context

## Environment
- OS: Windows 10
- Working directory: `c:/Users/Kjol/AppData/Roaming/VintagestoryData`
- Python: 3.12
- DB access via `.env` (`DATABASE_URL`)

## Active Stack (Authoritative)
- Backend API: `api/app.py`
- Resolver engine: `scripts/resolver.py`
- Recipe parser: `scripts/parse_recipes_json.py`
- Pipeline orchestrator: `run_pipeline.py`
- Canonical linkage/tooling:
  - `scripts/build_canonical_items.py`
  - `scripts/build_aliases.py`
  - `scripts/link_recipes.py`
  - `scripts/apply_manual_lr_links.py`

## Key Dependencies
- `psycopg2-binary`
- `json5`
- `python-dotenv`

## Canonical Pipeline Order (Current)
1. `scripts/ingest_lr_prices.py`
2. `scripts/ingest_fta_prices.py`
3. `scripts/parse_recipes_json.py`
4. `scripts/build_canonical_items.py`
5. `scripts/build_aliases.py`
6. `scripts/link_recipes.py`
7. `scripts/apply_manual_lr_links.py`

## API Surface (Core)
- `GET /health`
- `GET /search?q=<query>&limit=<n>`
- `POST /calculate`
  - supports order text and optional pricing/selection controls (including material override path).

## Data Model (Core Tables)
- `recipes`
- `recipe_ingredients`
- `canonical_items`
- `item_aliases`
- `lr_items`
- `fta_items`
- `price_overrides`

## Technical Constraints / Caveats
- Avoid concurrent pipeline/link runs; serial execution is required for stability.
- Stale DB sessions can leave `idle in transaction`; clear them before reruns if locking appears.
- Legacy scripts are retained for reference only and should not be used in active runbooks.

## Historical Material
Detailed technical chronology moved to:
- `cline_docs/deprecated/techContext_historical.md`


## Update (2026-04-06): Repository Location
- **New project root:** `C:/Users/Kjol/projects/merchant-ledger`
- Previous mixed path under Vintage Story data is no longer the active project root.
- Git remote: `origin -> https://github.com/Miles-Johnson/merchant-ledger.git`
