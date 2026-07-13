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

## Repository structure

- `src/reinaluxe_recovery/` contains the Python package and minimal CLI entry
  point.
- `src/reinaluxe_recovery/domain/` contains immutable Pydantic domain contracts
  and controlled vocabularies.
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
- SQLAlchemy with SQLite as the intended future persistence baseline
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
