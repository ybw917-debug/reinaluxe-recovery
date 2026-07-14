# Batch Import Workflow

## Dry run

Without `--database`, `import-batch` always validates and parses locally without
persistence. `--dry-run` enforces the same behavior even when `--database` is
present: no database directory is created, and no migration or write occurs.

The entire JSON contract and all confined paths are validated before any entry
is attempted. Selected files are then read and parsed exactly once in manifest
order. Disabled, filtered, limited, and fail-fast remainder entries are reported
without parsing.

## Persisted run

With `--database` and without `--dry-run`, the existing lifecycle service safely
initializes or upgrades the SQLite file once. It never deletes, replaces, or
recreates existing contents. Each attempted entry then delegates its existing
`ImportResult` to `ImportPersistenceService`, which owns one transaction.

Successful earlier transactions remain committed if a later file, controlled
import, or persistence operation fails. Controlled failed imports preserve
diagnostics by default and never create Article versions;
`--no-persist-failed` skips those writes.

## Continue, fail fast, and selection

The default `--continue-on-error` attempts every selected enabled entry and
reports all outcomes. `--fail-fast` stops after the first failed entry and marks
later selected entries `not_attempted`. Disabled entries and entries excluded by
filters or limits are `skipped`.

Repeated `--entry-id` options select explicit IDs. Unknown IDs and a selection
with no enabled entries fail before database work. `--limit` applies after
enabled and ID filtering. Manifest order is never changed and the manifest
contract is never mutated.

## Resume and idempotency

There is no checkpoint file, job database, retry, worker, or scheduler. Resume
by rerunning the same manifest:

- exact prior observations reuse page, crawl, and Article version records;
- a new timestamp with unchanged normalized content creates crawl history and
  reuses the Article version;
- changed normalized content creates the next sequential Article version;
- corrected missing, mismatched, or controlled-failure entries are attempted
  normally.

## Offline boundary

The workflow performs no HTTP, DNS, browser, sitemap, cloud, WordPress, Reddit,
LLM, scoring, similarity, rewriting, publishing, scheduling, or background work.
Processing is sequential and automatic retries are intentionally absent.
