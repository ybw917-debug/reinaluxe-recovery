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
    research_question: str


_PROFILES = {
    "terminology": QueryFamilyProfile(
        key="terminology",
        anchors=(
            "AAA",
            "1:1",
            "mirror quality",
            "superfake",
            "high tier",
            "quality tier",
        ),
        default_lane=SourceLane.COMMUNITY_REDDIT,
        exact_query=(
            "site:reddit.com/r/ replica bags AAA 1:1 mirror quality "
            "superfake high tier meaning"
        ),
        domain_filter="reddit.com",
        exclusions=("wholesale contact", "brand homepage"),
        target_section="AAA terminology",
        research_question=(
            "What terminology, interpretations and disagreements appear in Reddit "
            "discussions about AAA, 1:1, mirror quality, superfake and replica quality tiers?"
        ),
    ),
    "psp_qc": QueryFamilyProfile(
        key="psp_qc",
        anchors=(
            "replica handbag",
            "pre-shipment photos",
            "QC photos",
            "PSP",
            "seller photos",
            "received item",
            "lighting",
            "batch variation",
        ),
        default_lane=SourceLane.COMMUNITY_FORUMS,
        exact_query=(
            'replica handbag "pre-shipment photos" PSP QC pictures received item '
            "lighting difference seller photos buyer forum review"
        ),
        domain_filter=None,
        exclusions=("official brand homepage", "ordinary news index"),
        target_section="PSP and QC limitations",
        research_question=(
            "What do public forum and buyer-review discussions report about "
            "pre-shipment photos, PSP and QC pictures, lighting differences, seller "
            "photos versus received items, and batch variation?"
        ),
    ),
    "handmade_provenance": QueryFamilyProfile(
        key="handmade_provenance",
        anchors=(
            "replica handbag",
            "handmade",
            "original leather",
            "tannery claims",
            "leather provenance",
            "verification",
        ),
        default_lane=SourceLane.EXPERT_EDITORIAL,
        exact_query=(
            'replica handbag handmade "original leather" tannery claims '
            '"leather provenance" verification expert analysis'
        ),
        domain_filter=None,
        exclusions=("official product listing", "seller contact page"),
        target_section="Handmade and provenance evidence",
        research_question=(
            "What expert or editorial analysis evaluates handmade, original-leather, "
            "tannery, supplier-material and leather-provenance claims for replica handbags?"
        ),
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
    seed_query = plan.queries[0] if plan.queries else None
    output: list[ResearchQuery] = []
    for key in keys:
        assert key is not None
        profile = _PROFILES[key]
        if profile.default_lane not in enabled:
            raise ResearchConfigurationError(
                f"request does not enable required lane {profile.default_lane.value}"
            )
        question_id = stable_id(
            "preview_question",
            {
                "research_id": plan.research_id,
                "family": key,
                "question": profile.research_question,
            },
        )
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
                research_question_id=question_id,
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
                    "research_question": profile.research_question,
                    "lane_template": profile.default_lane.value,
                    "article_entity_policy": "generic_topic_only",
                },
                clear_research_question=profile.research_question,
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


def research_questions_for_queries(
    queries: list[ResearchQuery],
) -> list[ResearchQuestion]:
    """Materialize the exact lane-consistent questions referenced by preview queries."""
    return [
        ResearchQuestion(
            question_id=query.research_question_id,
            question=query.clear_research_question or query.exact_search_query,
            rationale=f"retrieval profile: {query.query_family or 'question_specific'}",
            target_article_section=query.target_article_section,
            evidence_gap="retrieval-oriented public evidence",
            priority=index,
        )
        for index, query in enumerate(queries, start=1)
    ]


def evaluate_query_quality(
    query: ResearchQuery,
    peers: list[ResearchQuery] | None = None,
) -> QueryQualityRecord:
    """Evaluate independent structural and retrieval quality before a paid call."""
    text = query.exact_search_query
    hits, missing = _semantic_anchor_assessment(query)
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
    structural_failures: list[str] = []
    if missing:
        structural_failures.append("missing_required_topic_anchor")
    if prohibited:
        structural_failures.append("prohibited_unrelated_entity")
    if contamination > 0.25:
        structural_failures.append("article_entity_dominance")
    if not lane_valid:
        structural_failures.append("lane_strategy_invalid")
    if duplicate:
        structural_failures.append("duplicate_query_risk")
    if len(text) > MAX_QUERY_LENGTH:
        structural_failures.append("query_too_long")
    if not query.clear_research_question:
        structural_failures.append("research_question_missing")
    question_consistent = _research_question_lane_consistent(query)
    quoted_phrases = re.findall(r'"([^"\r\n]+)"', text)
    quoted_tokens = sum(len(_TOKEN.findall(phrase)) for phrase in quoted_phrases)
    ordered_tokens = _TOKEN.findall(text.casefold())
    quoted_ratio = min(1.0, quoted_tokens / max(1, len(ordered_tokens)))
    overconstraint = len(quoted_phrases) >= 3 or (
        len(quoted_phrases) >= 2 and quoted_ratio > 0.65
    )
    ambiguous = _unmitigated_acronyms(text)
    acronym_mitigated = not ambiguous
    natural_score = _natural_language_score(
        text,
        question_consistent=question_consistent,
        overconstraint=overconstraint,
        ambiguous_acronyms=ambiguous,
    )
    retrieval_failures: list[str] = []
    if not question_consistent:
        retrieval_failures.append("research_question_lane_contradiction")
    if missing:
        retrieval_failures.append("semantic_anchor_groups_incomplete")
    if overconstraint:
        retrieval_failures.append("retrieval_overconstraint_risk")
    if ambiguous:
        retrieval_failures.append("ambiguous_acronym_unmitigated")
    if natural_score < 0.6:
        retrieval_failures.append("natural_language_query_score_low")
    return QueryQualityRecord(
        query_id=query.query_id,
        passed=not structural_failures,
        required_anchor_hits=hits,
        missing_required_anchors=missing,
        prohibited_entity_hits=prohibited,
        entity_contamination_score=round(contamination, 4),
        lane_strategy_valid=lane_valid,
        duplicate_query_risk=duplicate,
        research_question_lane_consistency=question_consistent,
        quoted_phrase_count=len(quoted_phrases),
        quoted_token_ratio=round(quoted_ratio, 4),
        retrieval_overconstraint_risk=overconstraint,
        ambiguous_acronyms=ambiguous,
        ambiguous_acronym_mitigated=acronym_mitigated,
        natural_language_query_score=natural_score,
        retrieval_quality_passed=not retrieval_failures,
        failure_reasons=[*structural_failures, *retrieval_failures],
    )


def _semantic_anchor_assessment(
    query: ResearchQuery,
) -> tuple[list[str], list[str]]:
    text = normalize_text(query.exact_search_query).casefold()
    key = canonical_query_family(query.query_family)
    if key == "terminology":
        concepts = {
            "AAA": _contains_phrase(text, "AAA"),
            "1:1": "1:1" in text,
            "mirror quality": _contains_phrase(text, "mirror quality"),
            "superfake": _contains_phrase(text, "superfake"),
            "high tier": _contains_phrase(text, "high tier"),
            "quality tier": _contains_phrase(text, "quality tier"),
        }
        hits = [name for name, present in concepts.items() if present]
        return hits, [] if len(hits) >= 3 else ["three_terminology_concepts"]
    if key == "psp_qc":
        groups = {
            "replica_handbag_context": _contains_any(
                text, ("replica handbag", "replica bag", "replica purse")
            ),
            "pre_shipment_or_qc_photos": _contains_any(
                text,
                (
                    "pre-shipment photo",
                    "pre-shipment photos",
                    "pre shipment photo",
                    "pre shipment photos",
                    "preshipment photo",
                    "preshipment photos",
                    "QC photo",
                    "QC photos",
                    "QC picture",
                    "QC pictures",
                ),
            ),
            "comparison_concept": _contains_any(
                text,
                ("received item", "lighting", "seller photo", "batch variation"),
            ),
        }
        return (
            [name for name, present in groups.items() if present],
            [name for name, present in groups.items() if not present],
        )
    if key == "handmade_provenance":
        groups = {
            "replica_handbag_context": _contains_any(
                text, ("replica handbag", "replica bag", "replica purse")
            ),
            "construction_or_material_claim": _contains_any(
                text,
                (
                    "handmade",
                    "original leather",
                    "tannery",
                    "supplier material",
                    "leather claim",
                ),
            ),
            "verification_or_provenance": _contains_any(
                text,
                ("verification", "verify", "provenance", "authentication", "source"),
            ),
        }
        return (
            [name for name, present in groups.items() if present],
            [name for name, present in groups.items() if not present],
        )
    configured = query.required_topic_anchors or query.query_anchor_terms
    hits = _phrase_hits(text, configured)
    return hits, [] if hits else list(configured)


def _research_question_lane_consistent(query: ResearchQuery) -> bool:
    question = normalize_text(query.clear_research_question or "").casefold()
    if not question:
        return False
    lane = query.requested_source_lane
    if re.search(r"\bnon[- ]community\b", question) and lane in {
        SourceLane.COMMUNITY_REDDIT,
        SourceLane.COMMUNITY_FORUMS,
    }:
        return False
    explicit_lanes: set[SourceLane] = set()
    if "reddit" in question:
        explicit_lanes.add(SourceLane.COMMUNITY_REDDIT)
    if _contains_any(question, ("public forum", "buyer-review", "buyer review")):
        explicit_lanes.add(SourceLane.COMMUNITY_FORUMS)
    if _contains_any(
        question, ("expert analysis", "expert or editorial", "editorial analysis")
    ):
        explicit_lanes.add(SourceLane.EXPERT_EDITORIAL)
    if _contains_any(question, ("official source", "official brand")):
        explicit_lanes.add(SourceLane.PRIMARY_OFFICIAL)
    if _contains_any(question, ("marketplace listing", "commercial listing")):
        explicit_lanes.add(SourceLane.COMMERCIAL_OBSERVATION)
    if _contains_any(question, ("image source", "visual reference")):
        explicit_lanes.add(SourceLane.VISUAL_IMAGE)
    return not explicit_lanes or lane in explicit_lanes


def _unmitigated_acronyms(value: str) -> list[str]:
    text = normalize_text(value).casefold()
    unresolved: list[str] = []
    if re.search(r"(?<![a-z0-9])psp(?![a-z0-9])", text) and not _contains_any(
        text,
        (
            "pre-shipment photo",
            "pre-shipment photos",
            "pre shipment photo",
            "pre shipment photos",
            "preshipment photo",
            "preshipment photos",
        ),
    ):
        unresolved.append("PSP")
    if re.search(r"(?<![a-z0-9])aaa(?![a-z0-9])", text) and not (
        "replica" in text and _contains_any(text, ("bag", "quality", "tier"))
    ):
        unresolved.append("AAA")
    if re.search(r"(?<![a-z0-9])qc(?![a-z0-9])", text) and not (
        "replica" in text
        and _contains_any(
            text, ("photo", "photos", "picture", "pictures", "quality control")
        )
    ):
        unresolved.append("QC")
    return unresolved


def _natural_language_score(
    value: str,
    *,
    question_consistent: bool,
    overconstraint: bool,
    ambiguous_acronyms: list[str],
) -> float:
    token_count = len(_TOKEN.findall(value))
    score = 1.0
    if token_count < 6:
        score -= 0.3
    elif token_count > 30:
        score -= 0.2
    if not question_consistent:
        score -= 0.45
    if overconstraint:
        score -= 0.35
    score -= min(0.4, len(ambiguous_acronyms) * 0.25)
    return round(max(0.0, min(1.0, score)), 4)


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


def _contains_phrase(value: str, phrase: str) -> bool:
    return bool(
        re.search(
            r"(?<![a-z0-9])"
            + re.escape(phrase.casefold()).replace(r"\ ", r"\s+")
            + r"(?![a-z0-9])",
            value.casefold(),
        )
    )


def _contains_any(value: str, phrases: tuple[str, ...]) -> bool:
    return any(_contains_phrase(value, phrase) for phrase in phrases)


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
