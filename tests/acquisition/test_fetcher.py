import httpx
import pytest

from reinaluxe_recovery.acquisition.contracts import AcquisitionStatus
from reinaluxe_recovery.acquisition.fetcher import MAX_RESPONSE_BYTES, SafeFetcher


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


def test_robots_failure_defaults_to_skip(public_resolver) -> None:
    def handler(request):
        raise httpx.ReadError("unavailable", request=request)

    page, _ = make_fetcher(handler, public_resolver).fetch("https://example.com/a")
    assert page.status is AcquisitionStatus.SKIPPED


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
