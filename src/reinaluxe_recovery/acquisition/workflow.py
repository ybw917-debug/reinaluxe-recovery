"""Sequential acquisition orchestration; separate from import and persistence."""

from collections.abc import Callable
from datetime import UTC, datetime
from time import sleep

import httpx

from reinaluxe_recovery.acquisition.contracts import (
    AcquisitionRequest,
    AcquisitionResult,
    AcquisitionSourceType,
)
from reinaluxe_recovery.acquisition.discovery import (
    MAX_DISCOVERED_URLS,
    MAX_SITEMAP_DEPTH,
    filter_urls,
    parse_sitemap,
)
from reinaluxe_recovery.acquisition.exceptions import (
    DiscoveryError,
    NoEligibleUrlsError,
)
from reinaluxe_recovery.acquisition.fetcher import SafeFetcher
from reinaluxe_recovery.acquisition.snapshots import (
    atomic_write,
    build_manifest,
    persist_page,
    write_manifest,
)
from reinaluxe_recovery.acquisition.url_normalization import (
    Resolver,
    system_resolver,
    validate_public_url,
)


class AcquisitionWorkflow:
    def __init__(
        self,
        *,
        transport: httpx.BaseTransport | None = None,
        resolver: Resolver = system_resolver,
        sleeper: Callable[[float], None] = sleep,
    ) -> None:
        self.transport = transport
        self.resolver = resolver
        self.sleeper = sleeper

    def _sitemap_urls(
        self, request: AcquisitionRequest, client: httpx.Client
    ) -> list[str]:
        pages: list[str] = []
        seen: set[str] = set()

        def visit(url: str, depth: int) -> None:
            if depth > MAX_SITEMAP_DEPTH:
                raise DiscoveryError("sitemap recursion depth exceeded")
            normalized = validate_public_url(url, request.allowed_hosts, self.resolver)
            if normalized in seen:
                return
            seen.add(normalized)
            try:
                response = client.get(
                    normalized,
                    headers={"User-Agent": request.user_agent},
                    timeout=request.request_timeout_seconds,
                )
            except httpx.HTTPError as error:
                raise DiscoveryError(f"sitemap request failed: {error}") from error
            if response.status_code != 200:
                raise DiscoveryError(f"sitemap returned HTTP {response.status_code}")
            kind, locations = parse_sitemap(response.content)
            if kind == "sitemapindex":
                for child in locations:
                    visit(child, depth + 1)
            else:
                pages.extend(locations)
            if len(pages) > MAX_DISCOVERED_URLS:
                raise DiscoveryError("sitemap URL limit exceeded")

        for item in request.sitemap_urls or ():
            visit(str(item), 0)
        return pages

    def run(self, request: AcquisitionRequest) -> AcquisitionResult:
        started = datetime.now(UTC)
        root = request.output_directory.expanduser().resolve()
        if root.exists() and any(root.iterdir()) and not request.overwrite_existing:
            raise DiscoveryError(f"output directory is not empty: {root}")
        root.mkdir(parents=True, exist_ok=True)
        atomic_write(
            root / "acquisition-request.json",
            f"{request.model_dump_json(indent=2)}\n".encode(),
            overwrite=request.overwrite_existing,
        )
        with httpx.Client(transport=self.transport, follow_redirects=False) as client:
            raw = (
                [str(item) for item in request.explicit_urls or ()]
                if request.source_type is AcquisitionSourceType.URL_LIST
                else self._sitemap_urls(request, client)
            )
            urls = filter_urls(
                raw,
                request.allowed_hosts,
                include_patterns=request.include_patterns,
                exclude_patterns=request.exclude_patterns,
                maximum_urls=request.maximum_urls,
                resolver=self.resolver,
            )
            fetcher = SafeFetcher(
                client,
                request.allowed_hosts,
                str(request.user_agent),
                self.resolver,
                request.request_timeout_seconds,
            )
            pages = []
            for index, url in enumerate(urls):
                if index and request.delay_between_requests_seconds:
                    self.sleeper(request.delay_between_requests_seconds)
                page, body = fetcher.fetch(url)
                if body is not None:
                    page = persist_page(
                        root, page, body, overwrite=request.overwrite_existing
                    )
                pages.append(page)
        successful = [p for p in pages if p.snapshot_path is not None]
        if not successful and not pages:
            raise NoEligibleUrlsError("no eligible URLs")
        manifest_path = None
        if successful:
            manifest_path = write_manifest(
                root,
                build_manifest(request, pages),
                overwrite=request.overwrite_existing,
            )
        result = AcquisitionResult(
            acquisition_id=str(request.acquisition_id),
            started_at=started,
            completed_at=datetime.now(UTC),
            source_type=request.source_type,
            output_directory=root,
            pages=tuple(pages),
            manifest_path=manifest_path,
        )
        atomic_write(
            root / "acquisition-result.json",
            f"{result.model_dump_json(indent=2)}\n".encode(),
            overwrite=request.overwrite_existing,
        )
        return result
