import pytest

from reinaluxe_recovery.acquisition.discovery import filter_urls, parse_sitemap
from reinaluxe_recovery.acquisition.exceptions import DiscoveryError, UnsafeTargetError
from reinaluxe_recovery.acquisition.url_normalization import validate_public_url


def test_order_dedup_filters(public_resolver) -> None:
    result = filter_urls(
        ["https://example.com/A#x", "https://example.com/A", "https://example.com/b"],
        frozenset({"example.com"}),
        include_patterns=("*/A",),
        resolver=public_resolver,
    )
    assert result == ["https://example.com/A"]


def test_sitemap_and_index() -> None:
    assert parse_sitemap(
        b"<urlset><url><loc>https://example.com/a</loc></url></urlset>"
    ) == ("urlset", ["https://example.com/a"])
    assert (
        parse_sitemap(
            b"<sitemapindex><sitemap><loc>https://example.com/s.xml</loc></sitemap></sitemapindex>"
        )[0]
        == "sitemapindex"
    )
    with pytest.raises(DiscoveryError):
        parse_sitemap(b"<bad")


@pytest.mark.parametrize(
    "url",
    [
        "ftp://example.com/x",
        "http://localhost/x",
        "http://127.0.0.1/x",
        "http://[::1]/x",
        "http://10.0.0.1/x",
        "http://169.254.1.1/x",
    ],
)
def test_unsafe_targets(url) -> None:
    host = url.split("//")[-1].split("/")[0].strip("[]")
    with pytest.raises(UnsafeTargetError):
        validate_public_url(url, frozenset({host}), lambda _: [host])


def test_disallowed_host(public_resolver) -> None:
    with pytest.raises(UnsafeTargetError):
        validate_public_url(
            "https://other.example/a", frozenset({"example.com"}), public_resolver
        )
