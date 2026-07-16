"""Atomic claim analysis, corroboration, contradiction, topic and article mapping."""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from collections import defaultdict
from typing import Any, Literal

from pydantic import Field

from reinaluxe_recovery.community.normalization import (
    normalize_claim_text,
    normalize_text,
    stable_id,
)
from reinaluxe_recovery.domain.base import DomainModel
from reinaluxe_recovery.research.contracts import (
    ArticleContentOpportunity,
    CandidateClaim,
    ClaimCluster,
    ClaimEvidenceLink,
    ContradictionRecord,
    EvidenceAssessment,
    EvidenceRelationship,
    ImageEvidenceRecord,
    ResearchPlan,
    ResearchTopic,
    SearchRun,
    SourceCandidate,
    SourceEvidenceRecord,
    SourceLane,
)

_SENTENCE = re.compile(r"(?<=[.!?])\s+")
_TOKENS = re.compile(r"[\w']+", re.UNICODE)
_NEGATIVE = {"not", "no", "never", "without", "isn't", "doesn't", "cannot", "can't"}
_FIRST_HAND = re.compile(r"\b(?:i|we|my|our)\b", re.IGNORECASE)
_NUMBER = re.compile(
    r"(?<!\w)\d+(?:[.,]\d+)?(?:\s?(?:%|kg|g|lb|oz|cm|mm|in))?", re.IGNORECASE
)
_URL = re.compile(r"https?://|www\.", re.IGNORECASE)
_PROMOTION = re.compile(
    r"\b(?:buy now|discount|coupon|affiliate|contact me|best price)\b", re.IGNORECASE
)


class SourceAnalysisResult(DomainModel):
    source_lane_classification: SourceLane | None = None
    relevance: float = Field(ge=0, le=1)
    first_hand_status: Literal["first_hand", "hearsay", "mixed", "unknown"]
    specificity: float = Field(ge=0, le=1)
    commercial_promotion_risk: Literal["low", "medium", "high", "unknown"]
    source_access_quality: Literal["full", "partial", "snippet_only", "unavailable"]
    evidence_summary: str
    key_observations: list[str] = Field(default_factory=list)
    claims: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    proposed_topic_ids: list[str] = Field(default_factory=list)
    proposed_article_sections: list[str] = Field(default_factory=list)
    image_presence_assessment: Literal[
        "present", "not_returned", "metadata_only", "uncertain"
    ] = "uncertain"


class SourceAnalysisProvider(ABC):
    """Optional GLM-assisted source-analysis boundary."""

    @abstractmethod
    def analyze(
        self, source: SourceCandidate, plan: ResearchPlan
    ) -> SourceAnalysisResult:
        """Analyze only a screened provider-returned source."""


class DeterministicSourceAnalyzer(SourceAnalysisProvider):
    """Transparent offline analyzer for fixtures and fallback review packages."""

    def analyze(
        self, source: SourceCandidate, plan: ResearchPlan
    ) -> SourceAnalysisResult:
        del plan
        composite = normalize_text(
            " ".join(item for item in [source.title, source.snippet] if item)
        )
        claims = [
            sentence.rstrip(".")
            for sentence in _SENTENCE.split(composite)
            if len(sentence.split()) >= 4
        ][:3]
        if not claims and composite:
            claims = [composite]
        first_hand: Literal["first_hand", "unknown"] = (
            "first_hand" if _FIRST_HAND.search(composite) else "unknown"
        )
        risk: Literal["high", "medium", "unknown"] = (
            "high"
            if _PROMOTION.search(composite)
            else (
                "medium"
                if source.source_lane.value == "commercial_observation"
                else "unknown"
            )
        )
        limitations = ["analysis is limited to provider-returned title and snippet"]
        if source.published_at is None:
            limitations.append("publication date unavailable")
        if source.has_images:
            limitations.append(
                "image appearance does not prove provenance or authenticity"
            )
        return SourceAnalysisResult(
            source_lane_classification=source.source_lane,
            relevance=0.6 if composite else 0.0,
            first_hand_status=first_hand,
            specificity=min(1.0, len(composite.split()) / 50) if composite else 0.0,
            commercial_promotion_risk=risk,
            source_access_quality="snippet_only",
            evidence_summary=composite or "No provider excerpt was available.",
            key_observations=claims,
            claims=claims,
            limitations=limitations,
            proposed_article_sections=[],
            image_presence_assessment=(
                "present" if source.has_images else "not_returned"
            ),
        )


