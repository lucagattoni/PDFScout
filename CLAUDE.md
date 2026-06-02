# PDFScout — Claude Code project rules

## Git workflow

- **Always create a new branch** for any new development or planning work. Never
  commit directly to `main` unless the user explicitly says so for a specific change.
- Branch name convention: short kebab-case description of the work
  (e.g. `feat/add-contract-schema`, `fix/burst-semaphore`, `plan/websocket-streaming`).
- Push the branch and let the user decide when to merge / open a PR.

## Plans

- Every new plan file goes in the `plans/` directory (create it if it doesn't exist).
- File name format: `YYYYMMDD_HHMM-<short-description>.md`
  (e.g. `plans/20260531_1430-add-websocket-support.md`).
- When **updating** a plan, write the update datetime on the line immediately
  after the creation date line, e.g.:
  ```
  _Created: 2026-05-31 14:30_
  _Updated: 2026-05-31 16:05 · <reason for update>_
  ```

## Reviews

- Always use the **devil's advocate** approach: actively try to find what can go
  wrong before accepting a design or implementation as sound.

## New coding project setup

When initialising any new coding project:

1. Pull the latest commits from `main` on `~/Code/repos/github_lucagattoni/andrej-karpathy-skills`
2. Copy the full content of its `CLAUDE.md` into the new project's `CLAUDE.md` (above the project-specific rules)
3. If the project's `CLAUDE.md` already had rules, check them against the newly added ones: remove or fix anything redundant or conflicting.
4. If the project is **pre-existing** (repo already has code), after steps 1–3 ask the user: "Would you like a full code review against the new guidelines?"

If the project is not clearly about code, or if it's unclear, ask the user first.
