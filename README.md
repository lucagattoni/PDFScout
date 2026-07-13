# PDFScout

An agnostic, multi-agent PDF structure extractor that converts any PDF
document into a validated, hierarchical JSON tree. Built on LangGraph with
Claude's native PDF vision API, prompt caching for cost efficiency, a
self-healing validation loop, and a completeness audit against the PDF's own
text layer. Works on text-based and scanned documents alike.

**[Read the documentation →](https://lucagattoni.github.io/PDFScout/)** · [Changelog](CHANGELOG.md) · [Roadmap](ROADMAP.md)

## Why

Traditional PDF parsers break on structurally complex documents —
multi-column papers, corporate brochures, dense financial sheets — because
they hardcode layout assumptions. PDFScout shifts the parsing burden to a
language model, then enforces correctness with deterministic checks: schema
validation with retries on every page, and a word-level completeness audit
against the text embedded in the PDF itself.

## What it does

Given a PDF, PDFScout:

1. Counts pages and rejects encrypted files (locally, before any API cost)
2. Classifies the document type (invoice, scientific paper, contract, or a
   generic fallback)
3. Extracts structured content from every page **in parallel**, with the PDF
   cached provider-side so pages 2–N read it at ~10% of the input cost
4. Validates each page against a JSON Schema and retries on failure (up to 3×)
5. Audits completeness against the PDF's native text layer and automatically
   re-extracts pages with dropped or duplicated content
6. Assigns parent-child relationships with a geometry-informed hierarchy agent
7. Outputs one validated, hierarchical JSON document tree

Interrupted runs resume from the last checkpoint — state persists to SQLite
after every step.

## Quick start

Requires [uv](https://docs.astral.sh/uv/) and an
[Anthropic API key](https://console.anthropic.com/).

```bash
git clone https://github.com/lucagattoni/PDFScout.git
cd PDFScout
uv sync --group dev
cp .env.example .env   # add your ANTHROPIC_API_KEY
uv run main.py path/to/document.pdf
```

Full setup (including optional Langfuse tracing):
[installation guide](docs/01-getting-started/01-installation.md).

## Documentation

Ordered simple → deep. Read it at
**[lucagattoni.github.io/PDFScout](https://lucagattoni.github.io/PDFScout/)**
(auto-deployed from `main`), browse the sources below on GitHub, or serve
locally with `make docs`.

| Section | Read this for |
|---|---|
| [Getting Started](docs/01-getting-started/README.md) | Install and run your first extraction |
| [Concepts](docs/02-concepts/README.md) | How and why it works — agentic design, LangGraph mechanics, the logic behind every heuristic |
| [Reference](docs/03-reference/README.md) | Every configuration constant, environment variables, limitations, REST API |
| [Contributing](docs/04-contributing/README.md) | Development commands, test architecture, real-document corpus |

**New to the project?** Start at
[Getting Started](docs/01-getting-started/README.md).
**ML engineer evaluating the design?** Go straight to
[Architecture](docs/02-concepts/01-architecture.md) and
[Design Innovations](docs/02-concepts/03-design-innovations.md).

## Development

```bash
make test   # 241 offline tests, no API key needed
make lint   # ruff check
make ci     # lint + lint-md + test — use before pushing
```

Full command list: [development guide](docs/04-contributing/01-development.md).

## License

MIT — see [LICENSE](LICENSE).
