# Progress

## Session 2026-04-19/20 (Current Authoritative Rundown)

### Resolver and Data Corrections
- Fixed pricing precedence to **LR → Override → Recipe**.
- Hardened cycle handling.
- Fixed `crafting_breakdown` partial-flag bug.
- Added then removed broad `_is_reverse_recipe` general filter after regressions (too broad; broke rope/flaxtwine paths).
- Replaced broad reverse-recipe filtering with targeted DB deletion of known bad reverse recipes.

### Pricing Rule State
- Implemented and active:
  - Anvils: `10 × ingot`
  - metalnailsandstrips: `ingot / 4`
  - gear_rusty: `5 CS` flat
  - Pelts: `0.8 × prepared hide LR unit`
  - Crushed materials: ingot-derived conversion
  - Powdered materials: ingot-derived conversion
- Dynamic hoops rule was tested and removed as unnecessary (recipe behavior already correct).

### UI Changes Completed
- Removed FTA/Guild pricing display.
- Renamed/standardized Set Price badge.
- Added loading skeleton.
- Fixed applySuggestion spacing bug.
- Fixed partial cost badge behavior.

### Deployment / Sync
- Added partial sync capability for Railway workflow.
- Deployed code via GitHub integration.
- Synced Railway DB via `scripts/sync_railway.py`.

## Architecture Direction (Approved)
- Do not create duplicate canonicals for armor sets.
- Keep individual armor pieces recipe-priced.
- Represent full armor sets through manual LR links in `scripts/apply_manual_lr_links.py`.
- Main remaining work: confirm LR row ↔ set mapping combinations and add links.

## Remaining Work
- Rewrite `scripts/audit_pricing_gaps.py` to call resolver directly.
- Refresh final gate baseline after post-change metrics stabilise.
- Complete armor set LR mapping confirmation + link coverage.

## Session 2026-04-21 (Rebrand + Ops Capture)

### Brand and UX Identity
- Rebrand applied in project context docs: app is now **Runic Abacus**.
- Confirmed thematic framing: **Bomrek, runesmith of Tharagdum**.
- Added canonical tagline: **"Carved in stone, priced in gold"**.
- Captured visual language tokens (dark stone / amber glow / arcane blue-white) and font stack (Cinzel + Crimson Pro).
- Captured preferred UI terminology set: Commission, Market Conditions, Appraise, Smith's Tithe, Reveal Runes, Empire Rate.

### Railway Runtime Facts Captured
- Active Postgres service: **Postgres-YbNR**.
- Active DSN recorded (`shinkansen.proxy.rlwy.net:38376`).
- Active web app recorded: `web-production-7eee5.up.railway.app`.
- Dead legacy DB endpoint recorded and marked avoid: `maglev.proxy.rlwy.net:33597`.

### Known Fixes Recorded
- Metalplate items are correctly unlinked from LR (recipe decomposition path restored).
- Guards in `scripts/build_canonical_items.py` and `scripts/apply_manual_lr_links.py` captured as part of fix history.
- FTA system removal from codebase documented as complete.
- `scripts/build_aliases.py` FTA join removal documented.
- `api/app.py` `sslmode` kwarg bug documented as fixed.
- Railway healthcheck route change (`/search?q=iron` → `/health`) documented.
