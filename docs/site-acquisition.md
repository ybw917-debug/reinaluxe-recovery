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

Before an article request, robots policy is loaded once per origin and cached
for that run. HTTP 200 is parsed and HTTP 404 allows acquisition. A policy rule
that denies the URL produces `skipped / robots_disallow`. A robots transport
failure, non-200/non-404 status, or UTF-8 parse failure instead produces a
failed page with `robots_fetch_error`, `robots_http_error`, or
`robots_parse_error`; it remains fail-closed and is inherited by later pages at
that origin without another robots request. No article request is made in these
failure cases and no automatic retry occurs.

Robots matching uses the configured User-Agent's leading product token while
the complete configured value is still sent in HTTP. Case-insensitive exact
product-token groups are merged; partial names do not match, and wildcard
groups are used only when no exact group exists. The longest matching rule wins
and Allow wins a tie. Matching covers the
normalized path plus query string when present, so query-specific policy rules
are supported consistently.

Exit codes: `0` complete, `1` controlled page failure, `2` arguments/list/path,
`3` sitemap discovery, `4` unsafe target or acquisition system, and
`5` no eligible URL. No automatic retries, conditional requests, hidden state,
parallelism, background work, or scheduling exist.
