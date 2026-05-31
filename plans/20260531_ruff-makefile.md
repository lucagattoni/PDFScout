# Ruff + Makefile Integration Plan

**Date:** 2026-05-31  
**Branch:** `claude/ruff-makefile-plan-1780207234`

---

## 1. Goals

- Add `ruff` as the single tool for linting *and* formatting across all Python files.
- Eliminate the 2 existing `F401` unused-import violations and reformat all 26 files that diverge from ruff's style.
- Expose a `Makefile` with `make lint`, `make test`, `make fix`, `make coverage`, and `make ci` as the canonical developer entry points — short commands that delegate to `uv run`, so they work regardless of how the developer's shell is set up.
- Update `README.md` to document the new developer workflow.

---

## 2. Changes

### 2.1 Add `ruff` to `pyproject.toml`

Ruff already ships as a system binary in this environment (`ruff 0.15.8`), but it must be declared as a dev dependency so it is available consistently in any environment after `uv sync --group dev`.

```toml
[dependency-groups]
dev = [
    ...
    "ruff>=0.9",
]
```

`>=0.9` is the minimum version that supports the `[tool.ruff.lint]` / `[tool.ruff.format]` table split introduced in ruff 0.1.0 and the `select`/`ignore` keys used below. The project is already on 0.15.8, so this constraint is satisfied immediately.

### 2.2 Add `[tool.ruff]` configuration to `pyproject.toml`

```toml
[tool.ruff]
line-length = 100
target-version = "py313"

[tool.ruff.lint]
select = [
    "E",    # pycodestyle errors
    "F",    # pyflakes (undefined names, unused imports)
    "I",    # isort (import order)
    "W",    # pycodestyle warnings
    "UP",   # pyupgrade (modernise syntax for Python 3.13)
]
ignore = [
    "E501",  # line too long — formatter handles length; avoid double-reporting
]

[tool.ruff.lint.per-file-ignores]
"tests/**" = ["F811"]  # pytest fixtures cause apparent redefinitions that aren't real

[tool.ruff.format]
quote-style = "double"
indent-style = "space"
```

**Rule rationale:**

| Ruleset | Reason to include |
|---|---|
| `E` / `W` | Standard PEP 8 style errors and warnings |
| `F` | Core pyflakes: catches undefined names, unused imports/variables — the most actionable class of bugs |
| `I` | Keeps import blocks sorted and grouped consistently (replaces a separate `isort` invocation) |
| `UP` | Flags syntax that can be modernised for Python 3.13 (e.g., `Optional[X]` → `X \| None`, `Dict` → `dict`) — safe auto-fixes only |

`E501` (line-too-long) is suppressed because ruff's formatter already enforces `line-length`; having both the linter *and* formatter report the same violation creates confusing double errors.

`F811` is suppressed in `tests/**` because pytest fixtures are imported in `conftest.py` and then used as function parameters — ruff's static analyser treats each fixture use as a redefinition even though it is valid pytest idiom.

### 2.3 Fix pre-existing violations

Running `ruff check --fix .` will auto-fix the 2 existing `F401` violations before any new CI gate applies:

| File | Violation | Fix |
|---|---|---|
| `src/schema_registry.py:2` | `F401` — `os` imported but unused | Remove `import os` |
| `tests/integration/test_api_runner.py:4` | `F401` — `pytest` imported but unused | Remove `import pytest` |

### 2.4 Apply formatter to all files

Running `ruff format .` will reformat the 26 files flagged by `ruff format --check .`. These are pure whitespace/quote normalisation changes — no semantic effect. The formatter is idempotent: running it twice produces identical output.

---

## 3. Makefile

```makefile
.PHONY: install lint fix test coverage ci clean

install:
	uv sync --group dev

lint:
	uv run ruff check .
	uv run ruff format --check .

fix:
	uv run ruff check --fix .
	uv run ruff format .

test:
	uv run pytest

coverage:
	uv run pytest --cov=. --cov-report=term-missing

ci: lint test

clean:
	find . -type d -name __pycache__ -exec rm -rf {} +
	rm -rf .coverage htmlcov .pytest_cache
```

**Target reference:**

| Target | What it does | Mutates files? |
|---|---|---|
| `make install` | Install all dev dependencies via uv | No |
| `make lint` | Check for violations and formatting drift | No |
| `make fix` | Auto-fix violations and reformat all files | Yes |
| `make test` | Run the full test suite | No |
| `make coverage` | Run tests and print per-module coverage | No |
| `make ci` | `lint` then `test` — full pre-push / CI check | No |
| `make clean` | Remove `__pycache__`, `.coverage`, `htmlcov`, `.pytest_cache` | Yes |

