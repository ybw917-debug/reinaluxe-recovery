# ReinaLuxe Recovery OS

ReinaLuxe Recovery OS is an AI-native SEO recovery and knowledge management
system for ReinaLuxe.

> **Current sprint:** Sprint 2 — Local Content Audit Operations
>
> **Status:** Issue 005 implemented and validated

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

## Windows PowerShell quick start

This is the authoritative owner quick start. Open PowerShell and run:

```powershell
# 1. Open the repository and prepare uv-managed stable Python 3.12.
Set-Location D:\reinaluxe.recovery\reinaluxe-recovery
uv sync --python 3.12 --group dev

# 2. Verify the project.
uv run pytest

# 3. Initialize or safely upgrade the local database.
uv run reinaluxe-recovery db-init

# 4. Import one existing local HTML fixture; no URL is fetched.
uv run reinaluxe-recovery import-html tests\importing\fixtures\complete-article.html `
  --source-url https://owner.example/saved-page/ `
  --fetched-at 2026-07-14T12:00:00+08:00 `
  --database data\reinaluxe-recovery.db

# 5. List locally stored pages.
uv run reinaluxe-recovery list-pages

# 6. Inspect the imported canonical page and its history.
uv run reinaluxe-recovery show-page https://owner.example/guides/craftsmanship/ `
  --include-history

# 7. Locate the local database.
Get-Item data\reinaluxe-recovery.db
```

The database is the single local file `data\reinaluxe-recovery.db`. The `data\`
directory and database extensions are ignored by Git, so local content is not
committed. Database-backed commands safely initialize or upgrade this file and
never crawl the supplied URL. Use project commands through `uv`; do not use the
older system Python. See the [CLI reference](docs/cli-reference.md) and
[local workflow](docs/local-workflow.md) for optional flags and detailed use.

## Batch offline import

Use an explicit local JSON manifest to validate or import multiple saved HTML
files in manifest order. This command remains offline and uses the same parser,
persistence transactions, and idempotent versioning as single-file import:

```powershell
# Validate and parse every enabled entry without creating a database.
uv run reinaluxe-recovery import-batch .\batch\manifest.json --dry-run

# Persist entries one at a time to the local database.
uv run reinaluxe-recovery import-batch .\batch\manifest.json `
  --database data\reinaluxe-recovery.db
```

See the [batch manifest contract](docs/batch-import-contract.md) and
[batch workflow](docs/batch-import-workflow.md) before preparing a manifest.

## Offline article audit

```powershell
uv run reinaluxe-recovery audit-articles --database data\reinaluxe-recovery.db
```

This audits latest normalized Articles without HTML reparsing, database writes,
or network access. See the [audit policy](docs/article-structure-audit.md) and
[rule reference](docs/audit-rule-reference.md).

## Read-only site acquisition

```powershell
uv run reinaluxe-recovery acquire-site --url-list .\urls.txt `
  --allowed-host reinaluxe.co --allowed-host www.reinaluxe.co `
  --output-directory D:\ReinaLuxeAcquisitions --acquisition-id approved-run
```

Acquisition performs public read-only GET requests and creates local snapshots
plus a batch manifest. It does not publish, import, or audit automatically. See
[site acquisition](docs/site-acquisition.md) and
[acquisition security](docs/acquisition-security.md).

## Documentation

- [Architecture](docs/architecture.md)
- [Roadmap](docs/roadmap.md)
- [Sprint 1](docs/sprint-1.md)
- [Development workflow](docs/development-workflow.md)
- [Coding guidelines](docs/coding-guidelines.md)
- [CLI reference](docs/cli-reference.md)
- [Local offline workflow](docs/local-workflow.md)
- [Batch manifest contract](docs/batch-import-contract.md)
- [Batch import workflow](docs/batch-import-workflow.md)
- [Sprint 2](docs/sprint-2.md)
- [Community intelligence](docs/community-intelligence.md)
- [Community evidence policy](docs/community-evidence-policy.md)
- [Community offline import](docs/community-offline-import.md)
- [Community review workflow](docs/community-review-workflow.md)

Started by Bowen Yuan.
