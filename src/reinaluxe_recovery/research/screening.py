"""Deterministic source screening, classification, and image registration."""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit

from pydantic import ValidationError

from reinaluxe_recovery.community.normalization import (
    content_hash,
    normalize_text,
    normalize_url,
    stable_id,
)
from reinaluxe_recovery.research.contracts import (
    ImageCandidate,
    ImageSourceCategory,
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
_TRACKING_KEYS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "fbclid",
    "gclid",
    "mc_cid",
    "mc_eid",
}
_REDDIT_POST = re.compile(
    r"^/r/(?P<subreddit>[^/]+)/comments/(?P<post_id>[a-z0-9]+)(?:/.*)?$",
    re.IGNORECASE,
)
_REDDIT_USERNAME = re.compile(r"(?<![\w/])(?:u/|/u/)[A-Za-z0-9_-]+", re.IGNORECASE)


def classify_source_lane(
    url: str, planned_lane: SourceLane, brand_scope: list[str] | None = None
) -> SourceLane:
    """Classify deterministic strong signals, otherwise retain the planned lane."""
    host = (urlsplit(url).hostname or "").casefold().removeprefix("www.")
    path = urlsplit(url).path.casefold()
    if host == "reddit.com" or host.endswith(".reddit.com"):
        return SourceLane.COMMUNITY_REDDIT
    if host in _FORUM_DOMAINS or "forum" in host or "/forum" in path:
        return SourceLane.COMMUNITY_FORUMS
    if host.endswith(_OFFICIAL_SUFFIXES) or _matches_official_brand_domain(
        host, brand_scope or []
    ):
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
    if plan.queries:
        provider.validate_configuration()
    policy_by_lane = {item.source_lane: item for item in plan.source_lane_policies}
    lane_counts: Counter[SourceLane] = Counter()
    sources: list[SourceCandidate] = []
    images: list[ImageCandidate] = []
    exclusions: list[dict[str, Any]] = []
    seen_urls: dict[str, str] = {}
    seen_content: dict[str, str] = {}
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
            candidate, reason = screen_source_candidate(query, raw, policy_by_lane)
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
            content_key = _content_duplicate_key(candidate)
            if content_key and content_key in seen_content:
                exclusions.append(
                    {
                        "query_id": query.query_id,
                        "url": str(candidate.source_url),
                        "reason": "identical_title_snippet_duplicate",
                        "duplicate_of_source_id": seen_content[content_key],
                    }
                )
                continue
            seen_urls[normalized] = candidate.source_id
            if content_key:
                seen_content[content_key] = candidate.source_id
            lane_counts[candidate.source_lane] += 1
            sources.append(candidate)
            for raw_image in raw_images(raw):
                if len(images) >= plan.maximum_image_candidates:
                    break
                image = screen_image_candidate(candidate, raw_image)
                if image is None:
                    continue
                normalized_image = str(image.normalized_image_url or image.image_id)
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


def screen_source_candidate(
    query: ResearchQuery,
    raw: Mapping[str, Any],
    policies: Mapping[SourceLane, SourceLanePolicy],
) -> tuple[SourceCandidate | None, str | None]:
    raw_url = raw.get("url")
    if not isinstance(raw_url, str) or not raw_url.strip():
        return None, "missing_url"
    try:
        normalized = normalize_source_url(raw_url)
    except (ValueError, UnicodeError):
        return None, "invalid_url"
    lane = classify_source_lane(normalized, query.source_lane, query.brand_scope)
    policy = policies.get(lane) or policies.get(query.source_lane)
    host = (urlsplit(normalized).hostname or "").casefold().removeprefix("www.")
    path = urlsplit(normalized).path
    if (
        query.source_lane
        in {
            SourceLane.COMMUNITY_REDDIT,
            SourceLane.COMMUNITY_FORUMS,
            SourceLane.PRIMARY_OFFICIAL,
        }
        and lane is query.source_lane
        and not _has_strict_lane_signal(
            normalized, query.source_lane, query.brand_scope
        )
    ):
        return None, "source_lane_mismatch"
    if lane is SourceLane.COMMUNITY_REDDIT and not _is_reddit_post(normalized):
        return None, "invalid_reddit_url"
    if (
        query.source_lane is SourceLane.COMMUNITY_REDDIT
        and lane is SourceLane.COMMUNITY_REDDIT
        and not _is_reddit_host(host)
    ):
        return None, "non_reddit_url_classified_as_reddit"
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
    for image in raw_images(raw):
        value = image.get("url") if isinstance(image, dict) else image
        if not isinstance(value, str):
            continue
        try:
            images.append(normalize_url(_remove_tracking(value)))
        except ValueError:
            continue
    source_id = stable_id("source", normalized)
    try:
        return (
            SourceCandidate.model_validate(
                {
                    "source_id": source_id,
                    "query_id": query.query_id,
                    "query_family": query.query_family,
                    "provider": str(raw.get("provider") or "zhipu"),
                    "provider_result_id": _optional_text(raw.get("provider_result_id")),
                    "provider_access_classification": raw.get(
                        "provider_access_classification",
                        "provider_returned_snippet",
                    ),
                    "source_url": raw_url,
                    "normalized_url": normalized,
                    "source_lane": lane,
                    "title": _safe_source_text(raw.get("title"), lane),
                    "snippet": _safe_source_text(raw.get("snippet"), lane),
                    "published_at": published_at,
                    "retrieved_at": retrieved_at,
                    "language": _optional_text(raw.get("language")),
                    "domain": host,
                    "has_images": bool(images),
                    "image_urls": images,
                    "provider_rank": _nonnegative_int(raw.get("rank")),
                    "source_cluster_id": stable_id(
                        "source_cluster",
                        _source_cluster_key(host, raw.get("provider_metadata")),
                    ),
                    "metadata": _json_mapping(raw.get("provider_metadata")),
                }
            ),
            None,
        )
    except ValidationError:
        return None, "contract_validation_failed"


