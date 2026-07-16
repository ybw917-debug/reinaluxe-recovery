"""Hard-limited live discovery smoke workflow with source-integrity reporting."""

from __future__ import annotations

import re
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from reinaluxe_recovery.community.io import (
    prepare_output,
    write_csv,
    write_json,
    write_text,
)
from reinaluxe_recovery.community.normalization import (
    content_hash,
    normalize_text,
    stable_id,
)
from reinaluxe_recovery.research.analysis import (
    ResearchAnalysisBundle,
    SourceAnalysisProvider,
    analyze_search_run,
)
from reinaluxe_recovery.research.artifacts import load_research_request
from reinaluxe_recovery.research.contracts import (
    EvidenceAssessment,
    ImageCandidate,
    ResearchPlan,
    ResearchQuery,
    SearchRun,
    SmokeRecommendation,
    SourceCandidate,
    SourceLane,
    VisualPageCandidate,
)
from reinaluxe_recovery.research.errors import ResearchConfigurationError, ResearchError
from reinaluxe_recovery.research.planning import build_research_plan
from reinaluxe_recovery.research.production import build_editorial_synthesis
from reinaluxe_recovery.research.providers import (
    ResearchSearchProvider,
    ZhipuGLMSourceAnalyzer,
    default_provider_registry,
)
from reinaluxe_recovery.research.query_integrity import (
    build_preview_queries,
    evaluate_query_quality,
    research_questions_for_queries,
)
from reinaluxe_recovery.research.screening import (
    classify_source_lane_details,
    normalize_source_url,
    qualify_visual_candidate,
    raw_images,
    screen_source_candidate,
)

SMOKE_MAX_CALLS = 3
SMOKE_MAX_RESULTS_PER_CALL = 15
SMOKE_MAX_RAW_RESULTS = 45
SMOKE_MAX_RETAINED_SOURCES = 20

SMOKE_OUTPUTS = (
    "smoke-executive-report.md",
    "smoke-validation.json",
    "provider-call-register.csv",
    "query-results-register.csv",
    "retained-source-register.csv",
    "source-exclusion-register.csv",
    "duplicate-source-register.csv",
    "candidate-claims.csv",
    "source-to-claim-map.csv",
    "contradiction-register.csv",
    "insufficient-evidence-register.csv",
    "image-source-candidates.csv",
    "visual-page-candidates.csv",
    "assertive-narrative-register.csv",
    "publication-wording-options.csv",
    "full-run-recommendation.md",
)

_LANE_TERMS = {
    SourceLane.COMMUNITY_REDDIT: "site:reddit.com/r/ comments",
    SourceLane.COMMUNITY_FORUMS: "public forum community discussion",
    SourceLane.PRIMARY_OFFICIAL: "official primary source",
    SourceLane.EXPERT_EDITORIAL: "expert editorial analysis",
    SourceLane.COMMERCIAL_OBSERVATION: "public commercial listing observation",
    SourceLane.VISUAL_IMAGE: "source-linked photos image comparison",
}
_EVIDENCE_TYPE = {
    SourceLane.COMMUNITY_REDDIT: "public Reddit post observations",
    SourceLane.COMMUNITY_FORUMS: "public non-Reddit community observations",
    SourceLane.PRIMARY_OFFICIAL: "official factual or terminology reference",
    SourceLane.EXPERT_EDITORIAL: "attributed expert context",
    SourceLane.COMMERCIAL_OBSERVATION: "scoped commercial observation",
    SourceLane.VISUAL_IMAGE: "provider-returned visual metadata",
}
_FAMILY_STOPWORDS = {"and", "the", "limits", "evidence", "about"}
_REDDIT_USERNAME = re.compile(r"(?<![\w/])(?:u/|/u/)[A-Za-z0-9_-]+", re.IGNORECASE)
_REDDIT_PROFILE_URL = re.compile(r"(reddit\.com/(?:user|u)/)[^/?#]+", re.IGNORECASE)


