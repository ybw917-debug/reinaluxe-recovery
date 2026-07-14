"""Deterministic explicit-list and sitemap discovery."""

import fnmatch
from pathlib import Path
from xml.etree import ElementTree

from reinaluxe_recovery.acquisition.exceptions import (
    DiscoveryError,
    NoEligibleUrlsError,
)
from reinaluxe_recovery.acquisition.url_normalization import (
    Resolver,
    validate_public_url,
)

MAX_SITEMAP_DEPTH = 3
MAX_DISCOVERED_URLS = 10_000


def load_url_list(path: Path) -> list[str]:
    try:
        text = path.read_text(encoding="utf-8-sig")
    except OSError as error:
        raise DiscoveryError(f"could not read URL list: {error}") from error
    if path.suffix.casefold() == ".json":
        import json

        try:
            values = json.loads(text)
        except ValueError as error:
            raise DiscoveryError("URL list JSON is malformed") from error
        if not isinstance(values, list) or not all(isinstance(v, str) for v in values):
            raise DiscoveryError("URL list JSON must be an array of strings")
        return values
    return [
        line.strip()
        for line in text.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]


def filter_urls(
    urls: list[str],
    allowed_hosts: frozenset[str],
    *,
    include_patterns: tuple[str, ...] | None = None,
    exclude_patterns: tuple[str, ...] | None = None,
    maximum_urls: int | None = None,
    resolver: Resolver,
) -> list[str]:
    found: list[str] = []
    seen: set[str] = set()
    for raw in urls:
        url = validate_public_url(raw, allowed_hosts, resolver)
        if url in seen:
            continue
        if include_patterns and not any(
            fnmatch.fnmatchcase(url, pattern) for pattern in include_patterns
        ):
            continue
        if exclude_patterns and any(
            fnmatch.fnmatchcase(url, pattern) for pattern in exclude_patterns
        ):
            continue
        seen.add(url)
        found.append(url)
        if maximum_urls is not None and len(found) >= maximum_urls:
            break
    if not found:
        raise NoEligibleUrlsError("no eligible URLs after filtering")
    return found


def parse_sitemap(xml: bytes) -> tuple[str, list[str]]:
    try:
        root = ElementTree.fromstring(xml)
    except ElementTree.ParseError as error:
        raise DiscoveryError("malformed sitemap XML") from error
    kind = root.tag.rsplit("}", 1)[-1]
    if kind not in {"urlset", "sitemapindex"}:
        raise DiscoveryError("unsupported sitemap root")
    locations = [
        (node.text or "").strip()
        for node in root.iter()
        if node.tag.rsplit("}", 1)[-1] == "loc" and (node.text or "").strip()
    ]
    return kind, locations
