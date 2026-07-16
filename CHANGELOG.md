# Changelog

## Stage 009C-Core-1B.1B - 2026-07-16

- Rephrased the three AAA preview queries for natural Reddit, public-forum, and expert retrieval, including explicit PSP expansion and limited exact-phrase use.
- Added research-question/lane consistency, quote-overconstraint, acronym-disambiguation, semantic anchor-group, natural-language score, and retrieval-quality contracts.
- Required both structural and retrieval quality before a paid provider call while preserving the existing entity-contamination gate.

## Stage 009C-Core-1B.1A - 2026-07-16

- Added offline exact-query previews, deterministic lane templates, entity-contamination controls, query hashes, and paid-call quality gates.
- Separated requested and classified source lanes, added family-specific relevance screening, and clustered regional official domains by organization.
- Split resolved image candidates from unresolved visual pages and added an offline audit for previously captured smoke artifacts without claim generation.

## Stage 009C-Core-1B - 2026-07-16

- Added the hard-limited `research-smoke` workflow with provider-call, raw-result, source-integrity, GLM-validation, visual-candidate, synthesis, and recommendation outputs.
- Added strict Reddit permalink screening, tracking-safe normalization, duplicate/source-cluster reporting, provider-result traceability, and rejection of model-added URLs or ungrounded numbers.
- Added `research-build-asset-manifest` for relative-path inventory, SHA-256, optional perceptual hashes, duplicate reporting, owner-original protection, and Core-1A new-page intake.
- Documented smoke operations, visual candidates, asset manifests, and the recommended Hermès asset-library layout.

## Stage 009C-Core-1A - 2026-07-16

- Added research-only, legacy-reconstruction, and new-page-build production modes.
- Added evidence-owned assertive synthesis, first-person eligibility, prohibited-overclaim, and publication-wording registers.
- Added ENRICH-first reconstruction packages that preserve existing sections, distinctive passages, images, and internal links without requiring new owner-handled evidence.
- Added reusable-topic and local asset-manifest inspection for future page blueprints and evidence/image gaps.
- Added planning-only AAA reconstruction output and a generic Hermès model new-page template; no live search or publication was performed.

## Stage 009C-Core - 2026-07-16

- Added generic article/topic research contracts and configurable public-source lanes.
- Added Zhipu web search plus optional GLM source analysis behind provider interfaces.
- Added deterministic source and image screening, atomic claims, corroboration, contradiction preservation, topic reuse, article opportunity mapping, and owner-review exports.
- Added a separate ignored research SQLite database and the AAA pilot request template.
- Added seven research CLI commands; no article drafting, WordPress mutation, or production-database write path was introduced.

Notable project changes are recorded in this file.

## Unreleased

### Stage 009B

- Added immutable knowledge-snapshot, page-context, content-opportunity, owner
  decision, and content-change-manifest contracts.
- Added six offline commands for snapshotting approved knowledge and read-only
  page context, deterministic opportunity mapping, owner review, decision
  validation, and hash-locked manifest creation.
- Added explicit model/material/role/intent/temporal mapping policies,
  authentication-versus-buying separation, hub/detail coordination, and safe
  new-article/no-action handling without copy generation.
- Added sanitized Chanel, Hermès, and Louis Vuitton fixtures plus end-to-end
  tests for 25-page preservation, auditability, stale-input rejection, and
  manifest locks.

### Stage 009A

- Added strict public contracts for offline community source records, atomic
  candidate claims, scoped evidence, owner decisions, and approved knowledge.
- Added deterministic normalization, hashing, exact deduplication, transparent
  likely-duplicate reporting, and confined local text/JSON manifest loading.
- Added offline import, owner review export, decision application, and approved
  knowledge-base CLI workflows with supplier-confidentiality safeguards.
- Added community evidence, privacy, import, and human-review policy guides and
  focused end-to-end tests without changing the site database or acquisition.

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
- Added synchronous read-only public HTML acquisition with explicit host and
  robots safeguards, confined snapshots, validated batch-manifest generation,
  mocked-network tests, and the `acquire-site` CLI.
- Corrected robots handling to cache fail-closed transport, HTTP, and parse
  failures as failed pages instead of synthetic policy disallows, and added
  deterministic product-token, duplicate-group, and longest-path rule matching.

## Sprint 1

### Day 1

- Repository created
- Project initialized
- Folder structure completed
