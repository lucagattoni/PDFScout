# Testing

[Documentation index](../index.md) · [Project overview](https://github.com/lucagattoni/PDFScout)

Three tiers, by cost: an offline suite that runs on every change, synthetic
e2e tests that hit the real API against generated PDFs, and a real-document
corpus that runs the full pipeline against production-like documents.

## Offline suite (241 tests)

Run with `make test`; coverage report with `make coverage`. No
`ANTHROPIC_API_KEY` required — the suite runs entirely in isolation with
mocked Anthropic clients.

| Layer | Location | What it covers |
|---|---|---|
| Unit | `tests/unit/` | State reducers, schema registry, routing edges, PDF utilities, page counter, tracing, usage accounting, Pydantic models, graph topology, golden-generator consensus logic, and every node function (extractor, classifier, worker, retry, coverage auditor, hierarchy) — all external I/O mocked |
| Integration | `tests/integration/` | All FastAPI endpoints (health, extract, jobs) via an ASGI test client; `run_extraction` background task; end-to-end LangGraph pipeline (happy path, pioneer retry-then-success, max-retry degradation) |

## Synthetic e2e tests

A separate tier exercises the real pipeline against synthetic PDF fixtures.
These require a real `ANTHROPIC_API_KEY` and are excluded from `make test`
(they carry `@pytest.mark.e2e`).

| Group | Concern | API calls |
|---|---|---|
| A | Native extraction (pypdf only) | 0 |
| B | Classifier accuracy | 1 per test |
| C | Block-type extraction | 1–2 per test |
| D | Schema-specific metadata | 1–2 per test |
| E | Multi-page burst + merge (hierarchy mocked) | N (one per page) |
| F | Hierarchy assignment (narrow, direct function call) | 1 per test |
| G | Two- and three-column reading order | 1–2 |
| H | Graceful degradation (blank page, tiny text) | 1 |
| I | Full-chain integration (no LLM tier mocked except classifier) | N + 1 |

```bash
make test-e2e          # all groups
make test-e2e GRP=c    # one group
make fixtures          # regenerate fixtures after a generator or prompt change
make fixtures GRP=b
```

PDF fixtures are not committed — they are generated at session start by a
hash-check that compares each generator script's SHA-256 against
`tests/fixtures/manifest.json`. Golden files (expected outputs, design-intent)
are committed to `tests/fixtures/golden/`.

Synthetic fixtures are also how real-world failures become regression tests:
every failure pattern found in a real document is distilled into a generator
under `tests/fixtures/generators/`, so the pattern is guarded forever without
committing the (often private) document that exposed it.

## Real-document corpus tests (Group R)

A third tier runs the full pipeline against real PDFs sourced from public
repositories and government/institutional open-access publications. Unlike
groups A–I (synthetic), Group R tests the pipeline against documents it will
encounter in production.

```bash
# Download PDFs (first time, or when URLs change)
python scripts/download_real_fixtures.py

# Run Group R tests (requires ANTHROPIC_API_KEY)
pytest tests/integration/test_real_docs.py -m grp_r
```

Real PDFs are never committed — they land in `tests/fixtures/pdfs/real/`
(gitignored) and are fetched on demand. Golden assertion files are committed
to `tests/fixtures/real_golden/`. The corpus manifest
(`tests/fixtures/real_manifest.json`) records URLs, checksums, licenses, and
memorisation risk for all 15 slots.

Corpus rules (page limits, recency requirements for scientific papers, golden
generation protocol): see the
[real-document workflow](03-real-doc-workflow.md).

## Coverage targets

| Module | Coverage |
|---|---|
| `src/state.py`, `src/edges.py`, `src/schema_registry.py` | 100% |
| `src/utils/`, `src/extractors/`, `src/api/jobs.py`, `src/api/models.py` | 100% |
| `src/graph.py`, `src/nodes/*.py` | 100% |
| `src/api/runner.py` | ≥ 90% |
| `api.py` | ≥ 75% (lifespan I/O not exercised) |
