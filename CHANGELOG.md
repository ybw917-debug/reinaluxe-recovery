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

## Sprint 1

### Day 1

- Repository created
- Project initialized
- Folder structure completed
