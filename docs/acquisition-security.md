# Acquisition Security Policy

Only absolute HTTP(S) URLs on explicit allowed hosts are eligible. Core logic
does not hard-code production hosts. Userinfo credentials are rejected. Before
each request and redirect, DNS results are checked; any localhost, loopback,
private, reserved, link-local, or otherwise non-global address rejects the
target. Redirects are limited to five and must remain on an allowed public host.
This reduces SSRF and DNS-rebinding exposure; it is not a complete guarantee
against hostile infrastructure.

The workflow requests each host's `robots.txt` using the configured User-Agent
before page acquisition and skips disallowed paths. It does not circumvent
robots rules, authentication, CAPTCHAs, rate limits, or access controls. Robots
compliance is a conservative safeguard, not legal advice.

Requests are synchronous, one at a time, with configurable timeout and delay.
There is no retry. Only HTML is accepted, with a 5 MiB maximum response body.
HTTP 404/410, 429, and 5xx responses receive distinct failure categories.
JavaScript is not executed and cookies are not persisted between runs.

Only content-type, content-length, ETag, Last-Modified, Cache-Control, and
Location response headers may enter metadata or manifests. Authorization,
Cookie, Set-Cookie, credentials, and arbitrary input headers are never stored.
Output paths are confined beneath the acquisition directory and traversal is
rejected. Partial page failures do not delete successful snapshots.

Automated tests use `httpx.MockTransport`; they do not contact ReinaLuxe or any
other public site. A real acquisition always requires a separate owner action.
