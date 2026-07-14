# Acquisition Security Policy

Only absolute HTTP(S) URLs on explicit allowed hosts are eligible. Core logic
does not hard-code production hosts. Userinfo credentials are rejected. Before
each request and redirect, DNS results are checked; any localhost, loopback,
private, reserved, link-local, or otherwise non-global address rejects the
target. Redirects are limited to five and must remain on an allowed public host.
This reduces SSRF and DNS-rebinding exposure; it is not a complete guarantee
against hostile infrastructure.

The workflow requests each origin's `robots.txt` using the configured full HTTP
User-Agent before page acquisition. HTTP 200 policies and the documented HTTP
404 allow-all result are cached in memory per origin for that acquisition run.
Explicit policy denial is reported as `skipped / robots_disallow`.

Robots policy remains fail-closed when it is unavailable. Transport failures
are reported as `failed / robots_fetch_error`; non-200/non-404 responses are
`failed / robots_http_error` with the status code; and an invalid UTF-8 HTTP 200
policy is `failed / robots_parse_error`. These controlled failures are also
cached per origin for the run, block every affected article request, and are
never converted into policy disallows. There is no automatic retry.

Policy evaluation uses the leading HTTP product token for group matching. For
example, `ReinaLuxeRecoveryAudit/1.0 (+https://reinaluxe.co/)` sends unchanged
on HTTP requests and matches robots groups as `ReinaLuxeRecoveryAudit`. The
exact product-token groups are selected case-insensitively, duplicate groups
for that token are merged, and `*` is the fallback only when no exact group
matches. Partial token names do not match. The longest Allow/Disallow path wins;
Allow wins equal-length ties. Empty Disallow has no effect, while Sitemap and
unknown directives are not access rules. Matching includes the URL path and,
when present, `?query`; UTF-8 and percent-encoded octets are normalized
deterministically. The workflow does not circumvent robots rules,
authentication, CAPTCHAs, rate limits, or access controls. Robots compliance is
a conservative safeguard, not legal advice.

Requests are synchronous, one at a time, with configurable timeout and delay.
Only HTML is accepted, with a 5 MiB maximum response body.
HTTP 404/410, 429, and 5xx responses receive distinct failure categories.
JavaScript is not executed and cookies are not persisted between runs.

Only content-type, content-length, ETag, Last-Modified, Cache-Control, and
Location response headers may enter metadata or manifests. Authorization,
Cookie, Set-Cookie, credentials, and arbitrary input headers are never stored.
Output paths are confined beneath the acquisition directory and traversal is
rejected. Partial page failures do not delete successful snapshots.

Automated tests use `httpx.MockTransport`; they do not contact ReinaLuxe or any
other public site. A real acquisition always requires a separate owner action.
