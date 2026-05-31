@https://raw.githubusercontent.com/lucagattoni/andrej-karpathy-skills/main/CLAUDE.md

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
