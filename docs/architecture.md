# Architecture

## Purpose

ReinaLuxe Recovery OS is an AI-native SEO recovery and knowledge management
system intended to:

1. Recover Google Search traffic.
2. Build an AI-powered knowledge base.
3. Automate content publishing and distribution.

## Current stage

Sprint 1 Issue 001 establishes the repository structure, documentation, package
boundary, configuration examples, and development tooling. It does not
implement product capabilities. Sprint 1 Issue 002 adds executable domain and
data contracts for the future Content Audit System without adding processing,
persistence, or integrations.
Sprint 1 Issue 003 adds a deterministic offline import boundary for
owner-provided HTML and JSON fixtures. It creates validated raw and normalized
domain records without accessing any website.
Sprint 1 Stage 004A adds the local SQLite schema and migration foundation while
leaving persistence workflows and repository operations for a later stage.
Sprint 1 Stage 004B adds offline transactional repositories and idempotent
`ImportResult` persistence without exposing ORM models or adding integrations.
Sprint 1 Stage 004C exposes those local capabilities through programmatic
database lifecycle services, application DTOs, and a thin offline CLI.
Sprint 1 Stage 004D verifies and documents the complete local workflow without
expanding product behavior.

## Repository structure

- `src/reinaluxe_recovery/` contains the Python package and minimal CLI entry
  point.
- `src/reinaluxe_recovery/domain/` contains immutable Pydantic domain contracts
  and controlled vocabularies.
- `src/reinaluxe_recovery/importing/` contains local input contracts, the
  BeautifulSoup parser, deterministic normalizer, and import diagnostics.
- `src/reinaluxe_recovery/application/` coordinates importer, persistence, and
  detached page queries without duplicating their behavior.
- `src/reinaluxe_recovery/persistence/` contains internal SQLAlchemy metadata,
  SQLite configuration, UTC types, Pydantic persistence DTOs, repositories, and
  the offline transactional import service.
- `migrations/` contains reviewed Alembic schema revisions.
- `tests/` contains automated tests, beginning with an import smoke test.
- `docs/` contains architecture, roadmap, sprint, workflow, and coding guidance.
- `data/` is reserved for future local runtime data; generated or sensitive
  contents are not committed.
- `pyproject.toml` contains project metadata, dependencies, and tool settings.
- `.env.example` documents future environment variables without secrets.

## Technology baseline

- Python 3.12
- `uv` for dependency and environment management
- Typer and Rich for the command-line interface
- Pydantic and pydantic-settings for future validation and configuration
- SQLAlchemy, Alembic, and SQLite as the local persistence baseline
- pytest, Ruff, and mypy for quality checks
- GitHub and Claude Code-assisted development workflow

Declaring a dependency establishes the project baseline; it does not mean the
corresponding capability is implemented.

## Conceptual boundaries

Future functionality should keep interface, application, domain,
configuration, and infrastructure concerns separate. The CLI should translate
user input and render output without owning product logic. Concrete modules,
contracts, persistence decisions, and integration boundaries will be introduced
only by approved implementation issues.

## Issue 002 domain boundaries

The Content Audit domain uses four explicit separations:

- `CrawlSnapshot` preserves raw crawl observations; `Article` contains only
  normalized audit content and references its source snapshot.
- `EvidenceReference` represents factual provenance; `CommunityClaim` remains a
  separately typed statement with an explicit verification status.
- `ContentRiskAssessment` and `RecoveryRecommendation` are generated outputs;
  `HumanReviewDecision` is the only owner/reviewer judgment record.
- `PerformanceSnapshot` uses an enforced page or site scope so the two metric
  levels cannot be mixed.

The versioned `ContentAuditResult` output envelope rejects dangling provenance
references. Domain models are immutable and transport-oriented; they are not
SQLAlchemy models and do not prescribe storage.

Detailed contracts are documented in [Domain Model](domain-model.md) and
[Data Contracts](data-contracts.md).

Issue 002 deliberately contains no AI-authorship probability, ranking-cause or
penalty assertion, similarity algorithm, scoring formula, crawler, database
model, publishing action, or business integration.

## Issue 003 offline import boundary

The import flow is deliberately one-way and offline:

```text
local HTML or JSON fixture -> ParsedDocument -> CrawlSnapshot + Article
```

The parser prefers semantic article/main content, strips tested site chrome,
normalizes whitespace and relative URLs, and handles malformed optional blocks
with warnings. The normalizer uses the existing domain contracts unchanged,
derives stable UUIDv5 identities from the source hash, and records value
provenance. Missing required structural facts produce a failed `ImportResult`
rather than invented content.

The CLI remains thin: it validates paths and owner-supplied provenance, calls
the import boundary, and prints or writes JSON. No network client, persistence
adapter, or business integration exists. See [Offline Import](offline-import.md)
and [Import Contracts](import-contracts.md).

## Stage 004A persistence foundation

SQLite stores page identities, raw crawl observations, normalized Article JSON
versions, and import warnings. Complex domain structures remain validated JSON;
the schema does not duplicate every content component relationally. SQLAlchemy
ORM objects remain internal and never replace Pydantic application contracts.

All history foreign keys use conservative `RESTRICT` behavior. SQLite foreign
keys are enabled on every connection, datetimes are rejected unless aware and
stored as UTC ISO 8601 values, and transactions use an explicit context
manager. Alembic owns schema creation and downgrade behavior. See
[Database Schema](database-schema.md) and
[Persistence Foundation](persistence-foundation.md).

Stage 004A deliberately omits repositories, save/idempotency workflows,
article-version decisions, and CLI database commands.

## Stage 004B persistence workflow

The Stage 004B flow remains local and synchronous:

```text
validated ImportResult -> URL/content identity -> one SQLite transaction
                       -> detached Pydantic persistence result
```

Repositories query through a caller-owned session and return DTOs. The service
stores crawl history on every new observation, creates Article versions only
when normalized editorial content changes, and moves the current pointer only
after a new version is flushed. Exact repeats and unchanged content are
idempotent. Contract-valid failed imports retain diagnostics but cannot create
or select an Article version.

See [Persistence Contracts](persistence-contracts.md) and
[Idempotency and Versioning](idempotency-and-versioning.md). Stage 004B adds no
CLI persistence command, network client, analysis, scoring, publishing, or
business integration.

## Stage 004C local application workflow

Database-backed CLI commands call an application or lifecycle boundary rather
than SQLAlchemy models directly:

```text
CLI -> lifecycle / application service -> importer, repository, persistence
```

Lifecycle functions invoke Alembic programmatically and return revision and
health DTOs. `OfflineImportWorkflow` calls the existing importer once and then
the Stage 004B persistence service. `PageQueryService` opens read sessions and
returns inventory/detail Pydantic contracts. No ORM object reaches the CLI.

Missing and older databases are safely initialized or upgraded only when a
database-backed command is explicitly invoked. Existing contents are never
deleted or replaced. See [CLI Reference](cli-reference.md) and
[Local Offline Workflow](local-workflow.md).

## Issue 001 scope boundary

This scaffold does not implement:

- Crawling or parsing
- Database models or migrations
- SEO analysis or recovery logic
- LLM integration
- Reddit collection
- WordPress integration
- Pinterest automation
- A dashboard

## Stage 004D release boundary

Stage 004D closes Sprint 1 through documentation consistency, CLI help checks,
the complete automated quality suite, and an isolated idempotent smoke workflow.
It adds no new runtime capability, dependency, database schema, or integration.
