# Product Context

## Purpose
This project provides a **Vintage Story order pricing app** that returns costs in **Copper Sovereigns**.

It resolves user-entered item names, maps them to canonical game items, and prices them through market sources and/or recipe decomposition.

## Core Problem
Vintage Story data is fragmented across base content, many mods, and multiple market sources. The system must unify:
- recipe identity,
- alias/name resolution,
- multi-source market pricing,
- deterministic fallback costing.

## Product Scope (Current)
- **Authoritative runtime:** Gen 3 stack only.
- **Primary data model:** canonical schema (`recipes`, `recipe_ingredients`, `canonical_items`, `item_aliases`).
- **Primary user workflows:**
  - search item names,
  - calculate item/order cost,
  - inspect recipe ingredient breakdown where applicable.

## Pricing Policy
1. **LR (Empire) price** is primary/default.
2. **FTA price** is used when LR is unavailable (and can also be shown alongside LR).
3. **Recipe costing** is used when market pricing is unavailable or when the resolver intentionally chooses recipe path.
4. **Manual overrides** are used for specific economic corrections (e.g., nuggets, processed ore chain).

## Locked Costing Semantics
- **Cooking:** minimum viable ingredient set only (`minQuantity` baseline; optional slots excluded).
- **Smithing:** ingredient quantity derived from voxel fill count (`ceil(filled_bits / 42)`).
- **Alloy:** ratio-aware quantities supported (midpoint from `ratio_min`/`ratio_max` when needed).

## Current Status Summary
- Direct JSON recipe parser path is active in pipeline.
- Legacy extraction/parser paths are deprecated and retained only for reference.
- Final-gate validation has improved to near-complete pass state; remaining issue is variant intent for `lantern up (iron)`.

## Historical Material
Detailed chronological history has been moved to:
- `cline_docs/deprecated/productContext_historical.md`
