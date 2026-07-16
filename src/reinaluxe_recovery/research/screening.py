"""Deterministic source screening, classification, and image registration."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit

from pydantic import ValidationError

from reinaluxe_recovery.community.normalization import (
    content_hash,
    normalize_url,
    stable_id,
)
from reinaluxe_recovery.research.contracts import (
    ImageCandidate,
    ResearchPlan,
    ResearchQuery,
    SearchRun,
    SourceCandidate,
    SourceLane,
    SourceLanePolicy,
)
from reinaluxe_recovery.research.errors import ResearchArtifactError
from reinaluxe_recovery.research.providers.base import ResearchSearchProvider

_FORUM_DOMAINS = {
    "purseforum.com",
    "forum.purseblog.com",
    "styleforum.net",
    "leatherworker.net",
}
_OFFICIAL_SUFFIXES = (".gov", ".edu", ".int")
_TRACKING_KEYS = {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content"}


def classify_source_lane(url: str, planned_lane: SourceLane) -> SourceLane:
    """Classify deterministic strong signals, otherwise retain the planned lane."""
    host = (urlsplit(url).hostname or "").casefold().removeprefix("www.")
    path = urlsplit(url).path.casefold()
    if host == "reddit.com" or host.endswith(".reddit.com"):
        return SourceLane.COMMUNITY_REDDIT
    if host in _FORUM_DOMAINS or "forum" in host or "/forum" in path:
        return SourceLane.COMMUNITY_FORUMS
    if host.endswith(_OFFICIAL_SUFFIXES):
        return SourceLane.PRIMARY_OFFICIAL
    return planned_lane


def discover_sources(
    plan: ResearchPlan,
    provider: ResearchSearchProvider,
) -> SearchRun:
    """Execute bounded queries and accept only URLs present in provider responses."""
    if provider.provider_name.casefold() != plan.provider.casefold():
        raise ResearchArtifactError(
            f"plan provider {plan.provider!r} does not match {provider.provider_name!r}"
        )
    provider.validate_configuration()
    policy_by_lane = {item.source_lane: item for item in plan.source_lane_policies}
    lane_counts: Counter[SourceLane] = Counter()
    sources: list[SourceCandidate] = []
    images: list[ImageCandidate] = []
    exclusions: list[dict[str, Any]] = []
    seen_urls: dict[str, str] = {}
    seen_images: dict[str, str] = {}
    executed: list[str] = []
    for query in plan.queries[: plan.maximum_search_calls]:
        response = provider.execute_query(query)
        executed.append(query.query_id)
        raw_results = provider.normalize_results(query, response)
        for provider_result in raw_results:
            raw = dict(provider_result)
            raw.setdefault("provider", provider.provider_name)
            if len(sources) >= plan.maximum_sources:
                exclusions.append(_exclusion(query, raw, "maximum_sources_reached"))
                continue
            candidate, reason = _screen_source(query, raw, policy_by_lane)
            if candidate is None:
                exclusions.append(_exclusion(query, raw, reason or "invalid_source"))
                continue
            policy = policy_by_lane.get(candidate.source_lane)
            if policy and lane_counts[candidate.source_lane] >= policy.source_quota:
                exclusions.append(_exclusion(query, raw, "source_lane_quota_reached"))
                continue
            normalized = str(candidate.normalized_url)
            if normalized in seen_urls:
                exclusions.append(
                    {
                        "query_id": query.query_id,
                        "url": str(candidate.source_url),
                        "reason": "exact_duplicate_url",
                        "duplicate_of_source_id": seen_urls[normalized],
                    }
                )
                continue
            seen_urls[normalized] = candidate.source_id
            lane_counts[candidate.source_lane] += 1
            sources.append(candidate)
            for raw_image in _raw_images(raw):
                if len(images) >= plan.maximum_image_candidates:
                    break
                image = _screen_image(candidate, raw_image)
                if image is None:
                    continue
                normalized_image = str(image.normalized_image_url)
                if normalized_image in seen_images:
                    continue
                seen_images[normalized_image] = image.image_id
                images.append(image)
    run_base = {
        "search_run_id": stable_id(
            "run", {"research_id": plan.research_id, "plan_hash": plan.plan_hash}
        ),
        "research_id": plan.research_id,
        "plan_hash": plan.plan_hash,
        "provider": provider.provider_name,
        "query_ids": executed,
        "source_candidates": sorted(sources, key=lambda item: item.source_id),
        "image_candidates": sorted(images, key=lambda item: item.image_id),
        "exclusions": sorted(
            exclusions,
            key=lambda item: (
                str(item.get("query_id", "")),
                str(item.get("url", "")),
                str(item.get("reason", "")),
            ),
        ),
        "usage": dict(provider.report_usage()),
    }
    draft = SearchRun.model_validate(run_base)
    run_hash = content_hash(draft.model_dump(mode="json", exclude={"run_hash"}))
    return draft.model_copy(update={"run_hash": run_hash})


def _screen_source(
    query: ResearchQuery,
    raw: Mapping[str, Any],
    policies: Mapping[SourceLane, SourceLanePolicy],
) -> tuple[SourceCandidate | None, str | None]:
    raw_url = raw.get("url")
    if not isinstance(raw_url, str) or not raw_url.strip():
        return None, "missing_url"
    try:
        normalized = normalize_url(_remove_tracking(raw_url))
    except (ValueError, UnicodeError):
        return None, "invalid_url"
    lane = classify_source_lane(normalized, query.source_lane)
    policy = policies.get(lane) or policies.get(query.source_lane)
    host = (urlsplit(normalized).hostname or "").casefold().removeprefix("www.")
    path = urlsplit(normalized).path
    if policy is not None:
        if _domain_matches(host, policy.excluded_domains):
            return None, "excluded_domain"
        if policy.allowed_domains and not _domain_matches(host, policy.allowed_domains):
            return None, "domain_not_allowed"
        if policy.path_requirements and not any(
            value in path for value in policy.path_requirements
        ):
            return None, "path_requirement_not_met"
    published_at = _parse_datetime(raw.get("published_at"))
    retrieved_at = _parse_datetime(raw.get("retrieved_at"))
    images = []
    for image in _raw_images(raw):
        value = image.get("url") if isinstance(image, dict) else image
        if not isinstance(value, str):
            continue
        try:
            images.append(normalize_url(value))
        except ValueError:
            continue
    source_id = stable_id("source", normalized)
    try:
        return (
            SourceCandidate.model_validate(
                {
                    "source_id": source_id,
                    "query_id": query.query_id,
                    "provider": str(raw.get("provider") or "zhipu"),
                    "source_url": raw_url,
                    "normalized_url": normalized,
                    "source_lane": lane,
                    "title": _optional_text(raw.get("title")),
                    "snippet": _optional_text(raw.get("snippet")),
                    "published_at": published_at,
                    "retrieved_at": retrieved_at,
                    "language": _optional_text(raw.get("language")),
                    "domain": host,
                    "has_images": bool(images),
                    "image_urls": images,
                    "provider_rank": _nonnegative_int(raw.get("rank")),
                    "metadata": _json_mapping(raw.get("provider_metadata")),
                }
            ),
            None,
        )
    except ValidationError:
        return None, "contract_validation_failed"


def _screen_image(
    source: SourceCandidate, raw: Mapping[str, Any] | str
) -> ImageCandidate | None:
    url_value: Any
    if isinstance(raw, str):
        url_value = raw
        alt = caption = None
    else:
        url_value = raw.get("url") or raw.get("image_url")
        alt = _optional_text(raw.get("alt") or raw.get("alt_text"))
        caption = _optional_text(raw.get("caption"))
    if not isinstance(url_value, str) or not url_value.strip():
        return None
    try:
        normalized = normalize_url(_remove_tracking(url_value))
        return ImageCandidate.model_validate(
            {
                "image_id": stable_id("image", normalized),
                "source_id": source.source_id,
                "query_id": source.query_id,
                "image_url": url_value,
                "normalized_image_url": normalized,
                "source_page_url": source.normalized_url,
                "alt_text": alt,
                "caption": caption,
            }
        )
    except (ValueError, ValidationError):
        return None


def _raw_images(raw: Mapping[str, Any]) -> list[Mapping[str, Any] | str]:
    value = raw.get("images") or raw.get("image_urls") or []
    if isinstance(value, str):
        return [value]
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, (str, dict))]


def _parse_datetime(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        prepared = value.strip().replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(prepared)
        except ValueError:
            try:
                parsed = datetime.fromisoformat(prepared[:10]).replace(tzinfo=UTC)
            except ValueError:
                return None
    else:
        return None
    return (
        parsed
        if parsed.tzinfo and parsed.utcoffset() is not None
        else parsed.replace(tzinfo=UTC)
    )


def _remove_tracking(value: str) -> str:
    from urllib.parse import parse_qsl, urlencode, urlunsplit

    parts = urlsplit(value.strip())
    query = urlencode(
        [
            (key, item)
            for key, item in parse_qsl(parts.query, keep_blank_values=True)
            if key.casefold() not in _TRACKING_KEYS
        ]
    )
    return urlunsplit((parts.scheme, parts.netloc, parts.path, query, ""))


def _domain_matches(host: str, configured: list[str]) -> bool:
    return any(
        host == value.casefold() or host.endswith(f".{value.casefold()}")
        for value in configured
    )


def _optional_text(value: Any) -> str | None:
    return str(value).strip() if value is not None and str(value).strip() else None


def _nonnegative_int(value: Any) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None


def _json_mapping(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    return {str(key): item for key, item in value.items() if _is_json(item)}


def _is_json(value: Any) -> bool:
    if value is None or isinstance(value, (str, int, float, bool)):
        return True
    if isinstance(value, list):
        return all(_is_json(item) for item in value)
    if isinstance(value, dict):
        return all(
            isinstance(key, str) and _is_json(item) for key, item in value.items()
        )
    return False


def _exclusion(
    query: ResearchQuery, raw: Mapping[str, Any], reason: str
) -> dict[str, Any]:
    return {
        "query_id": query.query_id,
        "url": str(raw.get("url") or ""),
        "reason": reason,
    }


def _json_payload(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, dict):
        return {key: _json_payload(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_payload(item) for item in value]
    return value
