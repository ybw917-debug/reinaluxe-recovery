"""Offline query previews with no provider construction or execution."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from reinaluxe_recovery.community.io import (
    prepare_output,
    write_csv,
    write_json,
    write_text,
)
from reinaluxe_recovery.community.normalization import content_hash
from reinaluxe_recovery.research.artifacts import load_research_request
from reinaluxe_recovery.research.contracts import QueryQualityRecord, ResearchPlan
from reinaluxe_recovery.research.planning import build_research_plan
from reinaluxe_recovery.research.query_integrity import (
    build_preview_queries,
    evaluate_query_quality,
    provider_request_preview,
    research_questions_for_queries,
)

PREVIEW_OUTPUTS = (
    "query-preview.md",
    "query-preview.csv",
    "query-quality-register.csv",
    "entity-inclusion-register.csv",
    "provider-request-preview.json",
    "validation.json",
)


def preview_queries(
    request_path: Path,
    query_families: list[str],
    output: Path,
) -> dict[str, Any]:
    """Generate exact paid-call previews without constructing a provider."""
    prepare_output(output)
    plan = build_research_plan(load_research_request(request_path))
    queries = build_preview_queries(plan, query_families)
    qualities = [evaluate_query_quality(query, queries) for query in queries]
    preview_plan = _preview_plan(plan, queries)
    _write_preview(output, preview_plan, qualities)
    validation = {
        "schema_version": "1.0",
        "research_id": plan.research_id,
        "valid": all(
            record.passed and record.retrieval_quality_passed for record in qualities
        ),
        "query_count": len(queries),
        "passed_query_count": sum(record.passed for record in qualities),
        "structural_quality_passed_count": sum(record.passed for record in qualities),
        "retrieval_quality_passed_count": sum(
            record.retrieval_quality_passed for record in qualities
        ),
        "provider_calls_made": 0,
        "glm_calls_made": 0,
        "live_search_used": False,
        "all_exact_queries_preserved": all(
            query.search_text == query.exact_search_query for query in queries
        ),
        "all_query_hashes_present": all(bool(query.query_hash) for query in queries),
        "output_files": list(PREVIEW_OUTPUTS),
    }
    write_json(output / "validation.json", validation)
    return validation


def _preview_plan(plan: ResearchPlan, queries: list[Any]) -> ResearchPlan:
    draft = plan.model_copy(
        update={
            "questions": research_questions_for_queries(queries),
            "queries": queries,
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


def _write_preview(
    output: Path,
    plan: ResearchPlan,
    qualities: list[QueryQualityRecord],
) -> None:
    quality_by_id = {record.query_id: record for record in qualities}
    rows = [
        {
            "query_id": query.query_id,
            "query_family": query.query_family,
            "research_question": query.clear_research_question,
            "exact_search_query": query.exact_search_query,
            "requested_source_lane": query.requested_source_lane.value,
            "search_domain_filter": query.search_domain_filter,
            "maximum_results": query.maximum_results,
            "query_anchor_terms": query.query_anchor_terms,
            "query_exclusion_terms": query.query_exclusion_terms,
            "target_article_section": query.target_article_section,
            "article_entities_included": query.article_entities_included,
            "entity_inclusion_rationale": query.entity_inclusion_rationale,
            "query_generation_inputs": query.query_generation_inputs,
            "query_hash": query.query_hash,
            "passed": quality_by_id[query.query_id].passed,
            "retrieval_quality_passed": quality_by_id[
                query.query_id
            ].retrieval_quality_passed,
        }
        for query in plan.queries
    ]
    write_csv(output / "query-preview.csv", list(rows[0]), rows)
    write_csv(
        output / "query-quality-register.csv",
        list(QueryQualityRecord.model_fields),
        [record.model_dump(mode="json") for record in qualities],
    )
    write_csv(
        output / "entity-inclusion-register.csv",
        [
            "query_id",
            "query_family",
            "permitted_article_entities",
            "prohibited_unrelated_entities",
            "article_entities_included",
            "entity_inclusion_rationale",
        ],
        [
            {
                "query_id": query.query_id,
                "query_family": query.query_family,
                "permitted_article_entities": [],
                "prohibited_unrelated_entities": query.prohibited_unrelated_entities,
                "article_entities_included": query.article_entities_included,
                "entity_inclusion_rationale": query.entity_inclusion_rationale,
            }
            for query in plan.queries
        ],
    )
    write_json(
        output / "provider-request-preview.json",
        {
            "schema_version": "1.0",
            "provider": plan.provider,
            "requests": [provider_request_preview(query) for query in plan.queries],
            "provider_calls_made": 0,
        },
    )
    write_text(output / "query-preview.md", _markdown(plan, quality_by_id))


def _markdown(
    plan: ResearchPlan,
    quality_by_id: dict[str, QueryQualityRecord],
) -> str:
    lines = [
        f"# Query preview: {plan.research_id}",
        "",
        "Offline preview only. No provider or GLM call was made.",
        "",
    ]
    for index, query in enumerate(plan.queries, start=1):
        quality = quality_by_id[query.query_id]
        lines.extend(
            [
                f"## Planned call {index}: {query.query_family}",
                "",
                f"- Exact query: `{query.exact_search_query}`",
                f"- Research question: {query.clear_research_question}",
                f"- Requested lane: `{query.requested_source_lane.value}`",
                f"- Domain filter: `{query.search_domain_filter or ''}`",
                f"- Topic anchors: {', '.join(query.query_anchor_terms)}",
                f"- Exclusions: {', '.join(query.query_exclusion_terms)}",
                "- Article entities included: "
                + (", ".join(query.article_entities_included) or "none"),
                f"- Inclusion rationale: {query.entity_inclusion_rationale}",
                f"- Structural quality: `{'PASS' if quality.passed else 'FAIL'}`",
                "- Retrieval quality: "
                f"`{'PASS' if quality.retrieval_quality_passed else 'FAIL'}`",
                f"- Quoted phrases: {quality.quoted_phrase_count} "
                f"({quality.quoted_token_ratio:.1%} of query tokens)",
                "- Retrieval overconstraint risk: "
                f"`{'yes' if quality.retrieval_overconstraint_risk else 'no'}`",
                "- Ambiguous acronyms: "
                + (", ".join(quality.ambiguous_acronyms) or "none"),
                f"- Natural-language query score: {quality.natural_language_query_score:.2f}",
                "",
            ]
        )
    return "\n".join(lines)
