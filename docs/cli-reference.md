# CLI Reference

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
