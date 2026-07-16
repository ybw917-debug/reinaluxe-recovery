from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from reinaluxe_recovery.research.artifacts import load_research_request
from reinaluxe_recovery.research.contracts import ResearchQuery, SourceLane
from reinaluxe_recovery.research.exploratory import (
    DeterministicExploratoryAnalysisProvider,
    ExploratoryAnalysisProvider,
    ExploratoryQuery,
    build_exploratory_query_universe,
    run_exploratory_research,
    score_source_utility,
)
from reinaluxe_recovery.research.providers.base import ResearchSearchProvider


def _request(tmp_path: Path, production: Path) -> Path:
    article = tmp_path / "article.json"
    article.write_text(
        json.dumps(
            {
                "title": "AAA Replica Bags Guide",
                "sections": [
                    {
                        "heading": {"level": 1, "text": "AAA terminology"},
                        "paragraphs": [
                            {"text": "Existing owner-authored introduction."}
                        ],
                    },
                    {
                        "heading": {"level": 2, "text": "PSP and QC limitations"},
                        "paragraphs": [{"text": "Existing visual-evidence context."}],
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    request = tmp_path / "request.json"
    request.write_text(
        json.dumps(
            {
                "research_id": "aaa-exploratory-synthetic",
                "content_production_mode": "legacy_reconstruction",
                "target_article_url": "https://example.test/aaa-guide/",
                "article_source_path": str(article),
                "production_database_path": str(production),
                "owner_objective": "Broadly enrich the existing AAA guide.",
                "target_audience": "readers evaluating informal quality language",
                "source_lane_priorities": [
                    {
                        "source_lane": lane,
                        "priority": index,
                        "query_quota": 20,
                        "source_quota": 50,
                    }
                    for index, lane in enumerate(
                        (
                            "community_reddit",
                            "community_forums",
                            "expert_editorial",
                            "primary_official",
                            "commercial_observation",
                            "visual_image",
                        ),
                        start=1,
                    )
                ],
                "maximum_search_calls": 20,
                "maximum_sources": 50,
                "maximum_image_candidates": 0,
                "first_round_call_budget": 6,
                "second_round_call_budget": 2,
                "total_call_budget": 8,
                "output_directory": str(tmp_path / "unused"),
                "provider": "lane-routed",
            }
        ),
        encoding="utf-8",
    )
    return request


class SyntheticSearchProvider(ResearchSearchProvider):
    def __init__(self, name: str) -> None:
        self.provider_name = name
        self.calls: list[str] = []

    def validate_configuration(self) -> None:
        return None

    def capabilities(self) -> dict[str, Any]:
        return {"requested_result_count": 10}

    def execute_query(self, query: ResearchQuery) -> ResearchQuery:
        self.calls.append(query.query_id)
        return query

    def normalize_results(
        self, query: ResearchQuery, response: Any
    ) -> list[dict[str, Any]]:
        del response
        family = str(query.query_family)
        base = query.query_id[-8:]
        phrase = query.exact_search_query
        return [
            {
                "provider_result_id": f"{base}-community",
                "url": f"https://forum.example.test/thread/{base}",
                "title": f"Buyer discussion about {family}",
                "snippet": f"{phrase}. Buyers report that labels vary, however photos and received items can differ.",
            },
            {
                "provider_result_id": f"{base}-commercial",
                "url": f"https://shop.example.test/products/{base}",
                "title": f"Seller terminology for {family}",
                "snippet": f"{phrase}. Shop now. Product catalog uses premium tier and original leather claims.",
            },
            {
                "provider_result_id": f"{base}-editorial",
                "url": f"https://editorial.example.test/analysis/{base}",
                "title": f"Inspection analysis for {family}",
                "snippet": f"{phrase}. Lighting, leather finish, stitching and batch sampling limit broad conclusions.",
            },
        ]

    def report_usage(self) -> dict[str, Any]:
        return {"query_calls": len(self.calls)}


class SyntheticAnalyzer(ExploratoryAnalysisProvider):
    def __init__(self) -> None:
        self.delegate = DeterministicExploratoryAnalysisProvider()
        self.expansion_calls = 0
        self.stages: list[str] = []

    def expand_queries(
        self, sources: list[Any], *, maximum_queries: int
    ) -> list[dict[str, Any]]:
        self.expansion_calls += 1
        return self.delegate.expand_queries(sources, maximum_queries=maximum_queries)

    def run_stage(self, stage: str, context: dict[str, Any]) -> list[dict[str, Any]]:
        self.stages.append(stage)
        records = self.delegate.run_stage(stage, context)
        if stage == "publication_module_generation" and records:
            records.append(
                {
                    "module_id": "fabricated-module",
                    "target_section": "Unsafe",
                    "reader_question": "Can this be claimed?",
                    "proposed_heading": "Our Test",
                    "paragraphs": [
                        "We handled and measured this bag at 999 grams. Buy from the seller at https://invented.example."
                    ],
                    "supporting_source_ids": records[0]["supporting_source_ids"],
                    "synthesis_type": "editorial_inference",
                    "confidence": 0.9,
                    "limitation": "",
                    "internal_link_opportunity": "",
                    "image_opportunity": "",
                    "expected_reader_value": "",
                }
            )
        return records


def _csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def test_legacy_defaults_to_exploratory_and_builds_broad_query_universe(
    tmp_path: Path,
) -> None:
    production = tmp_path / "production.sqlite"
    production.write_bytes(b"protected")
    request = load_research_request(_request(tmp_path, production))
    assert request.mode.value == "exploratory_editorial_research"
    universe = build_exploratory_query_universe(request.research_id)
    assert len({item.query_family for item in universe}) == 12
    assert len(universe) == 36
    assert {item.language for item in universe} >= {"en", "zh-CN"}
    assert all(item.exact_search_query.count('"') <= 2 for item in universe)


def test_utility_scores_preserve_low_reliability_high_query_value() -> None:
    query = ExploratoryQuery(
        query_id="utility-query",
        round=1,
        query_family="materials_and_leather_claims",
        exact_search_query="replica bag original leather tier terminology",
        target_provider="brave-web-search",
        target_lane=SourceLane.COMMERCIAL_OBSERVATION,
        expansion_rationale="Test commercial language.",
        expected_information_gain="Find unstable seller terminology.",
        query_style="commercial-language",
    )
    score = score_source_utility(
        query,
        title="Original leather replica bag tier catalog",
        snippet="New seller vocabulary compares mirror and premium grade claims.",
        classified_lane=SourceLane.COMMERCIAL_OBSERVATION,
        seen_terms=set(),
    )
    assert score.factual_reliability == 0.2
    assert score.query_expansion_value >= 0.6
    assert score.terminology_value >= 0.8


def test_two_round_workflow_retains_commercial_and_generates_safe_outputs(
    tmp_path: Path,
) -> None:
    production = tmp_path / "production.sqlite"
    production.write_bytes(b"synthetic protected production bytes")
    before = production.read_bytes()
    brave = SyntheticSearchProvider("brave-web-search")
    zhipu = SyntheticSearchProvider("zhipu")
    analyzer = SyntheticAnalyzer()
    output = tmp_path / "exploratory"
    validation = run_exploratory_research(
        _request(tmp_path, production),
        output,
        providers={"brave-web-search": brave, "zhipu-web-search": zhipu},
        analyzer=analyzer,
        first_round_calls=6,
        second_round_calls=2,
    )
    assert validation["discovery_rounds"] == 2
    assert validation["total_calls"] == 8
    assert analyzer.expansion_calls == 1
    assert "publication_module_generation" in analyzer.stages
    assert "overclaim_and_fabrication_review" in analyzer.stages
    calls = _csv(output / "provider-call-register.csv")
    assert len(calls) == 8
    assert all(row["retry_count"] == "0" for row in calls)
    sources = _csv(output / "useful-source-candidates.csv")
    commercial = [
        row for row in sources if row["classified_lane"] == "commercial_observation"
    ]
    assert commercial
    assert all("market_language" in row["allowed_editorial_uses"] for row in commercial)
    assert all(
        "verified_material_claim" in row["prohibited_factual_uses"]
        for row in commercial
    )
    assert _csv(output / "adjacent-domain-connections.csv")
    assert _csv(output / "market-pattern-register.csv")
    assert _csv(output / "editorial-inference-register.csv")
    assert _csv(output / "buyer-guidance-register.csv")
    reviews = _csv(output / "overclaim-review.csv")
    assert any(row["status"] == "rejected" for row in reviews)
    modules = (output / "publication-modules.md").read_text(encoding="utf-8")
    assert "We handled" not in modules
    assert "https://invented.example" not in modules
    assert len(_csv(output / "follow-up-query-plan.csv")) <= 2
    assert production.read_bytes() == before
    for name in (
        "research-landscape.md",
        "discovered-theme-register.csv",
        "market-pattern-register.csv",
        "editorial-inference-register.csv",
        "buyer-guidance-register.csv",
        "contradiction-map.csv",
        "adjacent-domain-connections.csv",
        "follow-up-query-plan.csv",
        "section-enrichment-copy.md",
        "image-analysis-opportunities.csv",
        "publication-modules.md",
        "content-change-manifest.csv",
        "overclaim-review.csv",
    ):
        assert (output / name).is_file(), name
