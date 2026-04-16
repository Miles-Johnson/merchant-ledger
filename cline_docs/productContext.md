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
2. **Recipe costing** is used when LR pricing is unavailable.
3. **Manual overrides** are applied last as final fallback/economic correction.

## Locked Costing Semantics
- **Cooking:** minimum viable ingredient set only (`minQuantity` baseline; optional slots excluded).
- **Smithing:** ingredient quantity derived from voxel fill count (`ceil(filled_bits / 42)`).
- **Alloy:** ratio-aware quantities supported (midpoint from `ratio_min`/`ratio_max` when needed).

## Current Status Summary
- Direct JSON recipe parser path is active in pipeline.
- Legacy extraction/parser paths are deprecated and retained only for reference.
- Final-gate validation issue for `lantern up (iron)` has been resolved in the latest task bundle.

## Historical Material
Detailed chronological history has been moved to:
- `cline_docs/deprecated/productContext_historical.md`

## Update (2026-04-16): Tasks 0–6 Applied
- Pricing model has been simplified and old FTA/Guild runtime pricing paths were removed from active precedence.
- **Effective precedence is now locked to:**
  1. LR direct price
  2. recipe decomposition
  3. manual override (applied last)
- Resolver behavior and variant intent selection were corrected for lantern/material pathways and now match expected deterministic outputs.
- Parser integrity is fail-fast: parse/insert failures now return non-zero exit status so corpus corruption is surfaced by pipeline runs.
- `/calculate` now returns structured status semantics (400/404/200+flag/500) instead of collapsing all failures to 500.
- Final validation intent for the previously failing lantern case is resolved (15/15 target reached per task notes).
