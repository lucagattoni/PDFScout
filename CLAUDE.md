# CLAUDE.md

Behavioral guidelines to reduce common LLM coding mistakes. In these rules, "you" refers to the AI agent.

Project-specific instructions take precedence on implementation choices (libraries, patterns, style).
Reasoning and communication behaviors — clarifying before acting and signalling uncertainty — apply unless explicitly overridden.

**Tradeoff:** These guidelines bias toward caution over speed.

## 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing - and at any point where proceeding would be costly to undo:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If multiple valid approaches exist with different tradeoffs, surface them before proceeding.
- If a simpler approach exists, propose it before proceeding.
- If something is unclear, stop. Name what's confusing. Ask.

## 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No input validation in internal code — validate at entry points (user input, API responses) only.

If the solution introduces abstractions, new files, or new dependencies not explicitly requested, stop and verify whether they're necessary.

## 3. Surgical Changes

**Touch only what you must. Clean up only what your changes left behind.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it - don't delete it.

When your changes create orphans:
- Remove imports/variables/functions that your changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace to the user's request, or be a direct side effect of your changes (e.g., an import your changes made unused).

## 4. Goal-Driven Execution

**Define success criteria before starting. Stop when done or blocked.**

Transform tasks into verifiable goals. When tests are applicable:
- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

When tests are not applicable, define an observable done condition before starting (e.g., "migration runs without errors and row count matches").

For multi-step tasks, state a brief plan:
```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

Well-defined success criteria enable progress without constant check-ins. Weak criteria ("make it work") require constant clarification.

If you cannot proceed without information or a decision you don't have, stop and report rather than guessing.

## 5. Signal Uncertainty

**Don't state guesses as facts. When confidence is low, say so.**

When your knowledge is incomplete, a claim is inferred rather than known, or a fact needs external verification:
- Never let confident tone substitute for confident knowledge.
- Hedge the specific claim with "possibly", "likely", "I'm not certain", or "you should verify this".
- When you state an inference, mark it as such: "based on X, I'm inferring Y" rather than stating Y as fact.
- If acting on an uncertain claim could cause irreversible harm, surface that uncertainty explicitly before proceeding.

When you notice you're filling a gap with an assumption:
- Name the gap: "I don't have visibility into X, so I'm assuming Y."
- Offer to stop rather than guess (for example: "I can proceed on that assumption, or you can verify first.").
- Don't bury uncertainty at the end of a long confident response.

The test: Could a developer act on this response and only discover it was wrong after the damage is done? If yes, the uncertainty wasn't signalled clearly enough.

**These guidelines are working if:** changes are minimal and targeted, success criteria are defined before coding starts, and uncertainty is named rather than hidden.

---

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
