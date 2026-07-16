from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from reinaluxe_recovery.research.artifacts import load_research_request
from reinaluxe_recovery.research.contracts import ResearchQuery
from reinaluxe_recovery.research.planning import build_research_plan
from reinaluxe_recovery.research.preview import preview_queries
from reinaluxe_recovery.research.providers.base import ResearchSearchProvider
from reinaluxe_recovery.research.query_integrity import (
    build_preview_queries,
    evaluate_query_quality,
)
from reinaluxe_recovery.research.screening import discover_sources


class NeverCalledProvider(ResearchSearchProvider):
    provider_name = "zhipu"

    def __init__(self) -> None:
        self.calls = 0

    def validate_configuration(self) -> None:
        return None

    def capabilities(self) -> dict[str, Any]:
        return {"web_search": True}

    def execute_query(self, query: ResearchQuery) -> list[dict[str, Any]]:
        del query
        self.calls += 1
        return []

    def normalize_results(
        self, query: ResearchQuery, response: Any
    ) -> list[dict[str, Any]]:
        del query
        return list(response)

    def report_usage(self) -> dict[str, Any]:
        return {"query_calls": self.calls}


def _queries() -> list[ResearchQuery]:
    request = load_research_request(Path("docs/examples/aaa-pillar-001.yaml"))
    plan = build_research_plan(request)
    return build_preview_queries(plan, ["terminology", "psp_qc", "handmade_provenance"])


def test_final_queries_questions_lanes_and_domains_are_retrieval_oriented() -> None:
    terminology, psp, provenance = _queries()
    assert terminology.exact_search_query == (
        "site:reddit.com/r/ replica bags AAA 1:1 mirror quality superfake "
        "high tier meaning"
    )
    assert terminology.clear_research_question == (
        "What terminology, interpretations and disagreements appear in Reddit "
        "discussions about AAA, 1:1, mirror quality, superfake and replica quality tiers?"
    )
    assert terminology.requested_source_lane.value == "community_reddit"
    assert terminology.search_domain_filter == "reddit.com"
    assert psp.exact_search_query == (
        'replica handbag "pre-shipment photos" PSP QC pictures received item '
        "lighting difference seller photos buyer forum review"
    )
    assert psp.requested_source_lane.value == "community_forums"
    assert psp.search_domain_filter is None
    assert provenance.exact_search_query == (
        'replica handbag handmade "original leather" tannery claims '
        '"leather provenance" verification expert analysis'
    )
    assert provenance.requested_source_lane.value == "expert_editorial"
    assert provenance.search_domain_filter is None
    assert '"handmade replica bag claims"' not in provenance.exact_search_query


def test_research_question_lane_contradiction_fails_retrieval_quality() -> None:
    query = _queries()[0].model_copy(
        update={
            "clear_research_question": (
                "What terminology definitions appear only in non-community sources?"
            )
        }
    )
    quality = evaluate_query_quality(query, [query])
    assert quality.passed is True
    assert quality.research_question_lane_consistency is False
    assert quality.retrieval_quality_passed is False
    assert "research_question_lane_contradiction" in quality.failure_reasons


def test_retrieval_failure_blocks_paid_provider_call() -> None:
    request = load_research_request(Path("docs/examples/aaa-pillar-001.yaml"))
    plan = build_research_plan(request)
    query = _queries()[0].model_copy(
        update={
            "clear_research_question": (
                "What terminology definitions appear only in non-community sources?"
            )
        }
    )
    provider = NeverCalledProvider()
    discover_sources(
        plan.model_copy(
            update={"queries": [query], "provider": provider.provider_name}
        ),
        provider,
    )
    assert provider.calls == 0


def test_excessive_exact_phrase_quoting_is_overconstrained() -> None:
    query = _queries()[0].model_copy(
        update={
            "exact_search_query": (
                'site:reddit.com/r/ "replica bags" "AAA" "1:1" "mirror quality" meaning'
            )
        }
    )
    quality = evaluate_query_quality(query, [query])
    assert quality.passed is True
    assert quality.quoted_phrase_count == 4
    assert quality.retrieval_overconstraint_risk is True
    assert quality.retrieval_quality_passed is False


def test_one_or_two_useful_quoted_phrases_are_acceptable() -> None:
    psp = evaluate_query_quality(_queries()[1], _queries())
    provenance = evaluate_query_quality(_queries()[2], _queries())
    assert psp.quoted_phrase_count == 1
    assert provenance.quoted_phrase_count == 2
    assert psp.retrieval_overconstraint_risk is False
    assert provenance.retrieval_overconstraint_risk is False
    assert psp.retrieval_quality_passed is True
    assert provenance.retrieval_quality_passed is True


def test_ambiguous_psp_without_expansion_fails_retrieval_quality() -> None:
    query = _queries()[1].model_copy(
        update={
            "exact_search_query": (
                "replica handbag PSP QC pictures received item lighting difference "
                "seller photos buyer forum review"
            )
        }
    )
    quality = evaluate_query_quality(query, [query])
    assert quality.passed is True
    assert quality.ambiguous_acronyms == ["PSP"]
    assert quality.ambiguous_acronym_mitigated is False
    assert quality.retrieval_quality_passed is False


def test_psp_expansion_mitigates_acronym_and_natural_queries_pass() -> None:
    qualities = [evaluate_query_quality(query, _queries()) for query in _queries()]
    assert all(quality.passed for quality in qualities)
    assert all(quality.retrieval_quality_passed for quality in qualities)
    assert qualities[0].quoted_phrase_count == 0
    assert qualities[0].natural_language_query_score >= 0.8
    assert qualities[1].ambiguous_acronyms == []
    assert qualities[1].ambiguous_acronym_mitigated is True


def test_preview_has_no_context_contamination_and_makes_zero_calls(
    tmp_path: Path,
) -> None:
    output = tmp_path / "preview"
    validation = preview_queries(
        Path("docs/examples/aaa-pillar-001.yaml"),
        ["terminology", "psp_qc", "handmade_provenance"],
        output,
    )
    assert validation["valid"] is True
    assert validation["provider_calls_made"] == 0
    assert validation["glm_calls_made"] == 0
    assert validation["structural_quality_passed_count"] == 3
    assert validation["retrieval_quality_passed_count"] == 3
    with (output / "query-preview.csv").open(
        "r", encoding="utf-8-sig", newline=""
    ) as handle:
        rows = list(csv.DictReader(handle))
    rendered = " ".join(row["exact_search_query"] for row in rows)
    assert "CarryAll" not in rendered
    assert "CarryAll Vibe" not in rendered
    assert "Louis Vuitton" not in rendered
