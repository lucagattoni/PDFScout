# Installation

[Documentation index](../index.md) · [Project overview](https://github.com/lucagattoni/PDFScout)

## Requirements

- [uv](https://docs.astral.sh/uv/) — the Python package manager used by this project
- Python 3.13 (pinned in `.python-version`; uv installs it automatically if missing)
- An [Anthropic API key](https://console.anthropic.com/)

## Steps

```bash
git clone https://github.com/lucagattoni/PDFScout.git
cd PDFScout
uv sync --group dev   # installs production deps + ruff, pytest, and other dev tools
cp .env.example .env  # then fill in your API key
```

Edit `.env` and set your Anthropic API key:

```text
ANTHROPIC_API_KEY=sk-ant-...
```

`.env` is gitignored and never committed. `.env.example` documents every
supported variable.

## Optional: Langfuse tracing

PDFScout ships with optional [Langfuse](https://langfuse.com/) observability.
When enabled, every pipeline run produces a single trace showing node
execution, Claude API calls, token usage (including prompt-cache hits), and
extraction metadata. All runs for the same PDF are grouped in the Langfuse
Sessions view via a shared `session_id`.

Add to your `.env` (keys from your [Langfuse project settings](https://cloud.langfuse.com)):

```text
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_BASE_URL=https://cloud.langfuse.com
```

If the keys are absent the pipeline runs normally with no tracing.

## Verify the install

```bash
make test   # 241 offline tests — no API key required
```

Next: [usage](02-usage.md) to run your first extraction.
