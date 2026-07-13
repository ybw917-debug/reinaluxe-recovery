# Sprint 1 — Content Audit System

Status: 🟢 In Development

## Sprint intent

Sprint 1 begins the Content Audit System. Issue 001 provides the repository
foundation. Issue 002 defines the domain model and data contracts required for
later approved implementation work.

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
