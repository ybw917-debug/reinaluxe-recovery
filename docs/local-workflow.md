# Local Offline Workflow

This workflow is designed for an owner working in Windows PowerShell. It reads
an already-saved HTML file and writes only to a local SQLite database.

## 1. Open the repository

```powershell
Set-Location D:\reinaluxe.recovery\reinaluxe-recovery
```

## 2. Initialize the database

```powershell
uv run reinaluxe-recovery db-init
```

The default file is `data\reinaluxe-recovery.db`. The command is safe to repeat:
it upgrades an older schema and otherwise reports that the database is current.

## 3. Import one saved page

```powershell
uv run reinaluxe-recovery import-html C:\saved-pages\article.html `
  --source-url https://owner.example/article/ `
  --fetched-at 2026-07-14T12:00:00+08:00 `
  --database data\reinaluxe-recovery.db
```

The URL and timestamp are provenance supplied by the owner. The command never
opens the URL. Repeating the exact command is idempotent; a new observation with
unchanged normalized content creates crawl history but not a duplicate Article
version.

## 4. List stored pages

```powershell
uv run reinaluxe-recovery list-pages
```

Use `--json` for structured output or `--limit` and `--offset` for pagination.

## 5. Inspect one page

```powershell
uv run reinaluxe-recovery show-page https://owner.example/article/ `
  --include-history
```

If the HTML contains an explicit canonical URL, use that canonical URL when
inspecting the page. `--json` returns the complete stable query contract.

## Custom database location

Pass the same explicit path to every database-backed command:

```powershell
$Database = "D:\ReinaLuxeData\recovery.db"
uv run reinaluxe-recovery db-init --database $Database
uv run reinaluxe-recovery list-pages --database $Database
```

No database file, JSON output, or saved HTML belongs in Git.

## Manual backup and restoration

The SQLite database is one local file. Close any active ReinaLuxe Recovery
commands before copying it so the copy represents a completed transaction. Back
up both the database file and the owner HTML source files used for imports; the
database does not replace those source files.

Do not edit the SQLite file manually. Automated backup and restore commands do
not exist yet. Restoration currently means closing all active commands and
replacing the inactive local database file with a verified backup copy.
