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

Sprint 1 currently provides deterministic offline HTML import, validated domain
contracts, local SQLite persistence, idempotent Article history, programmatic
database lifecycle, and owner-facing CLI queries. It does not implement live
crawling, SEO scoring, LLM calls, publishing, or external integrations.

## Tech stack

- Python 3.12 managed with `uv`
- SQLite local persistence with SQLAlchemy and Alembic
- Pydantic and pydantic-settings for validation and configuration
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

The project uses uv-managed stable Python 3.12:

```console
uv sync --group dev
uv run reinaluxe-recovery --help
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy
```

Project commands should run through `uv`; do not use the older system Python.

## Local database quick start

From PowerShell in the repository root:

```powershell
# 1. Initialize or safely upgrade the local database.
uv run reinaluxe-recovery db-init

# 2. Import one already-saved HTML page; no URL is fetched.
uv run reinaluxe-recovery import-html C:\saved-pages\article.html `
  --source-url https://owner.example/article/ `
  --fetched-at 2026-07-14T12:00:00+08:00 `
  --database data\reinaluxe-recovery.db

# 3. List locally stored pages.
uv run reinaluxe-recovery list-pages

# 4. Inspect one page and its history.
uv run reinaluxe-recovery show-page https://owner.example/article/ `
  --include-history
```

Database-backed commands safely initialize or upgrade the local SQLite file.
They never crawl the supplied URL. See the [CLI reference](docs/cli-reference.md)
and [local workflow](docs/local-workflow.md).

## Documentation

- [Architecture](docs/architecture.md)
- [Roadmap](docs/roadmap.md)
- [Sprint 1](docs/sprint-1.md)
- [Development workflow](docs/development-workflow.md)
- [Coding guidelines](docs/coding-guidelines.md)
- [CLI reference](docs/cli-reference.md)
- [Local offline workflow](docs/local-workflow.md)

Started by Bowen Yuan.
