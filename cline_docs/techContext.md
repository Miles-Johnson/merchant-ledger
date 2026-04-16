# Tech Context

## Environment
- OS: Windows 10
- Working directory: `C:/Users/Kjol/projects/merchant-ledger`
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
2. `scripts/parse_recipes_json.py`
3. `scripts/build_canonical_items.py`
4. `scripts/build_aliases.py`
5. `scripts/link_recipes.py`
6. `scripts/apply_manual_lr_links.py`

## API Surface (Core)
- `GET /health`
- `GET /search?q=<query>&limit=<n>`
- `POST /calculate`
  - supports order text and optional pricing/selection controls (including material override path).
  - structured error semantics:
    - `400` invalid request/input
    - `404` unresolved/not found
    - `200` + status flag for recoverable partial outcomes
    - `500` unexpected internal failures

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
- Parser integrity is fail-fast: any recipe parse/insert failure must produce non-zero process exit.

## Update (2026-04-16): Runtime/Parser/API Corrections
- Runtime pricing precedence is now explicitly LR-first with fallback `LR → recipe decomposition → manual override`.
- Legacy FTA/Guild pricing precedence path has been removed from active runtime behavior.
- Resolver includes stronger variant-intent handling (`game_code` inference fallback + material-aware variant selection).
- Multi-placeholder recipe inputs are fully expanded via Cartesian product insertion.

## Historical Material
Detailed technical chronology moved to:
- `cline_docs/deprecated/techContext_historical.md`


## Update (2026-04-06): Repository Location
- **New project root:** `C:/Users/Kjol/projects/merchant-ledger`
- Previous mixed path under Vintage Story data is no longer the active project root.
- Git remote: `origin -> https://github.com/Miles-Johnson/merchant-ledger.git`
