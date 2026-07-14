# Sprint 1 — Content Audit System

Status: 🟢 In Development

## Sprint intent

Sprint 1 begins the Content Audit System. Issue 001 provides the repository
foundation. Issue 002 defines the domain model and data contracts required for
later approved implementation work. Issue 003 provides deterministic offline
normalization of owner-provided content into those contracts. Stage 004A adds
the local SQLite schema and migration foundation.
Stage 004B adds transactional repository reads and idempotent offline import
persistence.

## Issue 001 — Repository scaffolding

### Objective

Create a clear, minimal, and reproducible Python project scaffold without
implementing product behavior.

### Deliverables

- Project overview and changelog
- Architecture and roadmap documentation
- Development workflow and coding guidelines
- Coding-agent guidance
- Python 3.12 project configuration
- Minimal `src/reinaluxe_recovery` package and CLI entry point
- Import smoke test
- Non-secret environment variable example and Git ignore rules

### Acceptance criteria

- Owner-authored project facts remain represented.
- The package layout and project metadata are internally consistent.
- Dependencies and development tools are declared but not installed during
  scaffolding.
- No secrets are committed.
- No product capability is implemented.
- Environment validation is deferred until explicit approval.

## Out of scope

Issue 001 does not implement:

- Crawler or parser behavior
- Database models or migrations
- SEO analysis or recovery logic
- LLM integration
- Reddit collection
- WordPress integration
- Pinterest automation
- Dashboard functionality

## Validation gate

After approval, first confirm the Python 3.12 and `uv` executables. Dependency
synchronization and the configured test, lint, format-check, and type-check
commands follow only after that environment check succeeds.

## Issue 002 — Content Audit domain model and contracts

### Objective

Define a stable, extensible vocabulary and executable input/output contracts for
future content-audit work without implementing collection, analysis, storage,
or publishing behavior.

### Deliverables

- Immutable Pydantic v2 models for normalized content, evidence, audit output,
  human review, raw crawl snapshots, and scoped performance snapshots
- Controlled enums for lifecycle, content, intent, evidence, risk, review,
  recovery, links, schema, similarity, and metric scope
- Versioned `Article`, `CrawlSnapshot`, `PerformanceSnapshot`, and
  `ContentAuditResult` contracts
- Domain-model and data-contract documentation
- Complete normalized-article and audit-result JSON examples
- Unit tests for validation, provenance separation, and JSON round trips

### Acceptance criteria

- Raw crawl data remains separate from normalized article data.
- Factual evidence remains separate from community claims.
- Automated assessments and recommendations remain separate from human review.
- Page-level and site-level metrics cannot be mixed.
- Every derived audit reference preserves resolvable provenance.
- Timestamps are timezone-aware and URLs are validated.
- No AI probability, assumed Google penalty, or unsupported ranking-cause field
  exists.
- pytest, Ruff, and mypy pass through the uv-managed Python environment.

### Out of scope

- SQLAlchemy models or migrations
- Crawling, parsing, similarity algorithms, or scoring formulas
- SEO automation, article rewriting, or LLM prompts/calls
- Reddit, WordPress, Pinterest, or dashboard integrations
- Automatic publishing or owner decisions

## Issue 003 — Deterministic offline content import

### Objective

Convert owner-provided local HTML and structured JSON fixtures into validated
`CrawlSnapshot` and `Article` records without live crawling or inference.

### Deliverables

- Strict local HTML and JSON fixture input contracts
- BeautifulSoup intermediate parser with deterministic extraction rules
- Stable source hashes, UUIDv5 record identities, and field provenance
- Recoverable warnings and controlled fatal import results
- Thin `import-html` CLI command with JSON output
- Representative offline fixtures and unit/CLI coverage
- Import-contract and operating documentation

### Acceptance criteria

- Relative URLs resolve without network access.
- Semantic content is preferred and overlapping containers are not duplicated.
- Optional malformed metadata warns without discarding usable content.
- Required domain facts are never invented.
- Repeated imports produce stable hashes and identifiers.
- Existing domain contracts remain unchanged.
- pytest, Ruff, formatting, and mypy pass through uv-managed Python 3.12.

### Out of scope

- Live crawling or access to ReinaLuxe, WordPress, Reddit, or communities
- Persistence, SQLAlchemy models, or migrations
- Scoring, similarity, SEO conclusions, LLMs, rewriting, or publishing
- Pinterest, dashboards, and business automation

## Stage 004A — SQLite schema and initial migration

### Objective

Create the local persistence foundation without implementing persistence
workflows or repository queries.

### Deliverables

- Typed SQLAlchemy 2.x models for pages, crawls, article versions, and warnings
- Synchronous SQLite engine, session, transaction, and UTC timestamp utilities
- Foreign-key enforcement and conservative history relationships
- Configurable Alembic environment and reviewed initial migration
- Upgrade, downgrade, schema, relationship, constraint, and timestamp tests
- Database-schema and persistence-foundation documentation

### Acceptance criteria

- Existing Pydantic domain and import contracts remain unchanged.
- Complex validated content is stored as JSON rather than over-normalized.
- Required uniqueness constraints and indexes are present.
- Naive datetimes are rejected and aware values normalize to UTC.
- Migration upgrade creates the schema and downgrade removes it.
- Tests create databases only in temporary directories.
- No repository/service behavior, CLI database command, or external integration
  is introduced.

## Stage 004B — Transactional import persistence

### Objective

Persist validated offline `ImportResult` records atomically and idempotently
while keeping SQLAlchemy models private.

### Deliverables

- Strict Pydantic persistence results and stored-record summaries
- Conservative canonical URL normalization and stable normalized-content hashes
- Caller-session read repositories with no independent commits
- Atomic import service for pages, crawls, warnings, and Article versions
- Failed-crawl diagnostics without failed Article versions
- Idempotency, versioning, history, rollback, DTO, and health-check tests
- Persistence-contract and versioning documentation

### Acceptance criteria

- Exact repeats do not duplicate crawls, warnings, or versions.
- New unchanged-content crawls reuse the existing Article version.
- Changed content creates sequential versions and transactionally advances the
  current pointer.
- Historical imports preserve minimum first-seen and maximum last-seen times.
- Any failure rolls back the complete import unit.
- Repository methods expose Pydantic DTOs, never ORM instances, and never
  commit caller transactions.
- All behavior remains local and offline with no CLI persistence command or
  business integration.

## Stage 004C — Local database and offline CLI workflow

### Objective

Make the completed offline importer and local persistence layer usable through
safe database lifecycle commands and thin owner-facing CLI workflows.

### Deliverables

- Programmatic Alembic initialization, upgrade, revision, and health services
- `db-init`, database-enabled `import-html`, `list-pages`, and `show-page`
- Stable Pydantic lifecycle, inventory, workflow, and page-detail outputs
- Automatic safe initialization/upgrade for explicitly database-backed commands
- Human Rich output, stable JSON output, and deterministic exit codes
- Lifecycle, orchestration, CLI integration, compatibility, and smoke tests
- PowerShell quick start, CLI reference, and local workflow documentation

### Acceptance criteria

- Existing no-database `import-html` output and exit behavior remain compatible.
- Import parsing occurs once and persistence delegates to the Stage 004B service.
- Database lifecycle never deletes or replaces an existing database.
- Page inventory and details expose DTOs rather than ORM objects.
- Failed imports persist diagnostics by default and never create Article versions.
- All commands remain local and offline with no external integration.