class ResearchAnalysisBundle(DomainModel):
    schema_version: str = "1.0"
    research_id: str
    plan: ResearchPlan
    run: SearchRun
    source_evidence_records: list[SourceEvidenceRecord]
    candidate_claims: list[CandidateClaim]
    claim_evidence_links: list[ClaimEvidenceLink]
    claim_clusters: list[ClaimCluster]
    contradictions: list[ContradictionRecord]
    image_evidence_records: list[ImageEvidenceRecord]
    topics: list[ResearchTopic]
    topic_knowledge_opportunities: list[dict[str, Any]]
    article_content_opportunities: list[ArticleContentOpportunity]


def analyze_search_run(
    run: SearchRun,
    plan: ResearchPlan,
    analyzer: SourceAnalysisProvider | None = None,
) -> ResearchAnalysisBundle:
    """Analyze only screened candidates, preserving every claim/source link."""
    if run.plan_hash != plan.plan_hash or run.research_id != plan.research_id:
        raise ValueError("search run does not match research plan")
    selected = analyzer or DeterministicSourceAnalyzer()
    query_by_id = {item.query_id: item for item in plan.queries}
    evidence: list[SourceEvidenceRecord] = []
    claims_by_key: dict[str, CandidateClaim] = {}
    links: list[ClaimEvidenceLink] = []
    source_by_id = {item.source_id: item for item in run.source_candidates}
    for source in sorted(run.source_candidates, key=lambda item: item.source_id):
        result = selected.analyze(source, plan)
        query = query_by_id[source.query_id]
        evidence_id = stable_id(
            "evidence", {"source_id": source.source_id, "query_id": source.query_id}
        )
        topic_ids = result.proposed_topic_ids or _topic_ids(query, plan)
        sections = result.proposed_article_sections or (
            [query.target_article_section] if query.target_article_section else []
        )
        evidence.append(
            SourceEvidenceRecord(
                evidence_id=evidence_id,
                source_id=source.source_id,
                query_id=source.query_id,
                source_lane_classification=(
                    result.source_lane_classification or source.source_lane
                ),
                relevance=result.relevance,
                first_hand_status=result.first_hand_status,
                specificity=result.specificity,
                commercial_promotion_risk=result.commercial_promotion_risk,
                source_access_quality=result.source_access_quality,
                evidence_summary=result.evidence_summary,
                key_observations=result.key_observations,
                image_presence_assessment=result.image_presence_assessment,
                limitations=result.limitations,
                proposed_topic_ids=topic_ids,
                proposed_article_sections=sections,
            )
        )
        for raw_claim in result.claims:
            if _URL.search(raw_claim) or not _numeric_claim_is_grounded(
                raw_claim, source
            ):
                continue
            normalized = normalize_claim_text(raw_claim)
            if not normalized:
                continue
            key = f"{normalized}|{'|'.join(sorted(query.brand_scope))}|{'|'.join(sorted(query.model_scope))}"
            claim = claims_by_key.get(key)
            if claim is None:
                claim = CandidateClaim(
                    claim_id=stable_id("claim", key),
                    claim_text=normalize_text(raw_claim),
                    normalized_claim_text=normalized,
                    topic_ids=topic_ids,
                    brand_scope=query.brand_scope,
                    model_scope=query.model_scope,
                    temporal_scope=query.temporal_range,
                    proposed_article_sections=sections,
                    limitations=result.limitations,
                )
                claims_by_key[key] = claim
            links.append(
                ClaimEvidenceLink(
                    link_id=stable_id(
                        "celink",
                        {"claim_id": claim.claim_id, "source_id": source.source_id},
                    ),
                    claim_id=claim.claim_id,
                    source_id=source.source_id,
                    evidence_id=evidence_id,
                    relationship=EvidenceRelationship.SUPPORTS,
                    independence_group=source.domain,
                    rationale="claim extracted from the screened provider-returned source",
                )
            )
    claims = sorted(claims_by_key.values(), key=lambda item: item.claim_id)
    contradictions = _find_contradictions(claims, links)
    contradiction_claims = {
        claim_id for item in contradictions for claim_id in item.claim_ids
    }
    clusters = _build_clusters(claims, links, source_by_id, contradiction_claims)
    claim_ids_by_source: dict[str, list[str]] = defaultdict(list)
    for link in links:
        claim_ids_by_source[link.source_id].append(link.claim_id)
    image_evidence = [
        ImageEvidenceRecord(
            image_evidence_id=stable_id("image_evidence", item.image_id),
            image_id=item.image_id,
            source_id=item.source_id,
            limitations=[
                "publication permission requires owner review",
                "image appearance does not prove provenance or authenticity",
            ],
            claim_ids=sorted(
                set(item.linked_claim_ids) | set(claim_ids_by_source[item.source_id])
            ),
        )
        for item in sorted(run.image_candidates, key=lambda value: value.image_id)
    ]
    research_topics = _build_topics(claims, plan)
    topic_opportunities = _topic_opportunities(claims, links)
    article_opportunities = _article_opportunities(claims, clusters, links, run, plan)
    return ResearchAnalysisBundle(
        research_id=plan.research_id,
        plan=plan,
        run=run,
        source_evidence_records=sorted(evidence, key=lambda item: item.evidence_id),
        candidate_claims=claims,
        claim_evidence_links=sorted(links, key=lambda item: item.link_id),
        claim_clusters=clusters,
        contradictions=contradictions,
        image_evidence_records=image_evidence,
        topics=research_topics,
        topic_knowledge_opportunities=topic_opportunities,
        article_content_opportunities=article_opportunities,
    )


