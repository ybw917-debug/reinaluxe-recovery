"""Deterministic source screening, classification, and image registration."""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
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
    VisualPageCandidate,
)
from reinaluxe_recovery.research.errors import ResearchArtifactError
from reinaluxe_recovery.research.providers.base import ResearchSearchProvider
from reinaluxe_recovery.research.query_integrity import (
    canonical_query_family,
    evaluate_query_quality,
    topic_relevance_hits,
)

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
_COMMERCIAL_HOST_MARKERS = (
    "aliexpress.",
    "alibaba.",
    "amazon.",
    "dhgate.",
    "ebay.",
    "etsy.",
    "taobao.",
)
_COMMERCIAL_TEXT_MARKERS = (
    "add to cart",
    "buy now",
    "shop now",
    "whatsapp",
    "contact seller",
    "price usd",
    "replica bags for sale",
    "product catalog",
)
_CORRUPTION_MARKERS = (
    "\ufffd",
    "ã€",
    "â€",
    "â€™",
    "â€œ",
    "â€�",
    "ï»¿",
    "馃",
    "鈥",
    "锟",
    "銆",
)
_PSP_GAMING_MARKERS = (
    "playstation portable",
    "sony psp",
    "psp game",
    "psp gaming",
    "handheld console",
    "video game console",
)
_MULTIPART_PUBLIC_SUFFIXES = {
    "co.jp",
    "co.uk",
    "com.au",
    "com.cn",
    "com.hk",
    "com.sg",
    "com.tw",
}


@dataclass(frozen=True)
class SourceLaneClassification:
    lane: SourceLane
    rule: str
    confidence: float


def classify_source_lane(
    url: str, planned_lane: SourceLane, brand_scope: list[str] | None = None
) -> SourceLane:
    """Return the actual lane without using the requested lane as a fallback."""
    del planned_lane
    return classify_source_lane_details(url, brand_scope).lane