def research_smoke(
    request_path: Path,
    query_families: list[str],
    output: Path,
    *,
    research_database: Path,
    glm_assisted: bool,
    provider: ResearchSearchProvider | None = None,
    analyzer: SourceAnalysisProvider | None = None,
) -> dict[str, Any]:
    """Run at most three provider calls and export an honest coverage assessment."""
    prepare_output(output)
    request = load_research_request(request_path).model_copy(
        update={
            "maximum_search_calls": SMOKE_MAX_CALLS,
            "maximum_sources": SMOKE_MAX_RETAINED_SOURCES,
            "maximum_image_candidates": SMOKE_MAX_RETAINED_SOURCES,
            "research_database_path": research_database,
            "request_hash": None,
        }
    )
    plan = _build_smoke_plan(build_research_plan(request), query_families)
    selected_provider = provider or default_provider_registry().create(plan.provider)
    if selected_provider.provider_name.casefold() != plan.provider.casefold():
        raise ResearchConfigurationError(
            f"plan provider {plan.provider!r} does not match "
            f"{selected_provider.provider_name!r}"
        )
    selected_analyzer = analyzer or (ZhipuGLMSourceAnalyzer() if glm_assisted else None)
    result = _execute_discovery(plan, selected_provider)
    bundle: ResearchAnalysisBundle | None = None
    analysis_error = ""
    structured_valid = not glm_assisted
    if result["configuration_failed"]:
        recommendation = SmokeRecommendation.CONFIGURATION_FAILED
    else:
        try:
            bundle = analyze_search_run(result["run"], plan, selected_analyzer)
            structured_valid = True
        except (ResearchError, ValidationError, ValueError) as error:
            analysis_error = _safe_error(error)
            recommendation = SmokeRecommendation.ANALYSIS_FAILED
        else:
            recommendation = _recommendation(
                result["run"], bundle, result["provider_failed"], structured_valid
            )
    validation = _export_smoke(
        output,
        plan,
        result,
        bundle,
        recommendation,
        structured_valid=structured_valid,
        glm_assisted=glm_assisted,
        analysis_error=analysis_error,
    )
    return validation


def _build_smoke_plan(plan: ResearchPlan, requested: list[str]) -> ResearchPlan:
    queries = build_preview_queries(plan, requested, maximum_results=15)
    draft = plan.model_copy(
        update={
            "questions": research_questions_for_queries(queries),
            "queries": queries,
            "maximum_search_calls": SMOKE_MAX_CALLS,
            "maximum_sources": SMOKE_MAX_RETAINED_SOURCES,
            "maximum_image_candidates": SMOKE_MAX_RETAINED_SOURCES,
            "plan_hash": None,
        }
    )
    return draft.model_copy(
        update={
            "plan_hash": content_hash(
                draft.model_dump(mode="json", exclude={"plan_hash"})
            )
        }
    )


def _match_family(value: str, available: dict[str, Any]) -> tuple[str, Any]:
    requested = _family_tokens(value)
    ranked = sorted(
        (
            (
                len(requested & _family_tokens(family)),
                requested <= _family_tokens(family),
                family,
                question,
            )
            for family, question in available.items()
        ),
        key=lambda item: (-int(item[1]), -item[0], item[2].casefold()),
    )
    if not ranked or ranked[0][0] == 0:
        raise ResearchConfigurationError(f"unknown smoke query family: {value}")
    return ranked[0][2], ranked[0][3]


def _family_tokens(value: str) -> set[str]:
    return {
        item
        for item in re.findall(r"[a-z0-9]+", value.casefold().replace("_", " "))
        if item not in _FAMILY_STOPWORDS
    }


