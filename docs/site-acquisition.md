# Safe Read-Only Site Acquisition

`acquire-site` performs sequential public HTTP GET requests and writes raw HTML
snapshots plus an Issue 005-compatible manifest. It never imports, opens SQLite,
runs an audit, authenticates, submits a form, executes JavaScript, or changes a
website. Import remains an explicit second command.

## PowerShell

```powershell
uv run reinaluxe-recovery acquire-site `
  --sitemap https://www.reinaluxe.co/sitemap.xml `
  --allowed-host reinaluxe.co --allowed-host www.reinaluxe.co `
  --output-directory D:\ReinaLuxeAcquisitions `
  --acquisition-id 2026-07-14

uv run reinaluxe-recovery import-batch `
  D:\ReinaLuxeAcquisitions\2026-07-14\manifest.json --dry-run
```

Alternatively pass `--url-list PATH` containing a JSON string array or one URL
per line. Exactly one source mode is required. URL fragments are removed;
path case and query strings remain. Exact normalized URLs are deduplicated in
source order. Include patterns select first, then exclude patterns remove.

The output directory contains `acquisition-request.json`,
`acquisition-result.json`, `manifest.json`, `html/<stable-id>.html`, and
`metadata/<stable-id>.json`. HTML bytes are preserved. Filenames derive from
UUID5 URL identities. JSON is UTF-8 and writes are atomic where practical.
Existing output is refused unless `--overwrite-existing` is explicit. An
identical existing final-URL snapshot with the same decoded-source SHA-256 is
reported unchanged and not duplicated.

The manifest is validated with the existing `BatchManifest` contract before
writing. It contains one enabled entry per fetched/unchanged snapshot, the final
allowed URL, fetch timestamp/status, safe response headers, relative HTML path,
and expected source hash.

Exit codes: `0` complete, `1` controlled page failure, `2` arguments/list/path,
`3` sitemap or robots discovery, `4` unsafe target or acquisition system, and
`5` no eligible URL. No automatic retries, conditional requests, hidden state,
parallelism, background work, or scheduling exist.
