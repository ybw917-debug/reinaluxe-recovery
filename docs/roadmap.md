# Roadmap

## Product direction

ReinaLuxe Recovery OS has three long-term goals:

1. Recover Google Search traffic.
2. Build an AI-powered knowledge base.
3. Automate content publishing and distribution.

## Current sprint

### Sprint 2 — Local Content Audit Operations

Status: Issue 005 implemented and validated

Sprint 1 completed the repository, domain contracts, deterministic single-file
offline importer, SQLite persistence and migrations, idempotent versioning, and
local inspection CLI.

Issue 005 adds deterministic batch offline import:

- Strict versioned local JSON manifests
- Manifest-root path confinement and optional source-hash checks
- Sequential dry-run and per-entry persisted workflows
- Continue-on-error, fail-fast, filters, limits, and stable reports
- Rerun-based resume through existing persistence idempotency

## Future work

Later approved issues may add structural audit and recovery capabilities on the
validated local content base. Requirements, interfaces, priorities, and delivery
dates remain subject to separate issue approval.

## Current scope exclusions

Issue 005 does not implement live acquisition, sitemap access, network clients,
parallel or background jobs, automatic retries, similarity, SEO scoring,
recovery prioritization, LLMs, rewriting, WordPress, Reddit, Pinterest,
publishing, scheduling, cloud storage, or dashboards. Listing these areas does
not commit their design, priority, or delivery date.