def _execute_discovery(
    plan: ResearchPlan, provider: ResearchSearchProvider
) -> dict[str, Any]:
    call_rows: list[dict[str, Any]] = []
    result_rows: list[dict[str, Any]] = []
    exclusion_rows: list[dict[str, Any]] = []
    duplicate_rows: list[dict[str, Any]] = []
    sources: list[SourceCandidate] = []
    images: list[ImageCandidate] = []
    visual_pages: list[VisualPageCandidate] = []
    seen_urls: dict[str, str] = {}
    seen_content: dict[str, str] = {}
    seen_images: set[str] = set()
    provider_urls: set[str] = set()
    processed_raw = 0
    returned_raw = 0
    provider_failed = False
    configuration_failed = False
    policy_by_lane = {item.source_lane: item for item in plan.source_lane_policies}
    failed_quality = [
        (query, evaluate_query_quality(query, plan.queries))
        for query in plan.queries[:SMOKE_MAX_CALLS]
    ]
    failed_quality = [
        (query, quality)
        for query, quality in failed_quality
        if not (quality.passed and quality.retrieval_quality_passed)
    ]
    if failed_quality:
        provider_failed = True
        for call_index, (query, quality) in enumerate(failed_quality, start=1):
            call_rows.append(
                {
                    "call_index": call_index,
                    **_provider_call_query_fields(query),
                    "returned_raw_results": 0,
                    "processed_results": 0,
                    "status": "query_quality_failed",
                    "error": "; ".join(quality.failure_reasons),
                    "retry_count": 0,
                }
            )
    else:
        try:
            provider.validate_configuration()
        except ResearchConfigurationError as error:
            configuration_failed = True
            call_rows.append(
                {
                    "call_index": 0,
                    "status": "configuration_failed",
                    "error": _safe_error(error),
                    "retry_count": 0,
                }
            )
    if not configuration_failed and not failed_quality:
        for call_index, query in enumerate(plan.queries[:SMOKE_MAX_CALLS], start=1):
            retrieved_at = datetime.now(UTC).isoformat()
            requested_limit = min(
                SMOKE_MAX_RESULTS_PER_CALL,
                query.maximum_results,
                int(provider.capabilities().get("requested_result_count", 15)),
            )
            try:
                response = provider.execute_query(query)
                raw_count = _raw_provider_count(response)
                normalized = provider.normalize_results(query, response)
            except (ResearchError, ValueError) as error:
                provider_failed = True
                call_rows.append(
                    {
                        "call_index": call_index,
                        **_provider_call_query_fields(query),
                        "requested_result_limit": requested_limit,
                        "returned_raw_results": 0,
                        "processed_results": 0,
                        "status": "provider_failed",
                        "error": _safe_error(error),
                        "retry_count": 0,
                    }
                )
                break
            returned_raw += raw_count
            remaining = SMOKE_MAX_RAW_RESULTS - processed_raw
            selected_results = normalized[: min(requested_limit, remaining)]
            processed_raw += len(selected_results)
            call_rows.append(
                {
                    "call_index": call_index,
                    **_provider_call_query_fields(query),
                    "requested_result_limit": requested_limit,
                    "returned_raw_results": raw_count,
                    "processed_results": len(selected_results),
                    "status": "completed",
                    "error": "",
                    "retry_count": 0,
                }
            )
            for rank, provider_result in enumerate(selected_results):
                raw = dict(provider_result)
                raw.setdefault("provider", provider.provider_name)
                raw.setdefault("retrieved_at", retrieved_at)
                raw.setdefault(
                    "provider_result_id",
                    stable_id(
                        "provider_result",
                        {
                            "query_id": query.query_id,
                            "rank": rank,
                            "url": raw.get("url"),
                        },
                    ),
                )
                raw_url = str(raw.get("url") or "")
                try:
                    provider_urls.add(normalize_source_url(raw_url))
                except ValueError:
                    pass
                candidate, reason = screen_source_candidate(query, raw, policy_by_lane)
                status = "excluded"
                source_id = ""
                if candidate is not None:
                    normalized_url = str(candidate.normalized_url)
                    content_key = _content_key(candidate)
                    duplicate_of = seen_urls.get(normalized_url)
                    duplicate_reason = "exact_duplicate_url"
                    if duplicate_of is None and content_key:
                        duplicate_of = seen_content.get(content_key)
                        duplicate_reason = "identical_title_snippet_duplicate"
                    if duplicate_of is not None:
                        reason = duplicate_reason
                        duplicate_rows.append(
                            {
                                "query_id": query.query_id,
                                "provider_result_id": raw["provider_result_id"],
                                "url": _owner_safe(raw_url),
                                "duplicate_reason": duplicate_reason,
                                "duplicate_of_source_id": duplicate_of,
                            }
                        )
                    elif len(sources) >= SMOKE_MAX_RETAINED_SOURCES:
                        reason = "maximum_retained_sources_reached"
                    else:
                        status = "retained"
                        source_id = candidate.source_id
                        seen_urls[normalized_url] = candidate.source_id
                        if content_key:
                            seen_content[content_key] = candidate.source_id
                        sources.append(candidate)
                        visual_inputs = raw_images(raw)
                        provider_metadata = raw.get("provider_metadata")
                        if not visual_inputs and isinstance(provider_metadata, dict):
                            media = provider_metadata.get("media")
                            if media:
                                visual_inputs = [{"media": media}]
                        for raw_image in visual_inputs:
                            if len(images) >= plan.maximum_image_candidates:
                                break
                            image, visual_page = qualify_visual_candidate(
                                candidate, raw_image
                            )
                            if image is not None:
                                image_key = str(
                                    image.normalized_image_url or image.image_locator
                                )
                                if image_key in seen_images:
                                    continue
                                seen_images.add(image_key)
                                images.append(
                                    image.model_copy(
                                        update={
                                            "brand": None,
                                            "model": None,
                                            "target_topic": query.query_family,
                                            "proposed_article_section": query.target_article_section,
                                        }
                                    )
                                )
                            elif visual_page is not None:
                                visual_pages.append(visual_page)
                if status == "excluded":
                    exclusion_rows.append(
                        {
                            "query_id": query.query_id,
                            "provider_result_id": raw["provider_result_id"],
                            "url": _owner_safe(raw_url),
                            "reason": reason or "invalid_source",
                        }
                    )
                classification = None
                try:
                    classification = classify_source_lane_details(
                        normalize_source_url(raw_url), query.brand_scope
                    )
                except ValueError:
                    pass
                result_rows.append(
                    {
                        "provider_result_id": raw["provider_result_id"],
                        "query_id": query.query_id,
                        "query_family": query.query_family,
                        "title": _owner_safe(raw.get("title")),
                        "url": _owner_safe(raw_url),
                        "snippet_or_content": _owner_safe(raw.get("snippet")),
                        "media_fields": raw.get("images")
                        or raw.get("provider_metadata")
                        or [],
                        "published_at": raw.get("published_at"),
                        "retrieved_at": raw.get("retrieved_at"),
                        "requested_source_lane": query.requested_source_lane.value,
                        "classified_source_lane": (
                            candidate.classified_source_lane.value
                            if candidate is not None
                            else classification.lane.value
                            if classification
                            else ""
                        ),
                        "classification_rule": (
                            candidate.classification_rule
                            if candidate is not None
                            else classification.rule
                            if classification
                            else "invalid_url"
                        ),
                        "classification_confidence": (
                            candidate.classification_confidence
                            if candidate is not None
                            else classification.confidence
                            if classification
                            else 0
                        ),
                        "classification_override_status": (
                            candidate.classification_override_status
                            if candidate is not None
                            else (
                                "requested_lane_confirmed"
                                if classification
                                and classification.lane is query.requested_source_lane
                                else "classified_lane_overridden"
                            )
                        ),
                        "provider_access_classification": raw.get(
                            "provider_access_classification",
                            "provider_returned_snippet",
                        ),
                        "status": status,
                        "source_id": source_id,
                        "exclusion_reason": reason if status == "excluded" else "",
                    }
                )
    run_base = {
        "search_run_id": stable_id(
            "smoke_run", {"research_id": plan.research_id, "plan_hash": plan.plan_hash}
        ),
        "research_id": plan.research_id,
        "plan_hash": plan.plan_hash,
        "provider": provider.provider_name,
        "query_ids": [row["query_id"] for row in call_rows if row.get("query_id")],
        "queries": plan.queries,
        "source_candidates": sorted(sources, key=lambda item: item.source_id),
        "image_candidates": sorted(images, key=lambda item: item.image_id),
        "visual_page_candidates": sorted(
            visual_pages, key=lambda item: item.visual_page_candidate_id
        ),
        "exclusions": exclusion_rows,
        "usage": {
            **dict(provider.report_usage()),
            "returned_raw_results": returned_raw,
            "processed_raw_results": processed_raw,
            "retry_count": 0,
        },
    }
    draft = SearchRun.model_validate(run_base)
    run = draft.model_copy(
        update={
            "run_hash": content_hash(
                draft.model_dump(mode="json", exclude={"run_hash"})
            )
        }
    )
    return {
        "run": run,
        "call_rows": call_rows,
        "result_rows": result_rows,
        "exclusion_rows": exclusion_rows,
        "duplicate_rows": duplicate_rows,
        "provider_urls": provider_urls,
        "processed_raw_results": processed_raw,
        "returned_raw_results": returned_raw,
        "provider_failed": provider_failed,
        "configuration_failed": configuration_failed,
    }