def classify_source_lane_details(
    url: str,
    brand_scope: list[str] | None = None,
    content: str = "",
) -> SourceLaneClassification:
    """Classify a source from URL evidence independently of query intent."""
    host = (urlsplit(url).hostname or "").casefold().removeprefix("www.")
    path = urlsplit(url).path.casefold()
    if host == "reddit.com" or host.endswith(".reddit.com"):
        return SourceLaneClassification(SourceLane.COMMUNITY_REDDIT, "reddit_host", 1.0)
    if host in _FORUM_DOMAINS or "forum" in host or "/forum" in path:
        return SourceLaneClassification(
            SourceLane.COMMUNITY_FORUMS, "public_forum_url_signal", 0.98
        )
    if host.endswith(_OFFICIAL_SUFFIXES) or _matches_official_brand_domain(
        host, brand_scope or []
    ):
        return SourceLaneClassification(
            SourceLane.PRIMARY_OFFICIAL, "official_domain_signal", 0.98
        )
    if any(marker in host for marker in _COMMERCIAL_HOST_MARKERS) or any(
        marker in path for marker in ("/product/", "/products/", "/listing/")
    ):
        return SourceLaneClassification(
            SourceLane.COMMERCIAL_OBSERVATION, "commercial_url_signal", 0.9
        )
    if path.casefold().endswith((".jpg", ".jpeg", ".png", ".webp", ".gif")):
        return SourceLaneClassification(
            SourceLane.VISUAL_IMAGE, "direct_image_url_signal", 0.95
        )
    normalized_content = normalize_text(content).casefold()
    if any(marker in normalized_content for marker in _COMMERCIAL_TEXT_MARKERS):
        return SourceLaneClassification(
            SourceLane.COMMERCIAL_OBSERVATION,
            "commercial_content_signal",
            0.88,
        )
    return SourceLaneClassification(
        SourceLane.EXPERT_EDITORIAL, "broad_web_editorial_default", 0.55
    )


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
    visual_pages: list[VisualPageCandidate] = []
    exclusions: list[dict[str, Any]] = []
    seen_urls: dict[str, str] = {}
    seen_content: dict[str, str] = {}
    seen_images: dict[str, str] = {}
    executed: list[str] = []
    for query in plan.queries[: plan.maximum_search_calls]:
        quality = evaluate_query_quality(query, plan.queries)
        if not (quality.passed and quality.retrieval_quality_passed):
            exclusions.append(
                {
                    "query_id": query.query_id,
                    "url": "",
                    "reason": "query_quality_failed",
                    "failure_reasons": quality.failure_reasons,
                }
            )
            continue
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
                image, visual_page = qualify_visual_candidate(candidate, raw_image)
                if image is not None:
                    normalized_image = str(
                        image.normalized_image_url or image.image_locator
                    )
                    if normalized_image in seen_images:
                        continue
                    seen_images[normalized_image] = image.image_id
                    images.append(image)
                elif visual_page is not None:
                    visual_pages.append(visual_page)
    run_base = {
        "search_run_id": stable_id(
            "run", {"research_id": plan.research_id, "plan_hash": plan.plan_hash}
        ),
        "research_id": plan.research_id,
        "plan_hash": plan.plan_hash,
        "provider": provider.provider_name,
        "query_ids": executed,
        "queries": [query for query in plan.queries if query.query_id in set(executed)],
        "source_candidates": sorted(sources, key=lambda item: item.source_id),
        "image_candidates": sorted(images, key=lambda item: item.image_id),
        "visual_page_candidates": sorted(
            visual_pages, key=lambda item: item.visual_page_candidate_id
        ),
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
    host = (urlsplit(normalized).hostname or "").casefold().removeprefix("www.")
    path = urlsplit(normalized).path
    raw_title = _optional_text(raw.get("title"))
    raw_snippet = _optional_text(raw.get("snippet"))
    raw_content = " ".join(value for value in (raw_title, raw_snippet) if value)
    if is_corrupted_content(raw_content):
        return None, "corrupted_content"
    classification = classify_source_lane_details(
        normalized, query.brand_scope, raw_content
    )
    if query.requested_source_lane is SourceLane.VISUAL_IMAGE and raw_images(raw):
        classification = SourceLaneClassification(
            SourceLane.VISUAL_IMAGE, "provider_image_metadata", 0.98
        )
    lane = classification.lane
    policy = policies.get(lane)
    if lane is SourceLane.COMMUNITY_REDDIT and not _is_reddit_post(normalized):
        return None, "invalid_reddit_url"
    if (
        query.source_lane is SourceLane.COMMUNITY_REDDIT
        and lane is SourceLane.COMMUNITY_REDDIT
        and not _is_reddit_host(host)
    ):
        return None, "non_reddit_url_classified_as_reddit"
    if lane is not query.requested_source_lane:
        return None, "source_lane_mismatch"
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
    title = _safe_source_text(raw.get("title"), lane)
    snippet = _safe_source_text(raw.get("snippet"), lane)
    relevance_text = " ".join(value for value in (title, snippet, normalized) if value)
    relevance_failure = _result_relevance_failure(query, relevance_text)
    if relevance_failure:
        return None, relevance_failure
    if lane is SourceLane.PRIMARY_OFFICIAL and _is_generic_official_page(normalized):
        return None, "topic_relevance_failed"
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
    registrable = registrable_domain(host)
    organization_cluster_id = stable_id(
        "organization", organization_cluster_key(host, query.brand_scope)
    )
    independent_cluster_id = (
        organization_cluster_id
        if lane is SourceLane.PRIMARY_OFFICIAL
        else stable_id(
            "independent_source",
            _source_cluster_key(host, raw.get("provider_metadata")),
        )
    )
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
                    "requested_source_lane": query.requested_source_lane,
                    "classified_source_lane": lane,
                    "classification_rule": classification.rule,
                    "classification_confidence": classification.confidence,
                    "classification_override_status": (
                        "requested_lane_confirmed"
                        if lane is query.requested_source_lane
                        else "classified_lane_overridden"
                    ),
                    "title": title,
                    "snippet": snippet,
                    "published_at": published_at,
                    "retrieved_at": retrieved_at,
                    "language": _optional_text(raw.get("language")),
                    "domain": host,
                    "exact_host": host,
                    "registrable_domain": registrable,
                    "organization_cluster_id": organization_cluster_id,
                    "regional_variant": regional_variant(host, registrable),
                    "independent_source_cluster_id": independent_cluster_id,
                    "has_images": bool(images),
                    "image_urls": images,
                    "provider_rank": _nonnegative_int(raw.get("rank")),
                    "source_cluster_id": independent_cluster_id,
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
    image, _ = qualify_visual_candidate(source, raw)
    return image


def qualify_visual_candidate(
    source: SourceCandidate, raw: Mapping[str, Any] | str
) -> tuple[ImageCandidate | None, VisualPageCandidate | None]:
    """Separate a resolvable image from an unresolved visual page hint."""
    url_value: Any
    if isinstance(raw, str):
        url_value = raw
        alt = caption = None
    else:
        url_value = raw.get("url") or raw.get("image_url")
        alt = _optional_text(raw.get("alt") or raw.get("alt_text"))
        caption = _optional_text(raw.get("caption"))
    media_metadata = _json_mapping(raw) if isinstance(raw, dict) else {}
    if not isinstance(url_value, str) or not _is_absolute_http_url(url_value):
        locator_key, locator_value = _metadata_image_locator(media_metadata)
        if locator_value is None:
            return None, _visual_page_candidate(
                source,
                media_metadata,
                "provider media did not include an image URL or asset identifier",
            )
        url_value = locator_value if locator_key in {"asset_url", "src"} else None
        locator_type = (
            "explicit_media_asset_url"
            if locator_key in {"asset_url", "src"}
            else "source_specific_metadata"
        )
        locator = locator_value
    else:
        locator_type = "provider_image_url"
        locator = url_value.strip()
    try:
        normalized = normalize_url(_remove_tracking(url_value)) if url_value else None
        return ImageCandidate.model_validate(
            {
                "image_id": stable_id("image", locator),
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
                "image_locator_type": locator_type,
                "image_locator": locator,
            }
        ), None
    except (ValueError, ValidationError):
        return None, _visual_page_candidate(
            source, media_metadata, "image locator failed contract validation"
        )


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


def registrable_domain(host: str) -> str:
    """Return a deterministic registrable-domain approximation for clustering."""
    labels = [label for label in host.casefold().strip(".").split(".") if label]
    if len(labels) <= 2:
        return ".".join(labels)
    suffix = ".".join(labels[-2:])
    return ".".join(labels[-3:]) if suffix in _MULTIPART_PUBLIC_SUFFIXES else suffix


def regional_variant(host: str, registered: str) -> str | None:
    """Identify subdomain-based regional variants without treating them as organizations."""
    normalized = host.casefold().removeprefix("www.")
    if normalized == registered:
        return None
    prefix = normalized[: -(len(registered) + 1)]
    return prefix or None


def organization_cluster_key(host: str, brand_scope: list[str] | None = None) -> str:
    """Collapse official regional and country-domain variants to one organization."""
    compact_host = re.sub(r"[^a-z0-9]", "", host.casefold())
    for brand in brand_scope or []:
        compact_brand = re.sub(r"[^a-z0-9]", "", brand.casefold())
        if compact_brand in {"", "crossbrand"} or len(compact_brand) < 4:
            continue
        if compact_brand in compact_host:
            return f"brand:{compact_brand}"
    return f"domain:{registrable_domain(host)}"


def _is_reddit_host(host: str) -> bool:
    return host == "reddit.com" or host.endswith(".reddit.com")


def _is_reddit_post(value: str) -> bool:
    parts = urlsplit(value)
    host = (parts.hostname or "").casefold().removeprefix("www.")
    return _is_reddit_host(host) and bool(_REDDIT_POST.match(parts.path))


def _is_generic_official_page(value: str) -> bool:
    parts = urlsplit(value)
    path = parts.path.casefold().rstrip("/")
    if not path:
        return True
    return any(
        marker in path
        for marker in (
            "/checkout",
            "/search",
            "/shopping-bag",
            "/magazine",
            "/stories/index",
        )
    )


def _is_absolute_http_url(value: str) -> bool:
    try:
        parts = urlsplit(value.strip())
    except ValueError:
        return False
    return parts.scheme.casefold() in {"http", "https"} and bool(parts.hostname)


def _metadata_image_locator(metadata: Mapping[str, Any]) -> tuple[str, str | None]:
    for key in ("asset_url", "src", "image_id", "asset_id"):
        value = metadata.get(key)
        if value is None or not str(value).strip():
            continue
        candidate = str(value).strip()
        if key in {"asset_url", "src"} and not _is_absolute_http_url(candidate):
            continue
        return key, candidate
    return "", None


def _visual_page_candidate(
    source: SourceCandidate,
    metadata: Mapping[str, Any],
    reason: str,
) -> VisualPageCandidate:
    return VisualPageCandidate(
        visual_page_candidate_id=stable_id(
            "visual_page",
            {"source_id": source.source_id, "metadata": dict(metadata)},
        ),
        source_id=source.source_id,
        query_id=source.query_id,
        source_page_url=source.normalized_url,
        qualification_failure_reason=reason,
        provider_media_metadata=dict(metadata),
    )


def _safe_source_text(value: Any, lane: SourceLane) -> str | None:
    text = _optional_text(value)
    if text is None or lane is not SourceLane.COMMUNITY_REDDIT:
        return text
    return _REDDIT_USERNAME.sub("[redacted-user]", text)


def is_corrupted_content(value: str) -> bool:
    """Reject obvious mojibake, control-heavy, or mechanically repeated content."""
    if not value:
        return False
    folded = value.casefold()
    if any(marker in folded for marker in _CORRUPTION_MARKERS):
        return True
    control_count = sum(
        ord(character) < 32 and character not in "\t\n\r" for character in value
    )
    if control_count:
        return True
    tokens = re.findall(r"\w+", folded)
    if len(tokens) >= 12:
        repeated = Counter(tokens)
        if repeated.most_common(1)[0][1] / len(tokens) > 0.55:
            return True
    return False


def _result_relevance_failure(query: ResearchQuery, value: str) -> str | None:
    """Apply conjunctive product-context and family-evidence screening."""
    family = canonical_query_family(query.query_family)
    if family is None:
        return None
    text = normalize_text(value).casefold()
    if family == "psp_qc" and any(marker in text for marker in _PSP_GAMING_MARKERS):
        return "psp_gaming_false_positive"
    replica_context = any(
        marker in text
        for marker in (
            "replica bag",
            "replica handbag",
            "replica purse",
            "designer replica",
            "fake bag",
            "repladies",
            "luxelife",
        )
    )
    if family == "terminology":
        family_hits = topic_relevance_hits(family, value)
        passed = replica_context and bool(family_hits)
    elif family == "psp_qc":
        photo_context = any(
            marker in text
            for marker in (
                "pre-shipment",
                "pre shipment",
                "qc photo",
                "qc picture",
                "psp photo",
                "psp picture",
                "seller photo",
            )
        ) or bool(re.search(r"(?<![a-z0-9])(?:psp|qc)(?![a-z0-9])", text))
        comparison_context = any(
            marker in text
            for marker in (
                "received item",
                "lighting",
                "batch variation",
                "quality check",
                "compare",
                "comparison",
                "inspection",
            )
        )
        passed = replica_context and photo_context and comparison_context
    else:
        material_context = any(
            marker in text
            for marker in (
                "handmade",
                "original leather",
                "tannery",
                "supplier material",
                "leather source",
            )
        )
        verification_context = any(
            marker in text
            for marker in (
                "verification",
                "verify",
                "provenance",
                "authentication",
                "evidence",
                "claim",
            )
        )
        passed = replica_context and material_context and verification_context
    return None if passed else "topic_relevance_failed"


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
