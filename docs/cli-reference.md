# CLI Reference

## Offline community evidence commands

`community-import --manifest PATH --output DIRECTORY` validates a confined
local manifest and writes normalized source, claim, evidence, warning, and
summary files without fetching source URLs.

`community-export-review --input DIRECTORY --output DIRECTORY` writes CSV/JSON
owner queues and source/evidence indexes with blank decision fields.

`community-apply-decisions --review CSV --input DIRECTORY --output DIRECTORY`
validates explicit owner decisions while retaining pending, rejected, and
contradicted audit records.

`community-build-kb --input DIRECTORY --output DIRECTORY` exports only approved
or qualified, evidence-linked entries. It does not publish them.

Community workflow validation errors use exit code `6`. See
[Community Offline Import](community-offline-import.md) and
[Community Review Workflow](community-review-workflow.md).

## Approved knowledge and content opportunity commands

`community-build-snapshot --inputs DIRECTORY... --output DIRECTORY` builds a
hash-locked, byte-stable snapshot from one or more approved Stage 009A KB
batches. Repeat `--inputs` for additional batches.

`content-build-page-context --role-matrix CSV --finding-register CSV --roadmap
MARKDOWN --output DIRECTORY [--database PATH] [--readiness CSV]` snapshots the
authoritative 25-page plan and reads current Article versions through an
immutable read-only SQLite connection.

`community-map-opportunities --knowledge-snapshot DIRECTORY --page-context
DIRECTORY --output DIRECTORY` applies transparent entity, role, intent,
cluster, and temporal rules and emits pending opportunities without copy.

`community-export-opportunity-review --input DIRECTORY --output DIRECTORY`
creates a blank owner review queue. `community-apply-opportunity-decisions
--review CSV --input DIRECTORY --output DIRECTORY` validates the completed
queue and retains pending, rejected, and deferred audit records.

`content-build-change-manifest --decisions DIRECTORY --knowledge-snapshot
DIRECTORY --page-context DIRECTORY --output DIRECTORY [--database PATH]`
creates a hash- and page-version-locked future drafting handoff from approved
decisions only. It performs no drafting or writes.

Content-operation validation errors use exit code `7`. See
[content mapping](community-content-mapping.md),
[opportunity review](content-opportunity-review.md), and
[change manifests](content-change-manifest.md).

All commands run through the repository's uv-managed Python environment and
remain fully local. None of them fetches a URL.

## Database policy

Database-backed commands safely initialize a missing local SQLite database and
upgrade an older database to the current Alembic revision. Existing contents
are never deleted or overwritten. The default database path is the ignored
local file `data/reinaluxe-recovery.db`; `--database PATH` selects another local
file.

## `db-init`

```powershell
uv run reinaluxe-recovery db-init [--database PATH] [--json]
```

Creates missing parent directories, applies Alembic migrations programmatically,
and performs a health check. Human output reports the resolved path, redacted
SQLite URL, previous and current revisions, migration status, and health.
`--json` returns those values as `DatabaseLifecycleResult`.

## `import-html`

```powershell
uv run reinaluxe-recovery import-html PAGE.html `
  --source-url https://owner.example/page/ `
  --fetched-at 2026-07-14T12:00:00+08:00 `
  [--output RESULT.json] `
  [--json-output RESULT.json] `
  [--database PATH] `
  [--persist-failed | --no-persist-failed]
```

Without `--database`, behavior is backward compatible: the command emits or
writes the original `ImportResult` JSON only. `--json-output` is an alias for
the existing `--output` option.

With `--database`, the command initializes/upgrades the database, parses the
HTML exactly once, and delegates persistence to `ImportPersistenceService`.
Output is a stable `ImportWorkflowResult` object:

```json
{
  "import_result": {},
  "persistence_result": {}
}
```

Failed imports are persisted as crawl diagnostics by default, matching Stage
004B. `--no-persist-failed` returns a null `persistence_result` for controlled
failed content. Failed imports never create or select an Article version.

## `import-batch`

```powershell
uv run reinaluxe-recovery import-batch MANIFEST_PATH `
  [--database PATH] [--dry-run] `
  [--continue-on-error | --fail-fast] `
  [--persist-failed | --no-persist-failed] `
  [--entry-id TEXT]... [--limit INTEGER] `
  [--json] [--output PATH]
```

Loads one strict local JSON manifest and processes enabled entries in manifest
order. Without `--database`, the command always performs a dry run and reports
`not persisted`. `--dry-run` also prevents database creation or upgrade when a
database path is supplied.

`--entry-id` is repeatable. Unknown IDs fail clearly; `--limit` applies after
enabled-entry and explicit-ID filtering while preserving manifest order. The
default is `--continue-on-error`; `--fail-fast` marks later selected entries as
`not_attempted`. Controlled failed imports persist diagnostics by default only
when a database is active.

`--json` prints `BatchImportResult`. `--output` creates requested parent
directories and writes the same contract as UTF-8 JSON, but refuses to overwrite
an existing file. Human output includes aggregate counts and one concise row per
manifest entry.

Batch exit codes are:

- `0`: every attempted entry succeeded, including a valid dry run;
- `1`: one or more file or controlled import failures were reported;
- `2`: invalid argument, manifest, confined-path policy, or output operation;
- `3`: database initialization or migration failure;
- `4`: one or more persistence-system failures;
- `5`: unknown entry filter or no matching enabled entries.

A missing selected HTML file or expected-hash mismatch is reported as an entry
failure (`1`) so `--continue-on-error` can still process other entries. Absolute
or escaping manifest paths invalidate the manifest before database work (`2`).

## `list-pages`

```powershell
uv run reinaluxe-recovery list-pages `
  [--database PATH] [--json] [--limit INTEGER] [--offset INTEGER]
```

Human output is a Rich table ordered by canonical URL. It shows current version,
first/last observation times, crawl count, and Article-version count. JSON is a
stable `PageInventoryResult` with `items`, `limit`, and `offset`.

## `show-page`

```powershell
uv run reinaluxe-recovery show-page URL `
  [--database PATH] [--json] [--include-history]
```

Shows the page summary and latest Article. `--include-history` adds crawl
history, Article-version history, and warnings grouped by crawl. A missing page
is reported distinctly from a database failure.

## Exit codes

- `0`: command succeeded;
- `1`: offline content produced a controlled failed `ImportResult`;
- `2`: input, argument, file-reading, or output-writing error;
- `3`: database initialization or migration error;
- `4`: import persistence error;
- `5`: page not found or page-query failure.

Expected errors are written to stderr without raw stack traces.

## `audit-articles`

```powershell
uv run reinaluxe-recovery audit-articles [--database PATH] [--all-versions] `
  [--page-url URL]... [--rule CODE]... [--include-info|--exclude-info] `
  [--limit INTEGER] [--json] [--output PATH] [--fail-on-errors]
```

Audits current normalized versions by default, read-only and offline. The full
exit policy is in [the audit policy](article-structure-audit.md).

## `acquire-site`

```powershell
uv run reinaluxe-recovery acquire-site `
  (--sitemap URL ... | --url-list PATH) --allowed-host HOST ... `
  [--output-directory PATH] [--acquisition-id TEXT] [--user-agent TEXT] `
  [--timeout FLOAT] [--delay FLOAT] [--maximum-urls INTEGER] `
  [--include-pattern GLOB]... [--exclude-pattern GLOB]... `
  [--overwrite-existing] [--json] [--result-output PATH]
```

The command only acquires public HTML and emits a batch manifest. See
[site acquisition](site-acquisition.md) for exit codes and security policy.