def _export_smoke(
    output: Path,
    plan: ResearchPlan,
    result: dict[str, Any],
    bundle: ResearchAnalysisBundle | None,
    recommendation: SmokeRecommendation,
    *,
    structured_valid: bool,
    glm_assisted: bool,
    analysis_error: str,
) -> dict[str, Any]:
    run: SearchRun = result["run"]
    claims = bundle.candidate_claims if bundle else []
    links = bundle.claim_evidence_links if bundle else []
    contradictions = bundle.contradictions if bundle else []
    synthesis = build_editorial_synthesis(plan, bundle) if bundle else []
    evidence = bundle.source_evidence_records if bundle else []
    insufficient = _insufficient_rows(bundle)
    source_counts = Counter(item.source_lane for item in run.source_candidates)
    domain_counts = Counter(item.domain for item in run.source_candidates)
    reddit_count = source_counts[SourceLane.COMMUNITY_REDDIT]
    non_reddit_community = source_counts[SourceLane.COMMUNITY_FORUMS]
    official_expert = (
        source_counts[SourceLane.PRIMARY_OFFICIAL]
        + source_counts[SourceLane.EXPERT_EDITORIAL]
    )
    image_source_count = len({item.source_id for item in run.image_candidates})
    promotional_risk = sum(
        item.commercial_promotion_risk in {"medium", "high"} for item in evidence
    )
    calls_made = sum(row.get("query_id") is not None for row in result["call_rows"])
    duplicate_count = len(result["duplicate_rows"])
    processed_raw = result["processed_raw_results"]
    traceability = bool(claims) and all(
        any(link.claim_id == claim.claim_id for link in links) for claim in claims
    )
    retained_provider_urls = all(
        str(item.normalized_url) in result["provider_urls"]
        for item in run.source_candidates
    )
    targets = {
        "at_least_five_retained_sources": len(run.source_candidates) >= 5,
        "at_least_two_source_lanes": len(source_counts) >= 2,
        "at_least_three_reddit_posts_when_available": (
            reddit_count >= 3
            if any(
                "reddit.com" in str(row.get("url", "")) for row in result["result_rows"]
            )
            else True
        ),
        "at_least_one_non_reddit_public_source": (
            len(run.source_candidates) - reddit_count >= 1
        ),
        "at_least_one_visual_source": image_source_count >= 1,
        "at_least_three_candidate_claims": len(claims) >= 3,
        "contradiction_limitation_or_shortfall_present": bool(
            contradictions or insufficient
        ),
        "claim_to_source_traceability_valid": traceability,
        "structured_glm_output_valid": structured_valid,
    }
    validation = {
        "schema_version": "1.0",
        "research_id": plan.research_id,
        "recommendation": recommendation.value,
        "calls_made": calls_made,
        "raw_results_processed": processed_raw,
        "raw_results_returned": result["returned_raw_results"],
        "retained_sources": len(run.source_candidates),
        "source_lane_count": len(source_counts),
        "reddit_sources": reddit_count,
        "non_reddit_community_sources": non_reddit_community,
        "official_expert_sources": official_expert,
        "image_containing_sources": image_source_count,
        "image_candidates": len(run.image_candidates),
        "duplicate_sources": duplicate_count,
        "candidate_claims": len(claims),
        "contradictions": len(contradictions),
        "evidence_shortfalls": len(insufficient),
        "promotional_risk_count": promotional_risk,
        "targets": targets,
        "hard_limits": {
            "maximum_search_calls": SMOKE_MAX_CALLS,
            "maximum_results_requested_per_call": SMOKE_MAX_RESULTS_PER_CALL,
            "maximum_raw_results_processed": SMOKE_MAX_RAW_RESULTS,
            "maximum_retained_sources": SMOKE_MAX_RETAINED_SOURCES,
            "search_call_limit_respected": calls_made <= SMOKE_MAX_CALLS,
            "result_limit_respected": processed_raw <= SMOKE_MAX_RAW_RESULTS,
            "retained_source_limit_respected": len(run.source_candidates)
            <= SMOKE_MAX_RETAINED_SOURCES,
            "automatic_fallback_used": False,
            "retry_count": 0,
        },
        "source_integrity": {
            "all_retained_urls_provider_returned": retained_provider_urls,
            "model_generated_source_urls": False,
            "direct_result_page_fetches": 0,
            "direct_reddit_requests": 0,
            "browser_automation_used": False,
            "images_downloaded": False,
            "claim_to_source_traceability_valid": traceability,
            "structured_glm_output_valid": structured_valid,
        },
        "safety": {
            "wordpress_modified": False,
            "article_modified": False,
            "article_drafted": False,
            "full_aaa_pilot_run": False,
            "production_sqlite_modified": False,
            "invented_measurements": False,
            "fabricated_physical_experience": False,
            "credentials_serialized": False,
        },
        "glm_assisted": glm_assisted,
        "analysis_error": analysis_error,
    }
    _write_smoke_csvs(
        output, result, run, bundle, insufficient, synthesis, domain_counts
    )
    write_json(output / "smoke-validation.json", validation)
    duplicate_rate = duplicate_count / processed_raw if processed_raw else 0.0
    write_text(
        output / "smoke-executive-report.md",
        (
            f"# AAA research smoke executive report\n\n"
            f"- Calls made: {calls_made}\n"
            f"- Raw provider results processed: {processed_raw}\n"
            f"- Valid retained sources: {len(run.source_candidates)}\n"
            f"- Reddit post sources: {reddit_count}\n"
            f"- Non-Reddit public community sources: {non_reddit_community}\n"
            f"- Official or expert sources: {official_expert}\n"
            f"- Image-containing sources: {image_source_count}\n"
            f"- Image candidates: {len(run.image_candidates)}\n"
            f"- Duplicate rate: {duplicate_rate:.1%}\n"
            f"- Promotional-risk records: {promotional_risk}\n"
            f"- Candidate claims: {len(claims)}\n"
            f"- Contradictions: {len(contradictions)}\n"
            f"- Evidence shortfalls: {len(insufficient)}\n"
            f"- Full-run recommendation: `{recommendation.value}`\n\n"
            "This smoke run used provider-returned metadata only. It did not crawl result "
            "pages, request Reddit directly, download images, draft or modify the AAA page, "
            "run the full pilot, access WordPress, or write the production database.\n"
        ),
    )
    unmet = [name for name, met in targets.items() if not met]
    write_text(
        output / "full-run-recommendation.md",
        (
            f"# Full-run recommendation\n\n`{recommendation.value}`\n\n"
            + (
                "Unmet smoke targets:\n\n"
                + "\n".join(f"- {item}" for item in unmet)
                + "\n"
                if unmet
                else "All smoke coverage targets were met.\n"
            )
        ),
    )
    missing = [name for name in SMOKE_OUTPUTS if not (output / name).is_file()]
    if missing:
        raise ResearchError(
            "smoke export omitted required outputs: " + ", ".join(missing)
        )
    return validation


