# PDFScout Documentation

An agnostic, multi-agent PDF structure extractor that converts any PDF into a
validated, hierarchical JSON tree — built on LangGraph with Claude's native
PDF vision API. This documentation is ordered **simple → deep**: start with
Getting Started, go deeper as you need.

<div class="grid cards" markdown>

- :material-rocket-launch-outline:{ .lg .middle } **Getting Started**

    ---

    Install, configure your API key, run your first extraction. No prior
    knowledge assumed.

    [:octicons-arrow-right-24: Installation](01-getting-started/01-installation.md) ·
    [Usage](01-getting-started/02-usage.md)

- :material-graph-outline:{ .lg .middle } **Concepts**

    ---

    How and *why* it works: the agentic design, LangGraph mechanics,
    reading-order and coverage-oracle logic, the output format, and the design
    rationale versus traditional parsers.

    [:octicons-arrow-right-24: Architecture](02-concepts/01-architecture.md) ·
    [Output Format](02-concepts/02-output-format.md) ·
    [Design Innovations](02-concepts/03-design-innovations.md)

- :material-tune:{ .lg .middle } **Reference**

    ---

    Every tunable constant with the principle behind it, environment
    variables, limitations, and the REST API.

    [:octicons-arrow-right-24: Configuration](03-reference/01-configuration.md) ·
    [API](03-reference/02-api.md)

- :material-source-pull:{ .lg .middle } **Contributing**

    ---

    Development commands, the three-tier test architecture, and the
    real-document corpus workflow.

    [:octicons-arrow-right-24: Development](04-contributing/01-development.md) ·
    [Testing](04-contributing/02-testing.md) ·
    [Real-Doc Workflow](04-contributing/03-real-doc-workflow.md)

</div>

## Reading paths

**New to the project?**
[Installation](01-getting-started/01-installation.md) →
[Usage](01-getting-started/02-usage.md) →
[Output Format](02-concepts/02-output-format.md).

**ML / LLM engineer evaluating the design?**
[Architecture](02-concepts/01-architecture.md) (agentic design, LangGraph
mechanics, the pre-sorter and oracle logic) →
[Design Innovations](02-concepts/03-design-innovations.md) →
[Configuration](03-reference/01-configuration.md) →
[Testing](04-contributing/02-testing.md).

## Elsewhere in the repo

- [Changelog](https://github.com/lucagattoni/PDFScout/blob/main/CHANGELOG.md) —
  versioned release history
- [Roadmap](https://github.com/lucagattoni/PDFScout/blob/main/ROADMAP.md) —
  open items, deferred decisions, rejected proposals
- [Schema authoring guide](https://github.com/lucagattoni/PDFScout/blob/main/schemas/README.md) —
  add a new document type
