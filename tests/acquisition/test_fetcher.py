import httpx
import pytest

from reinaluxe_recovery.acquisition.contracts import AcquisitionStatus
from reinaluxe_recovery.acquisition.fetcher import MAX_RESPONSE_BYTES, SafeFetcher

LIVE_POLICY = """User-agent: *
Allow: /
Disallow: /wp-admin/
Allow: /wp-admin/admin-ajax.php
Disallow: /wp-content/uploads/wpo/wpo-plugins-tables-list.json
Content-signal: search=yes,ai-train=no
Sitemap: https://example.com/sitemap.xml"""


def make_fetcher(handler, public_resolver):
    return SafeFetcher(
        httpx.Client(transport=httpx.MockTransport(handler)),
        frozenset({"example.com"}),
        "OwnerAgent",
        public_resolver,
        1,
    )


def test_html_redirect_and_sanitized_headers(public_resolver) -> None:
    def handler(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nAllow: /", request=request)
        if request.url.path == "/a":
            return httpx.Response(302, headers={"Location": "/b"}, request=request)
        return httpx.Response(
            200,
            content=b"<html>ok</html>",
            headers={
                "Content-Type": "text/html",
                "Set-Cookie": "secret",
                "Authorization": "secret",
            },
            request=request,
        )

    page, body = make_fetcher(handler, public_resolver).fetch("https://example.com/a")
    assert page.status is AcquisitionStatus.FETCHED and body
    assert len(page.redirect_chain) == 1
    assert (
        "set-cookie" not in page.response_headers
        and "authorization" not in page.response_headers
    )


@pytest.mark.parametrize(
    "status,kind",
    [
        (404, "not_found"),
        (410, "not_found"),
        (429, "rate_limited"),
        (503, "server_error"),
    ],
)
def test_http_failures(status, kind, public_resolver) -> None:
    def handler(request):
        return (
            httpx.Response(200, text="Allow: /", request=request)
            if request.url.path == "/robots.txt"
            else httpx.Response(status, request=request)
        )

    page, _ = make_fetcher(handler, public_resolver).fetch("https://example.com/a")
    assert page.error_type == kind


def test_robots_disallow(public_resolver) -> None:
    def handler(request):
        return httpx.Response(
            200, text="User-agent: *\nDisallow: /private", request=request
        )

    page, _ = make_fetcher(handler, public_resolver).fetch(
        "https://example.com/private"
    )
    assert page.status is AcquisitionStatus.SKIPPED


@pytest.mark.parametrize(
    "error_type",
    [
        httpx.ReadError,
        httpx.ConnectError,
        httpx.ReadTimeout,
        httpx.ConnectTimeout,
        httpx.TransportError,
    ],
)
def test_robots_transport_failure_is_failed_and_cached(
    error_type, public_resolver
) -> None:
    calls = []

    def handler(request):
        calls.append(request)
        raise error_type(
            "Authorization=secret-auth Cookie=secret-cookie "
            "Set-Cookie=secret-set-cookie at "
            "https://user:password@example.com/robots.txt",
            request=request,
        )

    fetcher = make_fetcher(handler, public_resolver)
    first, _ = fetcher.fetch("https://example.com/a?authorization=secret")
    second, _ = fetcher.fetch("https://example.com/b")

    assert first.status is AcquisitionStatus.FAILED
    assert second.status is AcquisitionStatus.FAILED
    assert first.error_type == second.error_type == "robots_fetch_error"
    assert first.error_type != "robots_disallow"
    diagnostic = first.error_message or ""
    for sensitive in (
        "secret-auth",
        "secret-cookie",
        "secret-set-cookie",
        "user",
        "password",
    ):
        assert sensitive not in diagnostic
    assert len(calls) == 1
    assert calls[0].url.path == "/robots.txt"


@pytest.mark.parametrize("status", [403, 429, 500])
def test_robots_http_failure_is_failed_and_cached(status, public_resolver) -> None:
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(status, request=request)

    fetcher = make_fetcher(handler, public_resolver)
    first, _ = fetcher.fetch("https://example.com/a")
    second, _ = fetcher.fetch("https://example.com/b")

    assert first.status is AcquisitionStatus.FAILED
    assert second.status is AcquisitionStatus.FAILED
    assert first.error_type == second.error_type == "robots_http_error"
    assert first.status_code == second.status_code == status
    assert len(calls) == 1


def test_robots_parse_failure_is_failed(public_resolver) -> None:
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200, content=b"\xff", request=request)

    fetcher = make_fetcher(handler, public_resolver)
    page, _ = fetcher.fetch("https://example.com/a")
    inherited, _ = fetcher.fetch("https://example.com/b")

    assert page.status is AcquisitionStatus.FAILED
    assert inherited.status is AcquisitionStatus.FAILED
    assert page.error_type == inherited.error_type == "robots_parse_error"
    assert len(calls) == 1