**Target order rationale:** `install` first (onboarding), then the read/write lint pair (`lint` → `fix`), then the test pair (`test` → `coverage`), then the composite (`ci`), then cleanup last (`clean`). Each group flows naturally into the next: install → check → fix → test → verify coverage → clean up.

**Design decisions:**

- **`uv run` prefix** — all commands go through `uv run` so they use the project's locked virtual environment rather than whatever Python/ruff is on the developer's `PATH`. This is consistent with how the project already runs everything (see README).
- **`lint` runs both `ruff check` and `ruff format --check`** — linting and formatting are conceptually separate (`check` catches logic/style violations, `format --check` checks whitespace/layout) and ruff keeps them as distinct subcommands. Running both under a single `make lint` target matches the common developer expectation: "lint should tell me if the code is clean."
- **`fix` is the explicit write counterpart to `lint`** — separating read-only (`lint`) from write (`fix`) prevents silent file mutations during CI while still giving developers a single command to apply all fixes locally.
- **`coverage` is separate from `test`** — running coverage on every test invocation adds measurable overhead (~0.3 s) and clutters the terminal during rapid iteration. A dedicated target makes it an intentional, on-demand action.
- **`ci` composes `lint` and `test`** — rather than duplicating the commands, it depends on the two existing targets. This means any future change to `lint` or `test` is automatically reflected in `ci`.
- **`clean` uses `find … -exec rm -rf`** — safer than `find … | xargs rm` under filenames with spaces; the `+` form batches deletions into a single `rm` call per directory.
- **`PHONY` declaration** — prevents `make` from confusing the target names with files or directories of the same name.

---

## 4. README Updates

Two sections of `README.md` need updating.

### 4.1 Installation section

Add an `install` step that runs `uv sync --group dev` so new contributors get the full dev toolchain (including ruff) in one command. The current README only shows `uv sync` (production deps only).

```markdown
uv sync --group dev    # includes ruff, pytest, and other dev tools
```

### 4.2 New "Development" section

Add a **Development** section after **Installation** (and before **Observability**) documenting the Makefile targets:

```markdown
## Development

Install dev dependencies (ruff, pytest, and supporting libraries):

\```bash
uv sync --group dev
\```

| Command | Description |
|---|---|
| `make lint` | Check for linting violations and formatting drift (read-only) |
| `make fix` | Auto-fix violations and reformat all files |
| `make test` | Run the full test suite (113 tests, no API key required) |
| `make coverage` | Run tests and print per-module coverage report |
| `make ci` | Run `lint` then `test` — use before pushing |
```

The **Testing** section already documents `uv sync --group dev` and the `pytest` invocations. After this change that section can be condensed to a forward reference: "see the **Development** section for the `make test` and `make coverage` commands."

---

## 5. Implementation Order

1. Add `ruff>=0.9` to `[dependency-groups] dev` in `pyproject.toml`.
2. Add `[tool.ruff]`, `[tool.ruff.lint]`, and `[tool.ruff.format]` tables to `pyproject.toml`.
3. Run `uv sync --group dev` to lock the new dependency.
4. Run `uv run ruff check --fix .` to auto-fix the 2 `F401` violations.
5. Run `uv run ruff format .` to reformat the 26 divergent files.
6. Run `uv run ruff check .` and `uv run ruff format --check .` — both must exit 0 before continuing.
7. Run `uv run pytest` — must stay green (113 tests passing).
8. Create `Makefile`.
9. Verify all seven targets (`make install`, `make lint`, `make fix`, `make test`, `make coverage`, `make ci`, `make clean`) behave correctly.
10. Update `README.md` — add `uv sync --group dev` to the Installation section; add the Development section with the Makefile target reference table; condense the Testing section to forward-reference the new Development section.
11. Commit and push.

---

## 5. Files Changed

| File | Change |
|---|---|
| `pyproject.toml` | Add `ruff>=0.9` to dev deps; add `[tool.ruff]`, `[tool.ruff.lint]`, `[tool.ruff.format]` sections |
| `Makefile` | New file — `install`, `lint`, `fix`, `test`, `coverage`, `ci`, `clean` targets |
| `README.md` | Add `uv sync --group dev` to Installation; add Development section with Makefile reference table; condense Testing section |
| `src/schema_registry.py` | Remove unused `import os` (auto-fixed by ruff) |
| `tests/integration/test_api_runner.py` | Remove unused `import pytest` (auto-fixed by ruff) |
| 26 Python source files | Reformatted by `ruff format` (whitespace/quote normalisation only) |