def screen_image_candidate(
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
    media_metadata = _json_mapping(raw) if isinstance(raw, dict) else {}
    if not isinstance(url_value, str) or not url_value.strip():
        if not media_metadata:
            return None
        try:
            return ImageCandidate.model_validate(
                {
                    "image_id": stable_id(
                        "image_media",
                        {"source_id": source.source_id, "media": media_metadata},
                    ),
                    "source_id": source.source_id,
                    "query_id": source.query_id,
                    "source_page_url": source.normalized_url,
                    "target_topic": source.query_family,
                    "image_source_category": _image_category(source.source_lane),
                    "expected_visual_evidence": "Provider-returned visual-reference metadata only.",
                    "required_attribution": "Retain source-page attribution and verify rights.",
                    "provider_media_metadata": media_metadata,
                }
            )
        except ValidationError:
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
                "target_topic": source.query_family,
                "image_source_category": _image_category(source.source_lane),
                "expected_visual_evidence": (
                    "Visible shape, proportion, construction, and comparison signals only."
                ),
                "required_attribution": "Retain source-page attribution and verify rights.",
                "duplicate_check_status": "unique",
                "provider_media_metadata": media_metadata,
            }
        )
    except (ValueError, ValidationError):
        return None


def raw_images(raw: Mapping[str, Any]) -> list[Mapping[str, Any] | str]:
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


def normalize_source_url(value: str) -> str:
    """Normalize provider URLs without fetching, including Reddit post permalinks."""
    normalized = normalize_url(_remove_tracking(value))
    parts = urlsplit(normalized)
    host = (parts.hostname or "").casefold().removeprefix("www.")
    if not _is_reddit_host(host):
        return normalized
    match = _REDDIT_POST.match(parts.path)
    if not match:
        return normalized
    subreddit = match.group("subreddit")
    post_id = match.group("post_id").casefold()
    return f"https://reddit.com/r/{subreddit}/comments/{post_id}/"


def _is_reddit_host(host: str) -> bool:
    return host == "reddit.com" or host.endswith(".reddit.com")


def _is_reddit_post(value: str) -> bool:
    parts = urlsplit(value)
    host = (parts.hostname or "").casefold().removeprefix("www.")
    return _is_reddit_host(host) and bool(_REDDIT_POST.match(parts.path))


def _safe_source_text(value: Any, lane: SourceLane) -> str | None:
    text = _optional_text(value)
    if text is None or lane is not SourceLane.COMMUNITY_REDDIT:
        return text
    return _REDDIT_USERNAME.sub("[redacted-user]", text)


def _source_cluster_key(host: str, metadata: Any) -> str:
    values = _json_mapping(metadata)
    return str(
        values.get("seller_source_cluster")
        or values.get("seller")
        or values.get("origin")
        or host
    ).casefold()


def _content_duplicate_key(candidate: SourceCandidate) -> str:
    content = normalize_text(
        " | ".join(value for value in (candidate.title, candidate.snippet) if value)
    ).casefold()
    return content_hash(content) if content else ""


def _image_category(lane: SourceLane) -> ImageSourceCategory:
    return {
        SourceLane.COMMUNITY_REDDIT: ImageSourceCategory.COMMUNITY_IMAGE,
        SourceLane.COMMUNITY_FORUMS: ImageSourceCategory.COMMUNITY_IMAGE,
        SourceLane.PRIMARY_OFFICIAL: ImageSourceCategory.OFFICIAL_REFERENCE,
        SourceLane.EXPERT_EDITORIAL: ImageSourceCategory.EXPERT_REFERENCE,
        SourceLane.COMMERCIAL_OBSERVATION: ImageSourceCategory.COMMERCIAL_LISTING,
        SourceLane.VISUAL_IMAGE: ImageSourceCategory.UNKNOWN_ORIGIN,
    }[lane]


def _has_strict_lane_signal(url: str, lane: SourceLane, brand_scope: list[str]) -> bool:
    host = (urlsplit(url).hostname or "").casefold().removeprefix("www.")
    path = urlsplit(url).path.casefold()
    if lane is SourceLane.COMMUNITY_REDDIT:
        return _is_reddit_post(url)
    if lane is SourceLane.COMMUNITY_FORUMS:
        return host in _FORUM_DOMAINS or "forum" in host or "/forum" in path
    if lane is SourceLane.PRIMARY_OFFICIAL:
        return host.endswith(_OFFICIAL_SUFFIXES) or _matches_official_brand_domain(
            host, brand_scope
        )
    return True


def _matches_official_brand_domain(host: str, brand_scope: list[str]) -> bool:
    compact_host = re.sub(r"[^a-z0-9]", "", host)
    for brand in brand_scope:
        compact_brand = re.sub(r"[^a-z0-9]", "", brand.casefold())
        if compact_brand in {"", "crossbrand"} or len(compact_brand) < 4:
            continue
        if compact_brand in compact_host:
            return True
    return False


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