def _write_smoke_csvs(
    output: Path,
    result: dict[str, Any],
    run: SearchRun,
    bundle: ResearchAnalysisBundle | None,
    insufficient: list[dict[str, Any]],
    synthesis: list[Any],
    domain_counts: Counter[str],
) -> None:
    write_csv(
        output / "provider-call-register.csv",
        [
            "call_index",
            "query_id",
            "query_family",
            "exact_search_query",
            "requested_source_lane",
            "search_domain_filter",
            "maximum_results",
            "query_anchor_terms",
            "query_exclusion_terms",
            "requested_result_limit",
            "returned_raw_results",
            "processed_results",
            "status",
            "error",
            "retry_count",
        ],
        result["call_rows"],
    )
    write_csv(
        output / "query-results-register.csv",
        [
            "provider_result_id",
            "query_id",
            "query_family",
            "title",
            "url",
            "snippet_or_content",
            "media_fields",
            "published_at",
            "retrieved_at",
            "requested_source_lane",
            "classified_source_lane",
            "classification_rule",
            "classification_confidence",
            "classification_override_status",
            "provider_access_classification",
            "status",
            "source_id",
            "exclusion_reason",
        ],
        result["result_rows"],
    )
    write_csv(
        output / "retained-source-register.csv",
        [
            *SourceCandidate.model_fields,
            "repeated_domain_count",
        ],
        [
            {
                **item.model_dump(mode="json"),
                "title": _owner_safe(item.title),
                "snippet": _owner_safe(item.snippet),
                "repeated_domain_count": domain_counts[item.domain],
            }
            for item in run.source_candidates
        ],
    )
    write_csv(
        output / "source-exclusion-register.csv",
        ["query_id", "provider_result_id", "url", "reason"],
        result["exclusion_rows"],
    )
    write_csv(
        output / "duplicate-source-register.csv",
        [
            "query_id",
            "provider_result_id",
            "url",
            "duplicate_reason",
            "duplicate_of_source_id",
        ],
        result["duplicate_rows"],
    )
    claims = bundle.candidate_claims if bundle else []
    links = bundle.claim_evidence_links if bundle else []
    contradictions = bundle.contradictions if bundle else []
    write_csv(
        output / "candidate-claims.csv",
        _fields(claims),
        [item.model_dump(mode="json") for item in claims],
    )
    write_csv(
        output / "source-to-claim-map.csv",
        _fields(links),
        [item.model_dump(mode="json") for item in links],
    )
    write_csv(
        output / "contradiction-register.csv",
        _fields(contradictions),
        [item.model_dump(mode="json") for item in contradictions],
    )
    write_csv(
        output / "insufficient-evidence-register.csv",
        ["record_id", "claim_id", "assessment", "source_ids", "limitation"],
        insufficient,
    )
    write_csv(
        output / "image-source-candidates.csv",
        list(ImageCandidate.model_fields),
        [item.model_dump(mode="json") for item in run.image_candidates],
    )
    write_csv(
        output / "visual-page-candidates.csv",
        list(VisualPageCandidate.model_fields),
        [item.model_dump(mode="json") for item in run.visual_page_candidates],
    )
    write_csv(
        output / "assertive-narrative-register.csv",
        _fields(synthesis),
        [item.model_dump(mode="json") for item in synthesis],
    )
    write_csv(
        output / "publication-wording-options.csv",
        [
            "synthesis_id",
            "restrained",
            "assertive",
            "highly_assertive_but_supportable",
            "allowed",
            "selected",
        ],
        [
            {
                "synthesis_id": item.synthesis_id,
                "restrained": item.restrained_wording,
                "assertive": item.assertive_wording,
                "highly_assertive_but_supportable": item.highly_assertive_but_supportable_wording,
                "allowed": item.publication_intensity_allowed.value,
                "selected": item.selected_publication_wording,
            }
            for item in synthesis
        ],
    )


