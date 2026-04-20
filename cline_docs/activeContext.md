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
