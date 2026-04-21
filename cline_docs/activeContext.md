# Active Context

## Current State (2026-04-20)

### Resolver + Data Integrity
- Pricing precedence is now correct and stable: **LR → Override → Recipe**.
- Cycle handling is hardened (cyclic paths remain partial/invalid, no bogus fallback totals).
- `crafting_breakdown` partial flag behavior is fixed.
- `_is_reverse_recipe` broad heuristic filter was tested and then removed because it was too broad (broke rope/flaxtwine behavior).
- Reverse contamination is handled with targeted DB deletion of known-bad recipes instead of broad filtering.

### Pricing Rules (Current)
- Implemented and active:
  - Anvils: `10 × parent ingot LR`
  - metalnailsandstrips: `parent ingot LR / 4`
  - gear_rusty: `5 CS` flat
  - Pelts: `0.8 × (prepared hide LR unit)` by tier mapping
  - Crushed materials: ingot-based conversion
  - Powdered materials: ingot-based conversion
- Dynamic hoops rule was added, validated as unnecessary, and removed (recipe behavior already correct).

### UI Status
- FTA/Guild pricing UI removed.
- Manual Override label replaced with **Set Price** badge.
- Loading skeleton added.
- applySuggestion spacing bug fixed.
- Partial cost badge behavior fixed.

### Deployment / Ops
- Partial Railway sync script created.
- Code deployed through GitHub integration.
- Railway DB synced via `scripts/sync_railway.py`.

### Architecture Decision: Armor Sets
- Do not duplicate canonical entries to represent set-vs-piece behavior.
- Keep individual pieces recipe-driven.
- Add manual LR links for full armor set canonicals in `scripts/apply_manual_lr_links.py`.
- User-facing behavior: searching a full set returns LR set price; searching a piece returns crafting cost.

## Immediate Next Steps
1. Complete LR row ↔ armor set mapping confirmations and add/verify manual links.
2. Keep reverse recipe mitigation targeted (no broad classifier unless proven safe by regression tests).
3. Rewrite `scripts/audit_pricing_gaps.py` to call resolver directly for authoritative metrics.
4. Rerun full pipeline + audit and refresh final gate baseline once metrics stabilise.

## Rebrand + Operations Addendum (2026-04-21)

### Brand / Theme (Now Active)
- App identity is **Runic Abacus**.
- Explicitly retired names for copy and docs: **Merchant Ledger**, **Runiic**.
- Character framing for UX/copy: **Bomrek, runesmith of Tharagdum (far north)**.
- Tagline: **"Carved in stone, priced in gold"**.

### UI Language + Visual Direction
- Preferred UX copy terms: Commission, Market Conditions, Appraise, Smith's Tithe, Reveal Runes, Empire Rate.
- Color anchors:
  - Base dark stone: `#0d0d0f`
  - Amber rune glow: `#c8922a`, `#e8a830`
  - Arcane accent: `#7eb8d4`
- Typography:
  - Headings: **Cinzel**
  - Body: **Crimson Pro**

### Railway Live DB / Deployment Pointers
- Active Railway Postgres service: **Postgres-YbNR**.
- Active external DSN: `postgresql://postgres:gMilkqIwIFsQgJRQYonBHKJyFgZGPfaE@shinkansen.proxy.rlwy.net:38376/railway`.
- Active web app: `web-production-7eee5.up.railway.app`.
- Dead/legacy DB endpoint to avoid: `maglev.proxy.rlwy.net:33597`.

### Rebuild Method (if full restore needed again)
1. `pg_dump` local (`--no-owner --no-acl`) to `full_snapshot.sql`.
2. Restore snapshot to Railway with `psql <RAILWAY_DSN> -f full_snapshot.sql`.
3. Run `scripts/build_aliases.py` **locally first**, then dump/push `item_aliases`.
4. Re-enable trigram search with `CREATE EXTENSION pg_trgm` on Railway.
5. Do **not** run aliases build via `railway_wrapper.py` (too slow over network).