def _numeric_claim_is_grounded(claim: str, source: SourceCandidate) -> bool:
    claim_numbers = {item.casefold() for item in _NUMBER.findall(claim)}
    if not claim_numbers:
        return True
    source_text = " ".join(
        item for item in (source.title, source.snippet) if item is not None
    )
    source_numbers = {item.casefold() for item in _NUMBER.findall(source_text)}
    return claim_numbers <= source_numbers


def _build_clusters(
    claims: list[CandidateClaim],
    links: list[ClaimEvidenceLink],
    sources: dict[str, SourceCandidate],
    contradiction_claims: set[str],
) -> list[ClaimCluster]:
    links_by_claim: dict[str, list[ClaimEvidenceLink]] = defaultdict(list)
    for link in links:
        links_by_claim[link.claim_id].append(link)
    output: list[ClaimCluster] = []
    for claim in claims:
        claim_links = links_by_claim[claim.claim_id]
        source_ids = sorted({item.source_id for item in claim_links})
        domains = {sources[item].domain for item in source_ids}
        lanes = {sources[item].source_lane for item in source_ids}
        if claim.claim_id in contradiction_claims:
            assessment = EvidenceAssessment.DISPUTED
        elif len(domains) >= 2:
            assessment = EvidenceAssessment.CORROBORATED
        elif len(source_ids) == 1:
            assessment = EvidenceAssessment.SINGLE_SOURCE
        else:
            assessment = EvidenceAssessment.INSUFFICIENT
        output.append(
            ClaimCluster(
                cluster_id=stable_id("cluster", claim.claim_id),
                canonical_claim_id=claim.claim_id,
                claim_ids=[claim.claim_id],
                supporting_source_ids=source_ids,
                assessment=assessment,
                source_lane_diversity=len(lanes),
                limitations=(
                    []
                    if assessment == EvidenceAssessment.CORROBORATED
                    else ["independent multi-source corroboration threshold not met"]
                ),
            )
        )
    return sorted(output, key=lambda item: item.cluster_id)


def _find_contradictions(
    claims: list[CandidateClaim], links: list[ClaimEvidenceLink]
) -> list[ContradictionRecord]:
    sources_by_claim: dict[str, set[str]] = defaultdict(set)
    for link in links:
        sources_by_claim[link.claim_id].add(link.source_id)
    output: list[ContradictionRecord] = []
    for index, left in enumerate(claims):
        left_tokens = set(_TOKENS.findall(left.normalized_claim_text))
        for right in claims[index + 1 :]:
            right_tokens = set(_TOKENS.findall(right.normalized_claim_text))
            common = left_tokens & right_tokens
            smaller = min(len(left_tokens), len(right_tokens)) or 1
            negation_differs = bool(left_tokens & _NEGATIVE) != bool(
                right_tokens & _NEGATIVE
            )
            if len(common) / smaller < 0.6 or not negation_differs:
                continue
            source_ids = sorted(
                sources_by_claim[left.claim_id] | sources_by_claim[right.claim_id]
            )
            if len(source_ids) < 2:
                continue
            output.append(
                ContradictionRecord(
                    contradiction_id=stable_id(
                        "contradiction", sorted([left.claim_id, right.claim_id])
                    ),
                    claim_ids=sorted([left.claim_id, right.claim_id]),
                    source_ids=source_ids,
                    position_a=left.claim_text,
                    position_b=right.claim_text,
                    possible_explanations=[
                        "scope, date, model, batch, seller, or methodology may differ",
                        "provider snippets may omit relevant source context",
                    ],
                )
            )
    return sorted(output, key=lambda item: item.contradiction_id)


def _topic_ids(query: Any, plan: ResearchPlan) -> list[str]:
    question = next(
        item
        for item in plan.questions
        if item.question_id == query.research_question_id
    )
    return question.topic_ids or [stable_id("topic", question.question)]


