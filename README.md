# ReinaLuxe Recovery OS

ReinaLuxe Recovery OS is an AI-native SEO recovery and knowledge management
system for ReinaLuxe.

> **Current sprint:** Sprint 1 — Content Audit System
>
> **Status:** 🟢 In Development

## Project goals

1. Recover Google Search traffic.
2. Build an AI-powered knowledge base.
3. Automate content publishing and distribution.

## Current scope

Sprint 1 Issue 001 establishes the repository foundation: a minimal Python
package, project-tool configuration, documentation, and an import smoke test.
It does not implement crawler, parser, database-model, SEO, LLM, Reddit,
WordPress, Pinterest, or dashboard functionality.

## Tech stack

- Python 3.12 managed with `uv`
- SQLite as the planned local persistence baseline, with SQLAlchemy
- Pydantic and pydantic-settings for future validation and configuration
- Typer and Rich for the command-line interface
- pytest, Ruff, and mypy for project quality checks
- GitHub and AI-assisted development, including Claude Code

Declaring a dependency establishes the project baseline; it does not mean that
the corresponding product capability has been implemented.

## Repository structure

```text
.
├── docs/                       Project documentation
├── src/reinaluxe_recovery/     Python package and minimal CLI
├── tests/                      Automated tests
├── data/                       Local runtime data (ignored; created as needed)
├── .env.example                Non-secret configuration example
└── pyproject.toml              Project and tool configuration
```

## Getting started

After the environment-validation step is approved, the intended workflow is:

```console
uv sync --group dev
uv run reinaluxe-recovery --help
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy
```

These commands are documented for the next stage; dependency synchronization
and quality checks were intentionally not run during scaffolding.

## Documentation

- [Architecture](docs/architecture.md)
- [Roadmap](docs/roadmap.md)
- [Sprint 1](docs/sprint-1.md)
- [Development workflow](docs/development-workflow.md)
- [Coding guidelines](docs/coding-guidelines.md)

Started by Bowen Yuan.
