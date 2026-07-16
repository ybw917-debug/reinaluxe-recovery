"""Deterministic lane-aware query construction and paid-call quality gates."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from reinaluxe_recovery.community.normalization import normalize_text, stable_id
from reinaluxe_recovery.research.contracts import (
    QueryQualityRecord,
    ResearchPlan,
    ResearchQuery,
    ResearchQuestion,
    SourceLane,
    TemporalScope,
)
from reinaluxe_recovery.research.errors import ResearchConfigurationError

MAX_QUERY_LENGTH = 220
_GENERIC_PROHIBITED_ENTITIES = ("CarryAll", "CarryAll Vibe", "Louis Vuitton")
_TOKEN = re.compile(r"[a-z0-9]+")


@dataclass(frozen=True)
class QueryFamilyProfile:
    key: str
    anchors: tuple[str, ...]
    default_lane: SourceLane
    exact_query: str
    domain_filter: str | None
    exclusions: tuple[str, ...]
    target_section: str


_PROFILES = {
    "terminology": QueryFamilyProfile(
        key="terminology",
        anchors=(
            "AAA replica bags",
            "1:1 quality",
            "mirror quality",
            "superfake",
            "grade terminology",
        ),
        default_lane=SourceLane.COMMUNITY_REDDIT,
        exact_query=(
            'site:reddit.com/r/ "AAA replica bags" "mirror quality" "1:1 quality" tiers'
        ),
        domain_filter="reddit.com",
        exclusions=("wholesale contact", "brand homepage"),
        target_section="AAA terminology",
    ),
    "psp_qc": QueryFamilyProfile(
        key="psp_qc",
        anchors=(
            "PSP",
            "QC",
            "pre-shipment photos",
            "seller photos",
            "received item",
            "lighting",
            "batch variation",
        ),
        default_lane=SourceLane.COMMUNITY_FORUMS,
        exact_query=(
            "replica bag PSP QC photos received item lighting difference "
            "buyer forum discussion"
        ),
        domain_filter=None,
        exclusions=("official brand homepage", "ordinary news index"),
        target_section="PSP and QC limitations",
    ),
    "handmade_provenance": QueryFamilyProfile(
        key="handmade_provenance",
        anchors=(
            "handmade replica bag claims",
            "original leather claims",
            "named tannery claims",
            "leather provenance",
            "supplier claims",
            "buyer verification",
        ),
        default_lane=SourceLane.EXPERT_EDITORIAL,
        exact_query=(
            '"handmade replica bag claims" "leather provenance" '
            "tannery supplier verification expert sourcing analysis"
        ),
        domain_filter=None,
        exclusions=("official product listing", "seller contact page"),
        target_section="Handmade and provenance evidence",
    ),
}


def canonical_query_family(value: str | None) -> str | None:
    """Map request spelling variants to integrity profiles."""
    tokens = set(_TOKEN.findall((value or "").casefold().replace("_", " ")))
    if "terminology" in tokens:
        return "terminology"
    if {"psp", "qc"} & tokens:
        return "psp_qc"
    if {"handmade", "tannery", "provenance"} & tokens:
        return "handmade_provenance"
    return None


def required_topic_anchors(query_family: str | None) -> list[str]:
    key = canonical_query_family(query_family)
    return list(_PROFILES[key].anchors) if key else []


def build_preview_queries(
    plan: ResearchPlan,
    requested_families: list[str],
    *,
    maximum_results: int = 15,
) -> list[ResearchQuery]:
    """Build one exact, deterministic lane-targeted query per requested family."""
    if not 1 <= len(requested_families) <= 3:
        raise ResearchConfigurationError("query preview requires one to three families")
    keys = [canonical_query_family(value) for value in requested_families]
    if any(key is None for key in keys) or len(set(keys)) != len(keys):
        raise ResearchConfigurationError(
            "query preview requires unique terminology, psp_qc, or handmade_provenance families"
        )
    enabled = {
        policy.source_lane
        for policy in plan.source_lane_policies
        if policy.enabled and policy.query_quota > 0
    }
    question_by_key = {
        canonical_query_family(
            question.rationale.removeprefix("query family: ")
        ): question
        for question in plan.questions
        if question.rationale.startswith("query family: ")
    }
    seed_query = plan.queries[0] if plan.queries else None
    output: list[ResearchQuery] = []
    for key in keys:
        assert key is not None
        profile = _PROFILES[key]
        if profile.default_lane not in enabled:
            raise ResearchConfigurationError(
                f"request does not enable required lane {profile.default_lane.value}"
            )
        question = question_by_key.get(key) or _fallback_question(plan, key)
        prohibited = list(_GENERIC_PROHIBITED_ENTITIES)
        output.append(
            ResearchQuery(
                query_id=stable_id(
                    "integrity_query",
                    {
                        "research_id": plan.research_id,
                        "family": key,
                        "lane": profile.default_lane.value,
                        "query": profile.exact_query,
                    },
                ),
                research_question_id=question.question_id,
                query_family=key,
                source_lane=profile.default_lane,
                requested_source_lane=profile.default_lane,
                search_text=profile.exact_query,
                exact_search_query=profile.exact_query,
                search_domain_filter=profile.domain_filter,
                maximum_results=maximum_results,
                positive_terms=list(profile.anchors),
                exclusion_terms=list(profile.exclusions),
                query_anchor_terms=list(profile.anchors),
                query_exclusion_terms=list(profile.exclusions),
                required_topic_anchors=list(profile.anchors),
                prohibited_unrelated_entities=prohibited,
                article_entities_included=[],
                entity_inclusion_rationale=(
                    "Generic AAA pillar research intentionally excludes page-specific brand, "
                    "model, image, filename, and product-ID entities."
                ),
                query_generation_inputs={
                    "family_profile": key,
                    "research_question": question.question,
                    "lane_template": profile.default_lane.value,
                    "article_entity_policy": "generic_topic_only",
                },
                clear_research_question=question.question,
                temporal_range=(
                    seed_query.temporal_range if seed_query else TemporalScope()
                ),
                brand_scope=(seed_query.brand_scope if seed_query else []),
                model_scope=(seed_query.model_scope if seed_query else []),
                target_article_section=profile.target_section,
                expected_evidence_type=_evidence_type(profile.default_lane),
                stopping_criteria=(
                    "one provider call after query-quality approval; retain only topic-relevant results"
                ),
                language=seed_query.language if seed_query else "en",
            )
        )
    return output


def evaluate_query_quality(
    query: ResearchQuery,
    peers: list[ResearchQuery] | None = None,
) -> QueryQualityRecord:
    """Evaluate whether a query is safe to send to a paid provider."""
    text = query.exact_search_query
    hits = _phrase_hits(text, query.required_topic_anchors or query.query_anchor_terms)
    required = query.required_topic_anchors or query.query_anchor_terms
    missing = [] if hits else list(required)
    prohibited = _phrase_hits(text, query.prohibited_unrelated_entities)
    entity_tokens = sum(len(_tokens(value)) for value in prohibited)
    total_tokens = max(1, len(_tokens(text)))
    contamination = min(1.0, entity_tokens / total_tokens)
    lane_valid = _lane_strategy_valid(query)
    duplicate = any(
        peer.query_id != query.query_id
        and _query_similarity(text, peer.exact_search_query) >= 0.8
        for peer in (peers or [])
    )
    failures: list[str] = []
    if not hits:
        failures.append("missing_required_topic_anchor")
    if prohibited:
        failures.append("prohibited_unrelated_entity")
    if contamination > 0.25:
        failures.append("article_entity_dominance")
    if not lane_valid:
        failures.append("lane_strategy_invalid")
    if duplicate:
        failures.append("duplicate_query_risk")
    if len(text) > MAX_QUERY_LENGTH:
        failures.append("query_too_long")
    if not query.clear_research_question:
        failures.append("research_question_missing")
    return QueryQualityRecord(
        query_id=query.query_id,
        passed=not failures,
        required_anchor_hits=hits,
        missing_required_anchors=missing,
        prohibited_entity_hits=prohibited,
        entity_contamination_score=round(contamination, 4),
        lane_strategy_valid=lane_valid,
        duplicate_query_risk=duplicate,
        failure_reasons=failures,
    )


def topic_relevance_hits(query_family: str | None, value: str) -> list[str]:
    """Return deterministic family-specific relevance signals."""
    key = canonical_query_family(query_family)
    if key is None:
        return []
    lexical = {
        "terminology": (
            "AAA",
            "1:1",
            "mirror quality",
            "superfake",
            "replica quality tier",
        ),
        "psp_qc": (
            "PSP",
            "QC",
            "pre-shipment",
            "seller photo",
            "received item",
            "lighting",
            "batch variation",
        ),
        "handmade_provenance": (
            "handmade",
            "tannery",
            "leather source",
            "provenance",
            "original leather",
            "supplier material claim",
        ),
    }[key]
    return _phrase_hits(value, lexical)


def _fallback_question(plan: ResearchPlan, key: str) -> ResearchQuestion:
    profile = _PROFILES[key]
    return ResearchQuestion(
        question_id=stable_id(
            "preview_question", {"research": plan.research_id, "key": key}
        ),
        question=f"What public evidence addresses {profile.target_section}?",
        rationale=f"query family: {key}",
        target_article_section=profile.target_section,
    )


def _lane_strategy_valid(query: ResearchQuery) -> bool:
    text = query.exact_search_query.casefold()
    lane = query.requested_source_lane
    if lane is SourceLane.COMMUNITY_REDDIT:
        return (
            "site:reddit.com/r/" in text and query.search_domain_filter == "reddit.com"
        )
    if lane is SourceLane.COMMUNITY_FORUMS:
        return any(
            value in text for value in ("forum", "discussion", "buyer report", "review")
        )
    if lane is SourceLane.EXPERT_EDITORIAL:
        return any(
            value in text
            for value in ("analysis", "verification", "method", "material", "sourcing")
        )
    if lane is SourceLane.PRIMARY_OFFICIAL:
        return any(value in text for value in ("official", "specification", "care"))
    if lane is SourceLane.COMMERCIAL_OBSERVATION:
        return any(value in text for value in ("listing", "retailer", "seller"))
    return any(value in text for value in ("image", "photo", "visual"))


def _phrase_hits(value: str, phrases: tuple[str, ...] | list[str]) -> list[str]:
    normalized = normalize_text(value).casefold()
    hits = []
    for phrase in phrases:
        candidate = normalize_text(phrase).casefold()
        pattern = (
            r"(?<![a-z0-9])"
            + re.escape(candidate).replace(r"\ ", r"\s+")
            + r"(?![a-z0-9])"
        )
        if re.search(pattern, normalized):
            hits.append(phrase)
    return hits


def _tokens(value: str) -> set[str]:
    return set(_TOKEN.findall(value.casefold()))


def _query_similarity(left: str, right: str) -> float:
    left_tokens = _tokens(left)
    right_tokens = _tokens(right)
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / len(left_tokens | right_tokens)


def _evidence_type(lane: SourceLane) -> str:
    return {
        SourceLane.COMMUNITY_REDDIT: "public Reddit post permalink",
        SourceLane.COMMUNITY_FORUMS: "public buyer or specialist discussion",
        SourceLane.PRIMARY_OFFICIAL: "directly relevant authentic-product reference",
        SourceLane.EXPERT_EDITORIAL: "attributed material or sourcing-claim analysis",
        SourceLane.COMMERCIAL_OBSERVATION: "scoped commercial observation",
        SourceLane.VISUAL_IMAGE: "resolved source-linked visual reference",
    }[lane]


def provider_request_preview(query: ResearchQuery) -> dict[str, Any]:
    """Render the exact non-secret request fields without executing a provider."""
    payload: dict[str, Any] = {
        "query_id": query.query_id,
        "search_query": query.exact_search_query,
        "requested_source_lane": query.requested_source_lane.value,
        "count": query.maximum_results,
        "query_hash": query.query_hash,
    }
    if query.search_domain_filter:
        payload["search_domain_filter"] = query.search_domain_filter
    return payload
