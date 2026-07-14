"""Sequential HTTP fetching with redirect, robots, size, and metadata policy."""

from datetime import UTC, datetime
from time import monotonic
from urllib.parse import urljoin
from urllib.robotparser import RobotFileParser
from uuid import NAMESPACE_URL, uuid5

import httpx

from reinaluxe_recovery.acquisition.contracts import AcquiredPage, AcquisitionStatus
from reinaluxe_recovery.acquisition.url_normalization import (
    Resolver,
    validate_public_url,
)

MAX_RESPONSE_BYTES = 5 * 1024 * 1024
MAX_REDIRECTS = 5
SAFE_RESPONSE_HEADERS = {
    "content-type",
    "content-length",
    "etag",
    "last-modified",
    "cache-control",
    "location",
}


def safe_headers(headers: httpx.Headers) -> dict[str, str]:
    return {
        key.casefold(): value
        for key, value in headers.items()
        if key.casefold() in SAFE_RESPONSE_HEADERS
    }


class SafeFetcher:
    def __init__(
        self,
        client: httpx.Client,
        allowed_hosts: frozenset[str],
        user_agent: str,
        resolver: Resolver,
        timeout: float,
    ) -> None:
        self.client = client
        self.allowed_hosts = allowed_hosts
        self.user_agent = user_agent
        self.resolver = resolver
        self.timeout = timeout
        self._robots: dict[str, RobotFileParser] = {}

    def robots_allows(self, url: str) -> bool:
        parts = httpx.URL(url)
        origin = (
            f"{parts.scheme}://{parts.host}{f':{parts.port}' if parts.port else ''}"
        )
        if origin not in self._robots:
            robots_url = validate_public_url(
                f"{origin}/robots.txt", self.allowed_hosts, self.resolver
            )
            try:
                response = self.client.get(
                    robots_url,
                    headers={"User-Agent": self.user_agent},
                    timeout=self.timeout,
                )
                lines = (
                    response.text.splitlines()
                    if response.status_code == 200
                    else []
                    if response.status_code == 404
                    else ["User-agent: *", "Disallow: /"]
                )
            except httpx.HTTPError:
                lines = ["User-agent: *", "Disallow: /"]
            parser = RobotFileParser()
            parser.set_url(robots_url)
            parser.parse(lines)
            self._robots[origin] = parser
        return self._robots[origin].can_fetch(self.user_agent, url)

    def fetch(self, url: str) -> tuple[AcquiredPage, bytes | None]:
        started = monotonic()
        requested = validate_public_url(url, self.allowed_hosts, self.resolver)
        entry_id = uuid5(NAMESPACE_URL, requested).hex
        if not self.robots_allows(requested):
            return AcquiredPage(
                entry_id=entry_id,
                requested_url=requested,  # type: ignore[arg-type]
                status=AcquisitionStatus.SKIPPED,
                error_type="robots_disallow",
                error_message="robots.txt disallows this URL",
                duration_ms=int((monotonic() - started) * 1000),
            ), None
        current = requested
        chain: list[str] = []
        try:
            for _ in range(MAX_REDIRECTS + 1):
                response = self.client.get(
                    current,
                    headers={"User-Agent": self.user_agent},
                    timeout=self.timeout,
                    follow_redirects=False,
                )
                if response.is_redirect:
                    location = response.headers.get("location")
                    if not location:
                        break
                    current = validate_public_url(
                        urljoin(current, location), self.allowed_hosts, self.resolver
                    )
                    chain.append(current)
                    continue
                fetched_at = datetime.now(UTC)
                headers = safe_headers(response.headers)
                content_type = response.headers.get("content-type")
                if response.status_code >= 400:
                    kind = (
                        "not_found"
                        if response.status_code in {404, 410}
                        else "rate_limited"
                        if response.status_code == 429
                        else "server_error"
                        if response.status_code >= 500
                        else "http_error"
                    )
                    return AcquiredPage(
                        entry_id=entry_id,
                        requested_url=requested,  # type: ignore[arg-type]
                        final_url=current,  # type: ignore[arg-type]
                        fetched_at=fetched_at,
                        status_code=response.status_code,
                        content_type=content_type,
                        response_headers=headers,
                        status=AcquisitionStatus.FAILED,
                        error_type=kind,
                        error_message=f"HTTP {response.status_code}",
                        redirect_chain=tuple(chain),  # type: ignore[arg-type]
                        duration_ms=int((monotonic() - started) * 1000),
                    ), None
                body = response.content
                if len(body) > MAX_RESPONSE_BYTES:
                    raise ValueError("response exceeds maximum byte size")
                if not content_type or "html" not in content_type.casefold():
                    raise ValueError("response is not HTML")
                return AcquiredPage(
                    entry_id=entry_id,
                    requested_url=requested,  # type: ignore[arg-type]
                    final_url=current,  # type: ignore[arg-type]
                    fetched_at=fetched_at,
                    status_code=response.status_code,
                    content_type=content_type,
                    response_headers=headers,
                    status=AcquisitionStatus.FETCHED,
                    redirect_chain=tuple(chain),  # type: ignore[arg-type]
                    duration_ms=int((monotonic() - started) * 1000),
                ), body
            raise ValueError("redirect limit exceeded")
        except httpx.TimeoutException as error:
            kind, message = "timeout", str(error) or "request timed out"
        except (httpx.HTTPError, ValueError) as error:
            kind, message = "fetch_error", str(error)
        return AcquiredPage(
            entry_id=entry_id,
            requested_url=requested,  # type: ignore[arg-type]
            final_url=current,  # type: ignore[arg-type]
            status=AcquisitionStatus.FAILED,
            error_type=kind,
            error_message=message,
            redirect_chain=tuple(chain),  # type: ignore[arg-type]
            duration_ms=int((monotonic() - started) * 1000),
        ), None
