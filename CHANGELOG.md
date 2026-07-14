# Changelog

Notable project changes are recorded in this file.

## Unreleased

### Repository scaffolding

- Added Python 3.12 project metadata and `uv` dependency groups.
- Added the minimal `reinaluxe_recovery` package and import smoke test.
- Added repository, architecture, sprint, workflow, and coding documentation.
- Added non-secret environment and Git ignore templates.
- Pinned the project to uv-managed stable Python 3.12 and generated `uv.lock`.
- Validated package import, linting, formatting, and static typing in the
  synchronized project environment.
- Added versioned Content Audit domain models and controlled vocabularies.
- Added executable input/output contracts that separate raw data, normalized
  content, factual evidence, community claims, automated assessments, and human
  decisions.
- Added complete JSON contract examples and validation/round-trip tests.
- Documented the domain model, provenance rules, and Issue 002 scope boundaries.
- Added strict local HTML and JSON fixture import contracts.
- Added deterministic BeautifulSoup parsing and normalization into validated
  `CrawlSnapshot` and `Article` records with stable IDs and provenance.
- Added recoverable extraction warnings, controlled fatal results, and the
  offline `import-html` CLI command.
- Added representative offline fixtures, import/CLI tests, and Issue 003
  documentation.
- Added the Stage 004A SQLAlchemy schema for page, crawl, article-version, and
  import-warning history.
- Added synchronous SQLite configuration with foreign-key enforcement,
  UTC-aware timestamp storage, explicit transaction scope, and Alembic.
- Added a reviewed initial upgrade/downgrade migration plus schema-level tests
  and persistence documentation.
- Added strict Pydantic persistence DTOs and detached read repositories for
  page, crawl, Article-version, and warning history.
- Added deterministic canonical URL normalization and SHA-256 hashing of
  editorially meaningful normalized Article content.
- Added atomic idempotent `ImportResult` persistence with sequential versions,
  safe current-version updates, failed-crawl diagnostics, and rollback tests.
- Documented repository contracts, idempotency behavior, timestamp ordering,
  transaction ownership, and SQLite concurrency limits.
- Added programmatic local SQLite initialization, Alembic upgrade, revision,
  current-schema, and health-check lifecycle operations.
- Added thin application workflows plus `db-init`, database-enabled
  `import-html`, `list-pages`, and `show-page` CLI behavior.
- Added aggregate page-inventory and detailed history DTOs without changing the
  database schema or exposing ORM objects.
- Added lifecycle, CLI, compatibility, pagination, failure, and orchestration
  tests plus owner-facing PowerShell workflow documentation.
- Completed the Sprint 1 release audit with an authoritative owner quick start,
  CLI help coverage, manual SQLite backup guidance, and an isolated idempotent
  workflow check.
- Reconfirmed JSON-only compatibility, failed-import policy, ignored local data,
  offline-only operation, and the complete pytest, Ruff, and mypy quality gates.
- Added strict versioned JSON batch manifests with confined relative paths,
  timestamp/header inheritance, source-hash validation, filtering, and limits.
- Added sequential dry-run and persisted batch orchestration that reuses the
  existing parser, normalizer, database lifecycle, and per-entry transactions.
- Added `import-batch` with human and JSON reports, continue/fail-fast handling,
  rerun-based resume, stable exit codes, synthetic fixtures, and focused tests.
- Added deterministic read-only Article structure audit contracts, transparent
  rules, latest/history selection, local inventory checks, aggregate reporting,
  `audit-articles`, tests, and documentation without a migration.

## Sprint 1

### Day 1

- Repository created
- Project initialized
- Folder structure completed
