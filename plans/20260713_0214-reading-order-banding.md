# Reading-order banding for columnar documents

_Created: 2026-07-13 02:14_

## Problem

`geometric_pre_sorter` (`src/nodes/hierarchy_node.py`) sorts blocks
`(page, xmin // COLUMN_BUCKET_PX, ymin)` — **column-major over the whole page**.
This is correct for two-column scientific papers (read the whole left column,
then the whole right column) but produces an unnatural order for invoices and
forms, where full-width bands (tables, headers, footers) alternate with
side-by-side field groups.

Evidence — the real `aruba rimborso 2025` invoice (18 blocks) under the current
sorter places:

- the top-right company header (`b2`) **12th**, after the invoice totals;
- the page footer (`b18`) **11th**, mid-document;
- Ship-to after TOTAL.

The flat `structured_payload` order is the **only** sibling-sequence signal in
the output (`parent_id` gives structure, not order), and it also feeds the
hierarchy LLM's "block directly following a heading" adjacency rule. So the
order matters for downstream consumers (text export, RAG chunking, remediation
agents) and for hierarchy quality.

## Chosen approach — Option F: band-then-column

Split each page into horizontal **bands** at every *full-width* block (width
>= `BAND_FULL_WIDTH_FRAC` of the page's x-span). Within a band, the full-width
block leads, then the remaining blocks are ordered column-major
(`xmin // COLUMN_BUCKET_PX` ASC, then `ymin` ASC). Pages are emitted in
ascending page order.

Why F over the alternatives:

- **Row-major (y-band then x)** fixes globals but interleaves side-by-side
  groups line-by-line and is catastrophic for two-column papers.
- **Doc-type-aware branching** inherits the interleaving flaw and adds a second
  code path gated on a fallible classifier.
- **LLM-assigned order** adds output-token cost, latency, and permutation
  validation for a problem that is deterministic geometry.
- **Full recursive XY-cut** is ~10× the code for 3 doc types — kept as the
  escalation path if F ever proves insufficient.

F is a **strict superset** of the current behavior: with no full-width blocks,
every block lands in band 0 and the result is identical column-major order. It
reduces to clean row-major for single-column docs (every block is full-width →
its own band → `ymin` order). It only changes behavior when full-width blocks
are interspersed — the invoice/form case.

Result on the aruba invoice: **17/18 ideal**; only `b2` (top-right header) comes
5th (after the complete Bill-to group) rather than 2nd — an acceptable
left-group-then-right-group reading order.

## Algorithm

```
for each page (ascending):
    span = max(xmax) - min(xmin) over the page's blocks
    full = { b : (xmax-xmin) >= BAND_FULL_WIDTH_FRAC * span }   # span>0
    cuts = sorted(ymin for b in full)
    band(b) = count of cuts <= b.ymin
    key(b)  = (band(b), 0 if b in full else 1,
               0 if b in full else b.xmin // COLUMN_BUCKET_PX,
               b.ymin, b.block_id)
    emit page blocks sorted by key
```

`BAND_FULL_WIDTH_FRAC = 0.6` — just above a single column of a two-column layout
(~0.48 of width) and well below a genuine full-width table (~1.0), giving clear
separation. Tunable in `src/config.py`.

## Success criteria

1. New unit tests for `geometric_pre_sorter` pass, including a regression
   fixture built from the 18 real aruba invoice bboxes asserting the banded
   order, and a two-column-with-full-width-title case.
2. Existing `TestGeometricPreSorter`, `grp_f`, and `grp_g` tests unchanged and
   green (traced by hand: none contain a mid-page full-width block, so F is
   order-identical for them).
3. `make test` (non-e2e) green; `make lint` clean.
4. **User-run e2e:** the aruba invoice end-to-end shows natural order;
   `pytest -m e2e -k "grp_g or grp_r"` still passes (papers order-preserved).

## Steps

1. Add `BAND_FULL_WIDTH_FRAC` to `src/config.py`. → verify: import works.
2. Rewrite `geometric_pre_sorter` per the algorithm. → verify: existing unit
   tests still pass.
3. Add unit tests (aruba regression fixture + full-width-band case). → verify:
   new tests pass.
4. `make test` + `make lint`. → verify: green/clean.
5. Sync docs: README config table, `schemas/README.md` sorter note, CHANGELOG,
   ROADMAP (same commit). → verify: grep for stale sorter description.
6. Push branch; request e2e runs (step 4 of success criteria).

## Risks

- **Width threshold false positives** — a wide column block mistaken for
  full-width would band incorrectly. Mitigated by 0.6 (well above two-column
  0.48). Tunable.
- **Full-width block overlapping column text** creates a mid-flow cut — but such
  a block visually does interrupt reading, and `is_continued` handles genuine
  cross-page/column text flow.
- Page width is estimated as `max(xmax) - min(xmin)` per page (blocks are all we
  have); a page with only narrow left-aligned blocks has a small span, but then
  there are no columns to disambiguate and band 0 column-major is correct.
