# Reading-order banding v2 — general, scale-invariant ordering

_Created: 2026-07-13 03:54_

Fixes ROADMAP Open #1 (three reading-order defects found on real documents on
2026-07-13). Method and constraints follow CLAUDE.md → Investigation rules:
offline replay on saved block sets, principle-derived thresholds, edge-case
tests, anti-overfit gate over the whole fixture corpus.

## Defects (mechanisms, not documents)

| # | Mechanism | Observed as |
|---|---|---|
| 1 | Full-width block *led* its band, and band boundaries stranded same-y narrow blocks | Label-left/wide-text-right pairs inverted on every row; heading divorced from its own table by sidebar content |
| 2 | Absolute-pixel knobs (`COLUMN_BUCKET_PX=50`, gap in px) are model-scale-dependent — the same A4 page was emitted with x-span 855 and 1125 units in consecutive runs | Same-column blocks with ~45px xmin jitter split into two "columns" (page title sorted 10th) |
| 3 | `BAND_FULL_WIDTH_FRAC=0.6` missed a real 0.59 separator | Whole-page column-major fallback: top-right key field sorted after bottom-left content |

## Algorithm changes (`geometric_pre_sorter`)

1. **Within a band, all blocks (full-width included) sort column-major** —
   `(band, xmin // bucket_w, ymin, block_id)`. A label left of a full-width
   block reads before it.
2. **Heading/title pull-down**: a heading that starts above a full-width block,
   whose bottom edge is within `pulldown_gap` of the cut (either side —
   tolerates bbox jitter), and that x-overlaps it, joins the band of the
   **nearest** such block (never a later one). Other block types are never
   pulled — that guard came from a false positive on the aruba regression
   fixture (plain paragraphs yanked out of their column).
3. **All knobs are fractions of the page x-span** (scale-invariant):

| Knob | Value | Principle |
|---|---|---|
| `BAND_FULL_WIDTH_FRAC` | 0.55 | A horizontal separator spans clearly more than half the page; multi-column layouts keep columns ≤ ~0.5 of span |
| `COLUMN_BUCKET_FRAC` | 0.11 | Column gutters exceed ~1/9 of page width; same-column xmin jitter stays below it |
| `BAND_PULLDOWN_GAP_FRAC` | 0.035 | A heading sits within about one line-height of the content it introduces |

## Offline validation (zero API cost)

Replay of the sorter on saved block sets from two real documents (2-page Irish
utility bill, 3-page Italian utility invoice), scored against 12 hand-derived
human-reading-order constraints plus 2 adjacency gap metrics:

| Configuration | Constraints passed |
|---|---|
| v1.7.0 sorter (baseline) | 5 / 12 |
| + within-band column-major + pull-down | 9 / 12 |
| + frac=0.55, bucket=0.11·span (sweep table below) | **11 / 12** |

Parameter sweep (frac × bucket × gap, absolute-px stage of the iteration):

| frac | bucket | passed |
|---|---|---|
| 0.5 | 50 | 10 |
| 0.5 | 100 | 11 |
| 0.55 | 50 | 10 |
| 0.55 | 100 | **11** |
| 0.6 | 50 | 9 |
| 0.6 | 100 | 10 |

Heading↔table adjacency gap: Enel p1 14 blocks → adjacent; Irish bill p2
5 blocks → 1 block.

**Known limitation (accepted):** on a page with *no* full-width block at all,
ordering degrades to whole-page column-major, so a top-right field can sort
after deep-left-column content (Irish bill p1: "account number" vs the
bottom-left barcode). Fixing this would need y-clustering without full-width
anchors; lowering `BAND_FULL_WIDTH_FRAC` toward ~0.42 instead would shred
two-column papers (columns ≈ 0.45 of span). Revisit only with evidence from
more documents.

## Tests

- 12 unit tests on `geometric_pre_sorter` (7 new): label-inversion,
  pull-down, paragraph-not-pulled (negative), jittered-overlap pull, stacked
  tables → nearest, no-x-overlap (negative), scale-invariance (same layout at
  two coordinate scales), empty input, zero span, determinism on ties.
- 2 new synthetic PDF fixtures + e2e tests (`grp_g_label_sidebar`,
  `grp_g_heading_table_sidebar`) distilled from the real failure patterns.
- Anti-overfit gate: full non-e2e suite (180) incl. the aruba 18-block
  regression fixture, unchanged G1/G2 column fixtures.

## Follow-ups

- Run `pytest -m e2e -k "grp_g or grp_r"` (paid) to validate ordering across
  the full golden corpus — the strongest generalisation check.
