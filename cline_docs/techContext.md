# Tech Context

## Environment
- OS: Windows 10
- Project root: C:/Users/Kjol/projects/merchant-ledger
- Python: 3.12
- DB: PostgreSQL via DATABASE_URL from .env
- Mod cache: C:\Users\Kjol\AppData\Roaming\VintagestoryData\Cache\unpack

## Active Runtime Stack
- API: api/app.py
- Resolver: scripts/resolver.py
- Pipeline orchestrator: run_pipeline.py

## Authoritative Pipeline Order
1. scripts/ingest_lr_prices.py
2. scripts/compute_primitive_prices.py
3. scripts/parse_recipes_json.py
4. scripts/build_canonical_items.py
5. scripts/build_aliases.py
6. scripts/link_recipes.py
7. scripts/apply_manual_lr_links.py

## Key Diagnostics / Ops Scripts
- scripts/audit_pricing_gaps.py — gap snapshot (does NOT call resolver, known debt)
- scripts/diagnose_item.py — recipe tree + pricing status for one item
- scripts/final_gate_validate.py — gate check (baseline stale, needs rewrite)
- scripts/parse_recipes_json.py — authoritative recipe JSON parser
- scripts/sync_railway.py — synchronises local canonical/pricing state into Railway DB

## Schema Notes
- Primary IDs: canonical_items.id
- Core tables: canonical_items, item_aliases, recipes, recipe_ingredients, lr_items, price_overrides
- Deprecated/unused: fta_items, vs_recipe_*, recipe_staging
- recipe_ingredients has NO is_tool column — tools excluded at parse time, never inserted

## LR Workbook
- Authoritative price field: Current Price column
- INDUSTRIAL GOODS: column index 6
- AGRICULTURAL GOODS: column index 5
- Updated weekly — always ingest latest before pricing decisions

## Critical Invariants
- Never reorder pricing precedence without updating systemPatterns.md Pattern #2
- Never add tool cost logic to resolver — tools are excluded at ingestion
- Never use dated snapshot LR columns — Current Price only
- Run pipeline serially — no overlapping runs

## Deployment Notes (Railway)
- App code deploys via GitHub integration.
- DB updates are applied explicitly via `scripts/sync_railway.py`.
- Partial sync flows are acceptable for targeted updates when full re-sync is unnecessary.
