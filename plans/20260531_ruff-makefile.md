# Ruff + Makefile Integration Plan

**Date:** 2026-05-31  
**Branch:** `claude/ruff-makefile-plan-1780207234`

---

## 1. Goals

- Add `ruff` as the single tool for linting *and* formatting across all Python files.
- Eliminate the 2 existing `F401` unused-import violations and reformat all 26 files that diverge from ruff's style.
- Expose a `Makefile` with `make lint` and `make test` as the canonical developer entry points — short commands that delegate to `uv run`, so they work regardless of how the developer's shell is set up.

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
.PHONY: lint test

lint:
	uv run ruff check .
	uv run ruff format --check .

test:
	uv run pytest
```

**Design decisions:**

- **`uv run` prefix** — all commands go through `uv run` so they use the project's locked virtual environment rather than whatever Python/ruff is on the developer's `PATH`. This is consistent with how the project already runs everything (see README).
- **`lint` runs both `ruff check` and `ruff format --check`** — linting and formatting are conceptually separate (`check` catches logic/style violations, `format --check` checks whitespace/layout) and ruff keeps them as distinct subcommands. Running both under a single `make lint` target matches the common developer expectation: "lint should tell me if the code is clean."
- **No `make lint-fix` or `make format` target** — applying fixes is a deliberate act. Keeping the Makefile read-only (`--check` mode) avoids silent file mutations during CI. Developers run `uv run ruff check --fix .` and `uv run ruff format .` manually when they want to apply fixes.
- **No `addopts` change to pytest config** — coverage is intentionally not baked into `make test`. Running coverage on every test invocation adds ~0.3 s of overhead and pollutes the terminal during rapid iteration. Use `uv run pytest --cov=. --cov-report=term-missing` explicitly when needed.
- **`PHONY` declaration** — prevents `make` from confusing the target names with files or directories named `lint` or `test`.

---

## 4. Implementation Order

1. Add `ruff>=0.9` to `[dependency-groups] dev` in `pyproject.toml`.
2. Add `[tool.ruff]`, `[tool.ruff.lint]`, and `[tool.ruff.format]` tables to `pyproject.toml`.
3. Run `uv sync --group dev` to lock the new dependency.
4. Run `uv run ruff check --fix .` to auto-fix the 2 `F401` violations.
5. Run `uv run ruff format .` to reformat the 26 divergent files.
6. Run `uv run ruff check .` and `uv run ruff format --check .` — both must exit 0 before continuing.
7. Run `uv run pytest` — must stay green (113 tests passing).
8. Create `Makefile`.
9. Verify `make lint` and `make test` both exit 0.
10. Commit and push.

---

## 5. Files Changed

| File | Change |
|---|---|
| `pyproject.toml` | Add `ruff>=0.9` to dev deps; add `[tool.ruff]`, `[tool.ruff.lint]`, `[tool.ruff.format]` sections |
| `Makefile` | New file |
| `src/schema_registry.py` | Remove unused `import os` (auto-fixed) |
| `tests/integration/test_api_runner.py` | Remove unused `import pytest` (auto-fixed) |
| 26 Python source files | Reformatted by `ruff format` (whitespace/quote normalisation only) |
