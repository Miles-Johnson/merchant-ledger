# Profiling Report: `scripts/build_canonical_items.py`

**Date:** 2026-04-16
**Wall-clock time:** 74.6s
**158M function calls** across 200 unique functions

---

## DB vs Python Time Split

| Segment      | Time (s) | % of Wall |
|--------------|----------|-----------|
| **DB total** | 0.52     | 0.7%      |
| **Python**   | 74.06    | 99.3%     |

**DB is negligible.** All 19 queries combined take < 0.6s. The slowest single
query is `INSERT INTO canonical_items` (0.25s, batch of 2440 rows). No DB
optimization is warranted.

---

## Top 3 Bottlenecks

### #1 — N x M SequenceMatcher Fuzzy Loop (73.7s / 98.8% of wall)

**Root cause:** `choose_best_lr_match()` is called 1,788 times (once per
game code needing LR linkage). Each call iterates over all 475 LR items
doing up to 4 matching passes (exact, suffix, contains, then **fuzzy**).
The fuzzy pass calls `SequenceMatcher(...).ratio()` for every unmatched
game code against every LR item.

**Evidence:**
- `choose_best_lr_match` cumtime: **73.7s** (1,788 calls)
- `SequenceMatcher.ratio()` called **796,100 times** (~1,788 x 445 residual LR items)
- `difflib.find_longest_match` alone: **24.0s** internal time (3.82M calls)
- `difflib.get_matching_blocks`: **7.1s** internal time
- `difflib.__chain_b`: **4.9s** internal time (re-indexes seq B on every call)
- `dict.get`: **9.9s** (62M calls -- SequenceMatcher internal hash lookups)

**This single function accounts for 98.8% of total runtime.**

### #2 — Repeated LR Name Normalization (9.1s / 12.2% of wall)

**Root cause:** `normalize_lr_name_for_match()` is called **2,472,014 times**
(~1,788 game codes x ~1,382 calls per game code across exact/suffix/contains/
fuzzy passes). The same 475 LR display names are re-normalized on every
iteration of every game code.

**Evidence:**
- `normalize_lr_name_for_match`: 2.30s tottime, 9.11s cumtime
- `normalize_for_compare`: 1.30s tottime, 4.01s cumtime (2,474,549 calls)
- `re.Pattern.sub`: 4.22s tottime (4,968,187 calls -- mostly from normalization)
- `str.strip`: 0.82s (5,010,708 calls)
- `str.lower`: 0.51s (2,506,897 calls)

### #3 — SequenceMatcher Re-Initialization Overhead (8.6s / 11.5% of wall)

**Root cause:** Each `SequenceMatcher(None, a, b).ratio()` call in the fuzzy
pass creates a new SequenceMatcher instance. `__chain_b()` rebuilds the
internal junk-filtering index for `seq2` (the LR name) on every call, even
though seq2 is the same 475 LR names repeated across all 1,788 game codes.

**Evidence:**
- `difflib.__chain_b`: 4.90s tottime (796,100 calls)
- `difflib.set_seq2`: 0.35s + 8.92s cumtime (calls __chain_b)
- `dict.setdefault`: 1.95s (10,193,439 calls -- __chain_b building b2j index)

---

## Estimated Improvement Opportunities

| Opportunity | Current Cost | Estimated Savings | Approach |
|------------|-------------|-------------------|----------|
| **Pre-index exact/suffix/contains lookups into dicts** | ~9s (normalization overhead) | **~55-65s** (eliminates 95%+ of fuzzy pass invocations) | Build `{normalized_name: LRItem}` dict once; check exact/suffix/contains via O(1) dict lookups before any fuzzy pass. Most of the 1,788 game codes that currently run all 4 passes would short-circuit earlier. |
| **Pre-compute normalized LR names** | 9.1s cumtime | **~8-9s** | Normalize each LR display name once into a list before the game-code loop. Pass pre-normalized names into matching functions. Eliminates 2.47M redundant normalize calls. |
| **Reuse SequenceMatcher instances** | 8.6s (__chain_b) | **~4-7s** | For the fuzzy pass residuals, create one SequenceMatcher per LR item with `set_seq2` called once, then `set_seq1` per game code. Avoids 796K `__chain_b` rebuilds. |
| **Overall projected improvement** | 74.6s | **~60-70s savings -> ~5-10s runtime** | Combining all three: dict-based exact/suffix/contains eliminates most fuzzy calls; pre-computed norms eliminate redundant regex; reused SequenceMatchers handle residual fuzzy cheaply. |

---

## Dataset Scale Context

- Game codes processed: **2,046** (1,583 recipe outputs + 463 ingredient-only)
- LR items matched against: **475**
- SequenceMatcher comparisons: **796,100** (N x M fuzzy pass)
- Canonical items created: **2,440**
- Lang alias entries loaded: **5,132** (negligible cost)
- FTA items linked: **277** (trivial cost)

---

## Summary

**The script is 99.3% Python-bound.** The entire bottleneck is a single function
(`choose_best_lr_match`) running an O(N x M) fuzzy comparison loop with no
caching of normalized values or SequenceMatcher state. The fix is structural:
pre-index LR names for exact/prefix/contains lookups to eliminate the fuzzy
pass for the vast majority of game codes, pre-compute normalizations, and
reuse SequenceMatcher instances for any remaining fuzzy comparisons.

**No DB optimization is needed.** All queries are fast and well-structured.
