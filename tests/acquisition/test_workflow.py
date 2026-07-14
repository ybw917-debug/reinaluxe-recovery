from datetime import UTC, datetime

import httpx

from reinaluxe_recovery.acquisition import (
    AcquisitionRequest,
    AcquisitionSourceType,
    AcquisitionWorkflow,
)
from reinaluxe_recovery.acquisition.contracts import AcquisitionStatus
from reinaluxe_recovery.batch import BatchImportOptions, BatchImportWorkflow
from reinaluxe_recovery.batch.loader import load_batch_manifest


def test_mocked_multi_page_workflow(tmp_path, public_resolver) -> None:
    calls = []

    def handler(request):
        calls.append(str(request.url))
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nAllow: /", request=request)
        return httpx.Response(
            200,
            content=f"<html><head><title>{request.url.path}</title></head><body><article><h1>{request.url.path}</h1><p>Safe offline fixture paragraph for acquisition smoke validation.</p></article></body></html>".encode(),
            headers={"Content-Type": "text/html"},
            request=request,
        )

    request = AcquisitionRequest(
        acquisition_id="mock",
        created_at=datetime.now(UTC),
        source_type=AcquisitionSourceType.URL_LIST,
        explicit_urls=("https://example.com/a", "https://example.com/b"),
        allowed_hosts=frozenset({"example.com"}),
        output_directory=tmp_path,
        user_agent="Owner",
        delay_between_requests_seconds=0,
    )
    result = AcquisitionWorkflow(
        transport=httpx.MockTransport(handler), resolver=public_resolver
    ).run(request)
    assert result.fetched_count == 2 and result.manifest_path
    assert len(load_batch_manifest(result.manifest_path).entries) == 2
    dry_run = BatchImportWorkflow().run(
        result.manifest_path, options=BatchImportOptions(dry_run=True)
    )
    assert dry_run.attempted_entries == 2
    assert not list(tmp_path.glob("*.db"))


def test_mocked_sitemap_index_workflow(tmp_path, public_resolver) -> None:
    def handler(request):
        if request.url.path == "/index.xml":
            return httpx.Response(
                200,
                text="<sitemapindex><sitemap><loc>https://example.com/pages.xml</loc></sitemap></sitemapindex>",
                request=request,
            )
        if request.url.path == "/pages.xml":
            return httpx.Response(
                200,
                text="<urlset><url><loc>https://example.com/a</loc></url></urlset>",
                request=request,
            )
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nAllow: /", request=request)
        return httpx.Response(
            200,
            content=b"<html>page</html>",
            headers={"Content-Type": "text/html"},
            request=request,
        )

    request = AcquisitionRequest(
        acquisition_id="map",
        created_at=datetime.now(UTC),
        source_type=AcquisitionSourceType.SITEMAP,
        sitemap_urls=("https://example.com/index.xml",),
        allowed_hosts=frozenset({"example.com"}),
        output_directory=tmp_path,
        user_agent="Owner",
        delay_between_requests_seconds=0,
    )
    result = AcquisitionWorkflow(
        transport=httpx.MockTransport(handler), resolver=public_resolver
    ).run(request)
    assert result.fetched_count == 1


def test_robots_transport_failure_counts_as_failed(tmp_path, public_resolver) -> None:
    calls = []

    def handler(request):
        calls.append(request)
        raise httpx.ReadError("unavailable", request=request)

    request = AcquisitionRequest(
        acquisition_id="robots-failure",
        created_at=datetime.now(UTC),
        source_type=AcquisitionSourceType.URL_LIST,
        explicit_urls=("https://example.com/a", "https://example.com/b"),
        allowed_hosts=frozenset({"example.com"}),
        output_directory=tmp_path,
        user_agent="Owner",
        delay_between_requests_seconds=0,
    )
    result = AcquisitionWorkflow(
        transport=httpx.MockTransport(handler), resolver=public_resolver
    ).run(request)

    assert result.failed_count == 2
    assert result.skipped_count == 0
    assert result.attempted_count == 2
    assert all(page.status is AcquisitionStatus.FAILED for page in result.pages)
    assert len(calls) == 1


def test_robots_disallow_counts_as_skipped(tmp_path, public_resolver) -> None:
    def handler(request):
        return httpx.Response(
            200, text="User-agent: *\nDisallow: /private", request=request
        )

    request = AcquisitionRequest(
        acquisition_id="robots-disallow",
        created_at=datetime.now(UTC),
        source_type=AcquisitionSourceType.URL_LIST,
        explicit_urls=("https://example.com/private",),
        allowed_hosts=frozenset({"example.com"}),
        output_directory=tmp_path,
        user_agent="Owner",
        delay_between_requests_seconds=0,
    )
    result = AcquisitionWorkflow(
        transport=httpx.MockTransport(handler), resolver=public_resolver
    ).run(request)

    assert result.failed_count == 0
    assert result.skipped_count == 1
    assert result.attempted_count == 0
    assert result.pages[0].error_type == "robots_disallow"