def _insufficient_rows(
    bundle: ResearchAnalysisBundle | None,
) -> list[dict[str, Any]]:
    rows = [
        {
            "record_id": item.cluster_id,
            "claim_id": item.canonical_claim_id,
            "assessment": item.assessment.value,
            "source_ids": item.supporting_source_ids,
            "limitation": "; ".join(item.limitations),
        }
        for item in (bundle.claim_clusters if bundle else [])
        if item.assessment
        in {EvidenceAssessment.SINGLE_SOURCE, EvidenceAssessment.INSUFFICIENT}
    ]
    rows.append(
        {
            "record_id": "provider-snippet-scope",
            "claim_id": "",
            "assessment": "method_limit",
            "source_ids": [],
            "limitation": (
                "The smoke workflow analyzed provider-returned snippets and metadata without "
                "fetching result pages."
            ),
        }
    )
    return rows


def _recommendation(
    run: SearchRun,
    bundle: ResearchAnalysisBundle,
    provider_failed: bool,
    structured_valid: bool,
) -> SmokeRecommendation:
    lane_count = len({item.source_lane for item in run.source_candidates})
    if provider_failed or len(run.source_candidates) < 5 or lane_count < 2:
        return SmokeRecommendation.PROVIDER_COVERAGE_INSUFFICIENT
    reddit = sum(
        item.source_lane is SourceLane.COMMUNITY_REDDIT
        for item in run.source_candidates
    )
    non_reddit = len(run.source_candidates) - reddit
    images = len({item.source_id for item in run.image_candidates})
    if (
        reddit >= 3
        and non_reddit >= 1
        and images >= 1
        and len(bundle.candidate_claims) >= 3
        and structured_valid
    ):
        return SmokeRecommendation.FULL_RUN_RECOMMENDED
    return SmokeRecommendation.FULL_RUN_RECOMMENDED_WITH_ADJUSTMENTS


