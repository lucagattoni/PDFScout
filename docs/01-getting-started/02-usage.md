# Usage

[Documentation index](../index.md) · [Project overview](https://github.com/lucagattoni/PDFScout)

## Extract a PDF (CLI)

```bash
uv run main.py path/to/document.pdf
```

The output is printed as formatted JSON to stdout. Progress is logged per node:

```text
Initializing extraction pipeline for: document.pdf (thread: a3f1c9d2...)
[GRAPH] Node 'native_extractor' completed.
[GRAPH] Node 'classifier' completed.
[GRAPH] Node 'pioneer_parser' completed.
[GRAPH] Node 'burst_dispatcher' completed.
[GRAPH] Node 'parser_worker' completed.
[GRAPH] Node 'coverage_auditor' completed.
[GRAPH] Node 'hierarchy_node' completed.

Extraction complete. Output tree:
{ ... }
```

What the output looks like and how to consume it: [output format](../02-concepts/02-output-format.md).

## Warnings

If any page degraded (schema validation exhausted its retries, or the
completeness audit found dropped content it couldn't repair), warnings are
printed before the tree and included in the output's `extraction_warnings`:

```text
WARNINGS:
  ! Pioneer page (page 1) failed schema validation after 3 retries. Page 1 data may be incomplete or structurally invalid.
```

An empty warnings list means every page validated and passed the coverage
audit.

## Token usage

Every run prints an aggregate usage line to stderr at the end:

```text
USAGE: 9 API calls | input 1200 | output 14500 | cache_read 98000 | cache_write 12400
```

Two environment variables control the detail level and cache behavior — see
[configuration](../03-reference/01-configuration.md#environment-variables):

- `PDFSCOUT_LOG_USAGE=1` — print a per-API-call `[USAGE]` line to stderr
- `PDFSCOUT_CACHE_TTL=1h` — hold the prompt cache for 1 hour instead of 5
  minutes (worth it when running the same document several times)

## Checkpoint Resumption

State is saved to SQLite (`state_checkpoint.db`, created automatically) after
every pipeline step. The thread ID is the PDF's SHA-256 hash, so re-running
the same file resumes from the last valid checkpoint instead of paying for the
whole document again:

```bash
# First run — interrupted mid-way
uv run main.py large_document.pdf

# Second run — resumes automatically from last checkpoint
uv run main.py large_document.pdf
```

## API Server

```bash
uv run uvicorn api:app --host 0.0.0.0 --port 8000
```

See the [API reference](../03-reference/02-api.md) for the full endpoint list, job
lifecycle, and operational notes.
