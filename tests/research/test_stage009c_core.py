from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

import httpx
import pytest
from pydantic import ValidationError
from typer.testing import CliRunner

from reinaluxe_recovery.cli import app
from reinaluxe_recovery.research.analysis import (
    SourceAnalysisProvider,
    SourceAnalysisResult,
    analyze_search_run,
)
from reinaluxe_recovery.research.artifacts import (
    STANDARD_OUTPUTS,
    export_review_package,
)
from reinaluxe_recovery.research.contracts import (
    ArticleResearchRequest,
    ResearchPlan,
    ResearchQuery,
    SourceCandidate,
    TopicResearchRequest,
)
from reinaluxe_recovery.research.database import (
    ResearchTopicDatabase,
    build_research_snapshot,
)
from reinaluxe_recovery.research.errors import ResearchConfigurationError
from reinaluxe_recovery.research.planning import build_research_plan
from reinaluxe_recovery.research.providers import (
    ResearchProviderRegistry,
    ResearchSearchProvider,
    ZhipuWebSearchProvider,
)
from reinaluxe_recovery.research.screening import (
    classify_source_lane,
    discover_sources,
)


def _article(tmp_path: Path) -> Path:
    path = tmp_path / "article.json"
    path.write_text(
        json.dumps(
            {
                "title": "Generic quality guide",
                "sections": [
                    {
                        "heading": {"level": 1, "text": "Generic quality guide"},
                        "paragraphs": [
                            {
                                "text": (
                                    "Every labeled tier always has identical quality. "
                                    "We compared one owner-provided sample."
                                )
                            }
                        ],
                        "images": [],
                        "links": [
                            {"target_url": "https://example.test/internal-guide/"}
                        ],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return path


def _request(tmp_path: Path, *, provider: str = "synthetic") -> ArticleResearchRequest:
    return ArticleResearchRequest.model_validate(
        {
            "research_id": "generic-001",
            "mode": "article_research",
            "target_article_url": "https://example.test/quality-guide/",
            "article_source_path": _article(tmp_path),
            "owner_objective": "Verify definitions and quality-evaluation claims.",
            "target_audience": "careful buyers",
            "source_lane_priorities": [
                {
                    "source_lane": "community_reddit",
                    "priority": 1,
                    "query_quota": 2,
                    "source_quota": 5,
                },
                {
                    "source_lane": "community_forums",
                    "priority": 2,
                    "query_quota": 1,
                    "source_quota": 5,
                },
                {
                    "source_lane": "primary_official",
                    "priority": 3,
                    "query_quota": 1,
                    "source_quota": 5,
                },
                {
                    "source_lane": "visual_image",
                    "priority": 4,
                    "query_quota": 1,
                    "source_quota": 5,
                },
            ],
            "language": "en",
            "alternate_languages": ["zh-CN"],
            "region": "global",
            "brand_scope": ["Example Brand"],
            "excluded_subjects": ["private identities"],
            "image_research_required": True,
            "maximum_search_calls": 5,
            "maximum_sources": 20,
            "maximum_image_candidates": 10,
            "output_directory": tmp_path / "output",
            "provider": provider,
        }
    )


class SyntheticProvider(ResearchSearchProvider):
    provider_name = "synthetic"

    def __init__(self) -> None:
        self.calls = 0

    def validate_configuration(self) -> None:
        return None

    def capabilities(self) -> dict[str, Any]:
        return {"web_search": True}

    def execute_query(self, query: ResearchQuery) -> ResearchQuery:
        self.calls += 1
        return query

    def normalize_results(
        self, query: ResearchQuery, response: Any
    ) -> list[dict[str, Any]]:
        del response
        host = {
            "community_reddit": "www.reddit.com",
            "community_forums": "forum.example.test",
            "primary_official": "standard.example.gov",
            "visual_image": "visual.example.test",
        }[query.source_lane.value]
        path = (
            f"/r/example/comments/{query.query_id[-8:]}/fixture/"
            if query.source_lane.value == "community_reddit"
            else f"/{query.query_id}"
        )
        result = {
            "url": f"https://{host}{path}?utm_source=test",
            "title": f"Scoped public observation {query.query_id}",
            "snippet": (
                "AAA replica quality tiers, PSP QC lighting, and handmade leather provenance "
                "were compared; the method does not always give identical quality."
            ),
            "images": [
                {
                    "url": "https://images.example.test/shared-comparison.jpg",
                    "alt": "source comparison",
                },
                "https://images.example.test/shared-comparison.jpg",
            ],
        }
        duplicate = dict(result)
        duplicate["url"] = result["url"].replace("utm_source=test", "")
        return [result, duplicate, {"title": "missing URL"}]

    def report_usage(self) -> dict[str, Any]:
        return {"provider": self.provider_name, "query_calls": self.calls}


class OpposingAnalyzer(SourceAnalysisProvider):
    def analyze(
        self, source: SourceCandidate, plan: ResearchPlan
    ) -> SourceAnalysisResult:
        del plan
        position = (
            "This method does not show identical quality"
            if "reddit" in source.domain
            else "This method does show identical quality"
        )
        return SourceAnalysisResult(
            relevance=0.9,
            first_hand_status="first_hand",
            specificity=0.8,
            commercial_promotion_risk="low",
            source_access_quality="full",
            evidence_summary=position,
            claims=[position],
            limitations=["scope is limited"],
        )


def test_article_and_topic_request_validation(tmp_path: Path) -> None:
    request = _request(tmp_path)
    assert request.with_request_hash().request_hash
    with pytest.raises(ValidationError, match="article research requires"):
        ArticleResearchRequest.model_validate(
            {
                **request.model_dump(mode="json"),
                "target_article_url": None,
                "article_source_path": None,
            }
        )
    topic = TopicResearchRequest.model_validate(
        {
            **request.model_dump(mode="json"),
            "mode": "topic_build",
            "target_article_url": None,
            "article_source_path": None,
            "topic_ids": ["quality-methodology"],
        }
    )
    assert topic.mode.value == "topic_build"


def test_generic_provider_selection_and_zhipu_secret_redaction() -> None:
    registry = ResearchProviderRegistry()
    registry.register("synthetic", SyntheticProvider)
    assert isinstance(registry.create("synthetic"), SyntheticProvider)
    with pytest.raises(ResearchConfigurationError, match="unknown"):
        registry.create("missing")
    missing = ZhipuWebSearchProvider(environ={})
    with pytest.raises(ResearchConfigurationError, match="ZHIPU_API_KEY"):
        missing.validate_configuration()
    key = "secret-never-serialize"
    configured = ZhipuWebSearchProvider(
        environ={
            "ZHIPU_API_KEY": key,
            "ZHIPU_SEARCH_ENGINE": "search-engine",
            "ZHIPU_SUMMARIZER_MODEL": "glm-model",
        }
    )
    configured.validate_configuration()
    assert key not in repr(configured)
    assert key not in json.dumps(configured.report_usage())


def test_zhipu_request_uses_documented_bounded_payload(tmp_path: Path) -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        return httpx.Response(200, json={"search_result": []})

    provider = ZhipuWebSearchProvider(
        environ={
            "ZHIPU_API_KEY": "test-secret",
            "ZHIPU_SEARCH_ENGINE": "search_std",
            "ZHIPU_SUMMARIZER_MODEL": "glm-test",
        },
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    query = build_research_plan(_request(tmp_path, provider="zhipu")).queries[0]
    provider.execute_query(query)
    assert captured["search_query"] == query.exact_search_query
    assert captured["search_domain_filter"] == "reddit.com"
    assert captured["search_engine"] == "search_std"
    assert captured["search_intent"] is False
    assert captured["search_recency_filter"] == "noLimit"
    assert captured["content_size"] == "high"
    assert "start_date" not in captured and "end_date" not in captured


def test_source_lanes_and_reddit_preference_are_not_reddit_only(
    tmp_path: Path,
) -> None:
    plan = build_research_plan(_request(tmp_path))
    assert plan.source_lane_policies[0].source_lane.value == "community_reddit"
    lanes = {query.source_lane.value for query in plan.queries}
    assert "community_reddit" in lanes
    assert {"community_forums", "primary_official"} <= lanes
    assert (
        classify_source_lane(
            "https://reddit.com/r/example/comments/1", plan.queries[0].source_lane
        ).value
        == "community_reddit"
    )
    assert (
        classify_source_lane(
            "https://forum.example.test/thread/1", plan.queries[0].source_lane
        ).value
        == "community_forums"
    )


def test_query_generation_duplicate_screening_and_image_dedup(tmp_path: Path) -> None:
    plan = build_research_plan(_request(tmp_path))
    assert plan.article_analysis and plan.article_analysis.unsupported_claims
    assert all(query.stopping_criteria for query in plan.queries)
    assert any(query.language == "zh-CN" for query in plan.queries)
    run = discover_sources(plan, SyntheticProvider())
    assert len(run.source_candidates) == len(plan.queries)
    assert len(run.image_candidates) == 1
    reasons = {str(item["reason"]) for item in run.exclusions}
    assert {"missing_url", "exact_duplicate_url"} <= reasons
    assert all(source.query_id for source in run.source_candidates)


def test_claim_traceability_contradiction_and_article_mapping(tmp_path: Path) -> None:
    plan = build_research_plan(_request(tmp_path))
    run = discover_sources(plan, SyntheticProvider())
    bundle = analyze_search_run(run, plan, OpposingAnalyzer())
    assert bundle.candidate_claims
    linked = {link.claim_id for link in bundle.claim_evidence_links}
    assert linked == {claim.claim_id for claim in bundle.candidate_claims}
    assert bundle.contradictions
    assert any(
        cluster.assessment.value == "disputed" for cluster in bundle.claim_clusters
    )
    assert all(
        item.drafting_authorized is False
        for item in bundle.article_content_opportunities
    )
    assert all(
        item.article_url == plan.target_article_url
        for item in bundle.article_content_opportunities
    )
    assert bundle.image_evidence_records[0].claim_ids
    assert any(
        item.opportunity_type == "add_visual"
        for item in bundle.article_content_opportunities
    )


def test_topic_reuse_blank_decisions_determinism_and_production_preservation(
    tmp_path: Path,
) -> None:
    plan = build_research_plan(_request(tmp_path))
    run = discover_sources(plan, SyntheticProvider())
    bundle = analyze_search_run(run, plan)
    production = tmp_path / "production.sqlite"
    with sqlite3.connect(production) as connection:
        connection.execute("CREATE TABLE protected(value TEXT)")
        connection.execute("INSERT INTO protected VALUES ('owner data')")
    before = production.read_bytes()
    database = tmp_path / "research.sqlite"
    first = build_research_snapshot(
        bundle, database, production_database_path=production
    )
    second = build_research_snapshot(
        bundle, database, production_database_path=production
    )
    assert first == second
    assert production.read_bytes() == before
    assert first.owner_decisions
    assert all(decision.decision is None for decision in first.owner_decisions)
    summaries = [
        ResearchTopicDatabase(database).topic_summary(topic_id)
        for topic_id in first.topic_ids
    ]
    assert any(summary and summary["source_ids"] for summary in summaries)


def test_standard_export_is_deterministic_and_offline(tmp_path: Path) -> None:
    plan = build_research_plan(_request(tmp_path))
    run = discover_sources(plan, SyntheticProvider())
    bundle = analyze_search_run(run, plan)
    snapshot = build_research_snapshot(bundle, tmp_path / "research.sqlite")
    output = tmp_path / "review"
    export_review_package(bundle, snapshot, output)
    before = {path.name: path.read_bytes() for path in output.iterdir()}
    export_review_package(bundle, snapshot, output)
    assert before == {path.name: path.read_bytes() for path in output.iterdir()}
    assert set(STANDARD_OUTPUTS) <= set(before)
    validation = json.loads((output / "validation.json").read_text(encoding="utf-8"))
    assert validation["wordpress_modified"] is False
    assert validation["production_sqlite_modified"] is False
    assert validation["live_api_used_during_export"] is False


def test_research_plan_cli_uses_local_fixture_only(tmp_path: Path) -> None:
    request = _request(tmp_path)
    request_path = tmp_path / "request.json"
    request_path.write_text(request.model_dump_json(indent=2), encoding="utf-8")
    output = tmp_path / "plan"
    result = CliRunner().invoke(
        app, ["research-plan", "--request", str(request_path), "--output", str(output)]
    )
    assert result.exit_code == 0, result.output
    assert (output / "research-plan.json").is_file()
    assert (output / "query-plan.csv").is_file()