def test_robots_404_allows_page_fetch(public_resolver) -> None:
    calls = []

    def handler(request):
        calls.append(request.url.path)
        if request.url.path == "/robots.txt":
            return httpx.Response(404, request=request)
        return httpx.Response(
            200,
            content=b"<html>ok</html>",
            headers={"Content-Type": "text/html"},
            request=request,
        )

    page, body = make_fetcher(handler, public_resolver).fetch("https://example.com/a")

    assert page.status is AcquisitionStatus.FETCHED
    assert body == b"<html>ok</html>"
    assert calls == ["/robots.txt", "/a"]


def test_full_user_agent_is_sent_and_product_token_matches(public_resolver) -> None:
    seen_user_agents = []

    def handler(request):
        seen_user_agents.append(request.headers["User-Agent"])
        if request.url.path == "/robots.txt":
            return httpx.Response(
                200,
                text=(
                    "User-agent: ReinaLuxeRecoveryAudit\n"
                    "Disallow: /blocked\n"
                    "User-agent: *\n"
                    "Allow: /"
                ),
                request=request,
            )
        return httpx.Response(500, request=request)

    fetcher = SafeFetcher(
        httpx.Client(transport=httpx.MockTransport(handler)),
        frozenset({"example.com"}),
        "ReinaLuxeRecoveryAudit/1.0 (+https://reinaluxe.co/)",
        public_resolver,
        1,
    )
    page, _ = fetcher.fetch("https://example.com/blocked")

    assert page.status is AcquisitionStatus.SKIPPED
    assert page.error_type == "robots_disallow"
    assert seen_user_agents == ["ReinaLuxeRecoveryAudit/1.0 (+https://reinaluxe.co/)"]


@pytest.mark.parametrize(
    "path,expected_status",
    [
        ("/", AcquisitionStatus.FETCHED),
        ("/best-hermes-replica-bags-guide/", AcquisitionStatus.FETCHED),
        (
            "/aaa-replica-reviews/best-celine-replica-bags-2025/",
            AcquisitionStatus.FETCHED,
        ),
        ("/wp-admin/", AcquisitionStatus.SKIPPED),
        ("/wp-admin/edit.php", AcquisitionStatus.SKIPPED),
        ("/wp-admin/admin-ajax.php", AcquisitionStatus.FETCHED),
        (
            "/wp-content/uploads/wpo/wpo-plugins-tables-list.json",
            AcquisitionStatus.SKIPPED,
        ),
    ],
)
def test_complete_live_policy_controls_article_fetch(
    path, expected_status, public_resolver
) -> None:
    calls = []

    def handler(request):
        calls.append(request.url.path)
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text=LIVE_POLICY, request=request)
        return httpx.Response(
            200,
            content=b"<html>ok</html>",
            headers={"Content-Type": "text/html"},
            request=request,
        )

    page, body = make_fetcher(handler, public_resolver).fetch(
        f"https://example.com{path}"
    )

    assert page.status is expected_status
    if expected_status is AcquisitionStatus.SKIPPED:
        assert page.error_type == "robots_disallow"
        assert calls == ["/robots.txt"]
        assert body is None
    else:
        assert calls == ["/robots.txt", path]
        assert body == b"<html>ok</html>"


@pytest.mark.parametrize("oversize", [False, True])
def test_rejects_non_html_and_oversize(oversize, public_resolver) -> None:
    content = b"x" * (MAX_RESPONSE_BYTES + 1) if oversize else b"x"
    content_type = "text/html" if oversize else "application/pdf"

    def handler(request):
        return (
            httpx.Response(200, text="Allow: /", request=request)
            if request.url.path == "/robots.txt"
            else httpx.Response(
                200,
                content=content,
                headers={"Content-Type": content_type},
                request=request,
            )
        )

    page, _ = make_fetcher(handler, public_resolver).fetch("https://example.com/a")
    assert page.status is AcquisitionStatus.FAILED


def test_timeout(public_resolver) -> None:
    def handler(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="Allow: /", request=request)
        raise httpx.ReadTimeout("late", request=request)

    page, _ = make_fetcher(handler, public_resolver).fetch("https://example.com/a")
    assert page.error_type == "timeout"
