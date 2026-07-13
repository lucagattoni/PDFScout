# Development

[Documentation index](../index.md) · [Project overview](https://github.com/lucagattoni/PDFScout)

## Commands

| Command | Description |
|---|---|
| `make install` | Install all dependencies (production + dev, including Node) |
| `make lint` | Check Python for linting violations and formatting drift (read-only) |
| `make lint-md` | Check Markdown files with markdownlint-cli2 (read-only) |
| `make fix` | Auto-fix Python violations and reformat all files |
| `make test` | Run the full offline test suite (no API key required) |
| `make test-e2e` | Run all synthetic e2e tests (requires `ANTHROPIC_API_KEY`) |
| `make test-e2e GRP=c` | Run one group of e2e tests (a–i) |
| `make fixtures` | Regenerate all synthetic PDF fixtures and golden files |
| `make fixtures GRP=c` | Regenerate one group of fixtures |
| `make coverage` | Run tests and print per-module coverage report |
| `make docs` | Serve this documentation locally with MkDocs Material |
| `make ci` | Run `lint`, `lint-md`, then `test` — use before pushing |
| `make clean` | Remove `__pycache__`, `.coverage`, `htmlcov`, `.pytest_cache`, `node_modules` |

Python linting and formatting use [ruff](https://github.com/astral-sh/ruff)
(configured in `pyproject.toml` under `[tool.ruff]`). Markdown linting uses
[markdownlint-cli2](https://github.com/DavidAnson/markdownlint-cli2)
(configured in `.markdownlint.json`).

## Extending with new document types

1. Add a new JSON Schema file to `schemas/<type>.json` following the Draft-07
   structure with the 8-type block enum and any domain-specific `metadata`
   extensions. The filename without `.json` is the exact token the classifier
   will return.
2. Add the new type string to `SUPPORTED_DOC_TYPES` in `src/config.py` — the
   classifier prompt updates automatically via `sorted(SUPPORTED_DOC_TYPES)`.
3. *(Optional but recommended)* Add a branch in `_doc_type_instructions()` in
   `src/nodes/worker_node.py` with domain-specific extraction instructions.
   These are appended to the prompt for every page, guiding the model to
   populate domain metadata subfields on the relevant block types.

The classifier, schema registry, and validation loop pick the new type up
after steps 1–2. Step 3 improves metadata extraction quality but is not
required for the pipeline to function.

Full schema authoring guide: [schemas/README.md](https://github.com/lucagattoni/PDFScout/blob/main/schemas/README.md).

## Documentation

The documentation is a hierarchical MkDocs Material site (this site). Content
lives in `docs/` as plain Markdown, organized general → specific: the root
`README.md` is the simple overview, section folders go progressively deeper.

```bash
make docs           # live-preview at http://127.0.0.1:8000
```

When a code change touches any user-facing surface (a flag, constant, command,
default, or behavior), update the docs **in the same change** — including test
counts and config values quoted anywhere in `docs/`.

## Testing

See [testing](02-testing.md) for the test architecture, e2e groups, and the
real-document corpus.
