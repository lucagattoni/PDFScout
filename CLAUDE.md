# CLAUDE.md — PDFScout project rules

"You" = the AI agent. Project rules take precedence on implementation choices
(libraries, patterns, style); the reasoning/communication behaviors below apply
unless explicitly overridden. Tradeoff: these rules bias toward caution over speed.

## Core behavior

- **Think before coding.** State assumptions explicitly. If multiple
  interpretations or approaches with different tradeoffs exist, present them —
  don't pick silently. Propose the simpler approach when one exists. If blocked
  on missing information or a decision, stop and report rather than guess.
- **Simplicity first.** Minimum code that solves the problem: no unrequested
  features, no abstractions for single-use code, no speculative configurability,
  no new dependencies without verifying they're necessary. Validate at entry
  points only (user input, API responses), never in internal code.
- **Surgical changes.** Touch only what the request requires; match existing
  style; don't improve/refactor adjacent code. Remove only orphans your change
  created; mention (don't delete) pre-existing dead code. Test: every changed
  line traces to the request or is a direct side effect of it.
- **Goal-driven execution.** Define verifiable success criteria before starting
  ("fix the bug" → "write a test that reproduces it, then make it pass"); for
  multi-step work state a brief step→verify plan. Stop when done or blocked.
- **Signal uncertainty.** Never let confident tone substitute for confident
  knowledge: hedge inferred claims ("based on X, I'm inferring Y"), name
  assumption gaps ("no visibility into X, so assuming Y"), and surface
  uncertainty *before* acting when being wrong would be costly — never buried at
  the end. Test: could the user act on the response and discover the error only
  after the damage is done?

## Git workflow

- **New branch for every piece of work** — features, fixes, refactors, plans.
  **Never commit directly to `main`** unless the user explicitly authorizes it
  for that change. Standing exception: `ROADMAP.md`-only updates merge to main
  immediately after being written (user directive, 2026-07-13).
- Branch names: short kebab-case with a type prefix, readable without context —
  `feat/<what-it-adds>`, `fix/<what-it-fixes>`, `test/<what-it-covers>`,
  `plan/<topic>`, `chore/<what>`. This project scheme overrides the global
  timestamped-branch naming convention.
- Push the branch and let the user decide when to merge / open a PR (except the
  standing exception above).

## Plans

- Every plan file goes in `plans/`, named `YYYYMMDD_HHMM-<short-description>.md`.
- On update, add the update datetime directly under the creation line; end each
  such line with a trailing `\` so Markdown keeps them on separate lines:
  `_Created: 2026-05-31 14:30_\` / `_Updated: 2026-05-31 16:05 · <reason>_`.
- **Plan and implementation live on the same branch** (`feat/<topic>`): write the
  plan there, refine, then implement. If a separate plan branch already exists,
  merge it into the implementation branch before pushing.

## Roadmap

`ROADMAP.md` is the single source of truth for open items, deferred decisions,
and rejected proposals.

- **Same-commit rule.** Work that opens, closes, or changes an item's state
  updates `ROADMAP.md` in the same commit — never as a follow-up.
- **Record, don't discard.** New gaps, deferred work, and recommendations go in
  the correct section (Open Now / Deferred / Rejected), not into chat or a
  commit message.
- **Commit + merge to main immediately** after any roadmap update.

## Commit & push cadence

- **Push every commit immediately when it is ready** — never accumulate commits
  for a batch push, in any context (iterative loops, multi-step work, one-off fixes).

## Releases

- **Version bump ⇒ `uv lock` in the same commit** (a stale lock self-version
  dirties every later `uv run` and causes rebase conflicts).
- **Release commit on main ⇒ push the annotated tag immediately** (`git tag -a
  v<X.Y.Z> && git push origin v<X.Y.Z>`); `release.yml` then auto-publishes the
  GitHub release with the CHANGELOG section as notes — verify its run succeeded.
  Two traps: pushing **>3 tags in one push suppresses the trigger** (push tags
  one at a time, or `gh release create` manually as fallback), and tags silently
  froze at v1.7.1 while CHANGELOG reached v1.11.0 — nine releases backfilled
  (2026-07-13).

## Test corpus (real-document fixtures)

- Every PDF in `tests/fixtures/real_manifest.json` is **max 5 pages** — verify
  the downloaded PDF's actual page count with pypdf (arXiv "comments" page
  counts lie: main text only).
- Scientific-paper slots must be **≤3 months old at selection**, post-dating the
  extraction model's knowledge cutoff (arXiv listings sorted by submittedDate
  are the proven source). Recency applies **only** to scientific-paper slots;
  invoice and business/civic slots may be older.
- **Never use classic/famous novels, stories, or well-known texts** anywhere in
  the corpus — memorisation corrupts extraction measurements.
- Record license and memorisation risk per slot in the manifest.
- Real user documents are **private and local-only — never committable**; the
  committable corpus is public documents plus synthetic fixtures.

## Investigation rules

Apply whenever existing logic stops working as expected (mis-ordering,
extraction gaps, validation failures) — layout/ordering issues affect every
document, so fixes here are never document-specific.

1. **Reproduce on the cheapest surface first.** Replay saved block sets or
   fixtures offline (no API calls) to reproduce and iterate; constraint-based
   scoring and parameter sweeps offline. Paid live run only to confirm a
   finished fix.
2. **Root-cause to a mechanism, never to a document.** Name the general failure
   mode ("band boundary strands same-y narrow blocks"), not the symptom
   location ("Enel p3 is wrong"). No mechanism named → keep investigating.
3. **Solutions must be general — no overfitting.** Derive every threshold from
   a typographic/geometric principle and state it in a comment. Geometry is
   scale-invariant: fractions of the page span, never absolute pixels (the
   model emits x-spans of 855–1125 units for the same A4 page). A constant
   justified only by "it fixes this document" is wrong.
4. **Tests must be general too — enumerate edge cases.** Per heuristic cover:
   degenerate geometry (empty input, single block, zero span), coordinate
   jitter, stacked/adjacent features, scale extremes, and at least one negative
   case where the heuristic must NOT trigger.
5. **Anti-overfit gate.** A change to shared logic must pass the entire fixture
   corpus (all unit tests + golden replays), not just the motivating case.
6. **Distill real failures into synthetic fixtures.** Encode each failure
   pattern as a generator under `tests/fixtures/generators/` (plus golden) in
   the same change as the fix. Block-level unit tests are the fast first line;
   the generated PDF fixture guards the full pipeline.
7. **Cost cap on paid testing.** No expensive workloads (large documents,
   high-run-count golden regenerations, full e2e sweeps) without explicit user
   sign-off. Minimum viable spend: smallest reproducing document, minimum run
   count, offline replays first, one paid confirmation run — not one per
   iteration.
8. **Ask when the principle is ambiguous.** If no general rule can be derived
   (two defensible policies, no principle to appeal to), ask the user with the
   concrete trade-off instead of picking silently.

## Reviews

- **Devil's advocate always**: actively try to find what can go wrong before
  accepting a design or implementation as sound.
- After every implementation, before committing:
  1. **Full non-e2e suite passes** — `make test` (= `uv run pytest -m "not e2e"`).
  2. **Lint clean** — `make lint` (= `uv run ruff check`).
  3. **Docs consistent** — proactively sync every doc referencing the changed
     system: README.md, schemas/README.md, CHANGELOG.md, ROADMAP.md, and plan
     files (test counts, config constants, feature lists, scope tables,
     acceptance criteria).