def _content_key(candidate: SourceCandidate) -> str:
    value = normalize_text(
        " | ".join(item for item in (candidate.title, candidate.snippet) if item)
    ).casefold()
    return content_hash(value) if value else ""


def _provider_call_query_fields(query: ResearchQuery) -> dict[str, Any]:
    return {
        "query_id": query.query_id,
        "query_family": query.query_family,
        "exact_search_query": query.exact_search_query,
        "requested_source_lane": query.requested_source_lane.value,
        "search_domain_filter": query.search_domain_filter or "",
        "maximum_results": query.maximum_results,
        "query_anchor_terms": query.query_anchor_terms,
        "query_exclusion_terms": query.query_exclusion_terms,
        "requested_result_limit": query.maximum_results,
    }


def _raw_provider_count(response: Any) -> int:
    items = response
    if isinstance(response, dict):
        items = response.get("search_result", response.get("results", []))
        if isinstance(items, dict):
            items = items.get("items", [])
    return len(items) if isinstance(items, list) else 0


def _owner_safe(value: Any) -> str:
    if value is None:
        return ""
    text = _REDDIT_USERNAME.sub("[redacted-user]", str(value))
    return _REDDIT_PROFILE_URL.sub(r"\1[redacted-user]", text)


def _safe_error(error: Exception) -> str:
    return normalize_text(str(error))[:300]


def _fields(records: list[Any]) -> list[str]:
    return list(type(records[0]).model_fields) if records else ["schema_version"]
