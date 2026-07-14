# Sprint 2 — Local Content Audit Operations

Status: In Development

Issue 006 implements a deterministic read-only structure audit over persisted
normalized Article versions. Audit persistence, fetching, scoring, similarity,
and generation remain outside scope.

Issue 007 adds conservative public read-only acquisition and Issue 005 manifest
generation. Acquisition remains separate from import, persistence, and audit;
it adds no login, publishing, browser automation, bypass, or background work.

## Sprint intent

Sprint 2 builds operational audit inputs on the completed Sprint 1 contracts and
local persistence foundation. Every issue remains explicitly scoped; future
roadmap concepts are not implemented merely because domain vocabulary exists.

## Issue 005 — Deterministic batch offline import

### Objective

Import multiple owner-provided HTML files from one strict local JSON manifest
through existing offline parsing and per-entry persistence boundaries.

### Deliverables

- Versioned manifest, options, entry-result, and aggregate-result contracts
- Manifest-root path confinement and pre-parse expected-hash validation
- Sequential dry-run and optional persisted workflows
- Continue-on-error, fail-fast, entry filtering, and ordered limit behavior
- Rerun-based resume through existing idempotency
- `import-batch` human/JSON CLI and non-overwriting report files
- Synthetic fixtures, focused tests, documentation, and isolated smoke workflows

### Explicit exclusions

- Live crawling, sitemap retrieval, HTTP, browsers, or network clients
- Parallel processing, workers, scheduling, retries, or checkpoint storage
- WordPress, Reddit, Pinterest, cloud storage, or publishing
- LLMs, similarity, scoring, recovery priority, or rewriting
- Database migration or schema changes