def _build_topics(
    claims: list[CandidateClaim], plan: ResearchPlan
) -> list[ResearchTopic]:
    names: dict[str, str] = {}
    for question in plan.questions:
        for topic_id in question.topic_ids or [stable_id("topic", question.question)]:
            names.setdefault(topic_id, question.question)
    for claim in claims:
        for topic_id in claim.topic_ids:
            names.setdefault(topic_id, claim.claim_text[:120])
    return [
        ResearchTopic(
            topic_id=topic_id,
            name=name,
            definition=f"Reusable research topic derived from: {name}",
            aliases=[],
            synonyms=[],
            query_templates=[
                query.search_text
                for query in plan.queries
                if any(
                    topic_id
                    in (question.topic_ids or [stable_id("topic", question.question)])
                    for question in plan.questions
                    if question.question_id == query.research_question_id
                )
            ],
        )
        for topic_id, name in sorted(names.items())
    ]


def _topic_opportunities(
    claims: list[CandidateClaim], links: list[ClaimEvidenceLink]
) -> list[dict[str, Any]]:
    sources_by_claim: dict[str, set[str]] = defaultdict(set)
    for link in links:
        sources_by_claim[link.claim_id].add(link.source_id)
    return [
        {
            "topic_id": topic_id,
            "claim_id": claim.claim_id,
            "source_ids": sorted(sources_by_claim[claim.claim_id]),
            "opportunity": "reuse_scoped_claim_across_relevant_articles",
        }
        for claim in claims
        for topic_id in claim.topic_ids
    ]


def _article_opportunities(
    claims: list[CandidateClaim],
    clusters: list[ClaimCluster],
    links: list[ClaimEvidenceLink],
    run: SearchRun,
    plan: ResearchPlan,
) -> list[ArticleContentOpportunity]:
    cluster_by_claim = {item.canonical_claim_id: item for item in clusters}
    links_by_claim: dict[str, list[ClaimEvidenceLink]] = defaultdict(list)
    for link in links:
        links_by_claim[link.claim_id].append(link)
    output: list[ArticleContentOpportunity] = []
    article_url = plan.target_article_url
    for claim in claims:
        # Use the claim's already-preserved section; avoid deriving or drafting copy here.
        section = (
            claim.proposed_article_sections[0]
            if claim.proposed_article_sections
            else None
        )
        cluster = cluster_by_claim[claim.claim_id]
        if cluster.assessment == EvidenceAssessment.CORROBORATED:
            opportunity_type: Literal[
                "add_evidence",
                "qualify_claim",
                "answer_question",
                "add_visual",
                "topic_only",
                "no_action",
            ] = "add_evidence"
            rationale = (
                "Multiple independent domains support a scoped evidence opportunity."
            )
        elif cluster.assessment == EvidenceAssessment.DISPUTED:
            opportunity_type = "qualify_claim"
            rationale = "Preserved disagreement requires qualification rather than forced resolution."
        else:
            opportunity_type = "no_action"
            rationale = "Evidence is relevant but insufficient for an article change."
        output.append(
            ArticleContentOpportunity(
                opportunity_id=stable_id(
                    "research_opportunity",
                    {"research_id": plan.research_id, "claim_id": claim.claim_id},
                ),
                research_id=plan.research_id,
                article_url=article_url,
                target_section=section,
                opportunity_type=opportunity_type,
                claim_ids=[claim.claim_id],
                source_ids=cluster.supporting_source_ids,
                rationale=rationale,
            )
        )
    claims_by_source: dict[str, list[str]] = defaultdict(list)
    for link in links:
        claims_by_source[link.source_id].append(link.claim_id)
    for image in run.image_candidates:
        linked_claims = sorted(
            set(image.linked_claim_ids) | set(claims_by_source[image.source_id])
        )
        section = next(
            (
                claim.proposed_article_sections[0]
                for claim in claims
                if claim.claim_id in linked_claims and claim.proposed_article_sections
            ),
            None,
        )
        output.append(
            ArticleContentOpportunity(
                opportunity_id=stable_id(
                    "research_opportunity",
                    {"research_id": plan.research_id, "image_id": image.image_id},
                ),
                research_id=plan.research_id,
                article_url=article_url,
                target_section=section,
                opportunity_type="add_visual",
                claim_ids=linked_claims,
                source_ids=[image.source_id],
                rationale=(
                    "Source-linked visual candidate requires permission and owner review; "
                    "appearance does not establish provenance or authenticity."
                ),
            )
        )
    return sorted(output, key=lambda item: item.opportunity_id)
