from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from reinaluxe_recovery.research.artifacts import load_research_request
from reinaluxe_recovery.research.comparison import export_provider_comparison
from reinaluxe_recovery.research.contracts import ResearchQuery, SourceLane
from reinaluxe_recovery.research.errors import ResearchError
from reinaluxe_recovery.research.planning import build_research_plan
from reinaluxe_recovery.research.providers import (
    BraveImageSearchProvider,
    BraveWebSearchProvider,
    default_lane_routed_provider,
)
from reinaluxe_recovery.research.query_integrity import build_preview_queries
from reinaluxe_recovery.research.screening import (
    classify_source_lane_details,
    screen_source_candidate,
)


def _queries() -> list[ResearchQuery]:
    plan = build_research_plan(
        load_research_request(Path("docs/examples/aaa-pillar-001.yaml"))
    )
    return build_preview_queries(
        plan,
        ["terminology", "psp_qc", "handmade_provenance"],
        maximum_results=10,
    )


def _policies() -> dict[Any, Any]:
    plan = build_research_plan(
        load_research_request(Path("docs/examples/aaa-pillar-001.yaml"))
    )
    return {item.source_lane: item for item in plan.source_lane_policies}


def test_brave_web_contract_caps_request_and_normalizes_without_crawling() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["count"] = request.url.params.get("count")
        captured["query"] = request.url.params.get("q")
        return httpx.Response(
            200,
            json={
                "web": {
                    "results": [
                        {
                            "title": "AAA and mirror quality in replica bags",
                            "url": "https://www.reddit.com/r/example/comments/abc123/topic/",
                            "description": "Replica bag AAA and mirror quality discussion.",
                        }
                    ]
                }
            },
        )

    provider = BraveWebSearchProvider(
        environ={"BRAVE_SEARCH_API_KEY": "secret-never-serialize"},
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        result_count=10,
    )
    query = _queries()[0]
    response = provider.execute_query(query)
    normalized = provider.normalize_results(query, response)
    assert captured == {
        "method": "GET",
        "count": "10",
        "query": query.exact_search_query,
    }
    assert (
        normalized[0]["provider_access_classification"] == "provider_returned_snippet"
    )
    assert provider.report_usage()["result_page_requests"] == 0
    assert "secret-never-serialize" not in repr(provider)
    assert "secret-never-serialize" not in json.dumps(provider.report_usage())


def test_brave_image_contract_has_no_live_execution_or_download() -> None:
    provider = BraveImageSearchProvider(
        environ={"BRAVE_SEARCH_API_KEY": "secret-never-serialize"}
    )
    assert provider.capabilities()["live_execution"] is False
    with pytest.raises(ResearchError, match="disabled"):
        provider.execute_query(_queries()[0])
    assert provider.report_usage()["query_calls"] == 0
    assert provider.report_usage()["images_downloaded"] == 0


def test_default_lane_routing_preserves_zhipu_and_configures_commercial() -> None:
    provider = default_lane_routed_provider(
        environ={
            "BRAVE_SEARCH_API_KEY": "brave-secret",
            "ZHIPU_API_KEY": "zhipu-secret",
            "ZHIPU_SEARCH_ENGINE": "search-engine",
            "ZHIPU_SUMMARIZER_MODEL": "glm-model",
            "RESEARCH_COMMERCIAL_SEARCH_PROVIDER": "zhipu-web-search",
        }
    )
    routes = provider.capabilities()["routes"]
    assert routes["community_reddit"] == "brave-web-search"
    assert routes["community_forums"] == "brave-web-search"
    assert routes["expert_editorial"] == "brave-web-search"
    assert routes["primary_official"] == "zhipu"
    assert routes["visual_image"] == "brave-image-search"
    assert routes["commercial_observation"] == "zhipu"
    assert provider.capabilities()["automatic_fallback"] is False


def test_conjunctive_relevance_rejects_gaming_corruption_and_partial_matches() -> None:
    terminology, psp, provenance = _queries()
    policies = _policies()
    gaming, gaming_reason = screen_source_candidate(
        psp,
        {
            "url": "https://forum.example.test/thread/sony-psp-games",
            "title": "Sony PSP gaming and handheld console review",
            "snippet": "PSP game pictures compare lighting on the video game console.",
        },
        policies,
    )
    assert gaming is None and gaming_reason == "psp_gaming_false_positive"
    corrupted, corrupted_reason = screen_source_candidate(
        terminology,
        {
            "url": "https://reddit.com/r/example/comments/abc123/topic/",
            "title": "Replica bag AAA mirror quality 鈥檇 corrupted",
        },
        policies,
    )
    assert corrupted is None and corrupted_reason == "corrupted_content"
    partial, partial_reason = screen_source_candidate(
        provenance,
        {
            "url": "https://editorial.example.test/leather-provenance",
            "title": "Handmade original leather provenance verification",
        },
        policies,
    )
    assert partial is None and partial_reason == "topic_relevance_failed"
    valid, reason = screen_source_candidate(
        provenance,
        {
            "url": "https://editorial.example.test/replica-leather-provenance",
            "title": "Replica handbag handmade original leather claim",
            "snippet": "An expert verification of tannery provenance evidence.",
        },
        policies,
    )
    assert reason is None and valid is not None


def test_commercial_content_is_not_classified_as_expert_editorial() -> None:
    commercial = classify_source_lane_details(
        "https://seller.example.test/blog/replica-guide",
        content="Replica bags for sale. Shop now or contact seller on WhatsApp.",
    )
    expert = classify_source_lane_details(
        "https://editorial.example.test/material-analysis",
        content="Independent material analysis and verification methodology.",
    )
    assert commercial.lane is SourceLane.COMMERCIAL_OBSERVATION
    assert commercial.rule == "commercial_content_signal"
    assert expert.lane is SourceLane.EXPERT_EDITORIAL


def test_offline_provider_comparison_reclassifies_zhipu_v2_registers(
    tmp_path: Path,
) -> None:
    queries = _queries()
    brave = tmp_path / "brave"
    zhipu = tmp_path / "zhipu"
    for run in (brave, zhipu):
        run.mkdir()
        _write_csv(
            run / "provider-call-register.csv",
            ["status", "returned_raw_results"],
            [{"status": "completed", "returned_raw_results": "1"}],
        )
    common_fields = [
        "provider_result_id",
        "query_id",
        "url",
        "title",
        "snippet_or_content",
        "published_at",
        "retrieved_at",
        "provider_access_classification",
        "status",
    ]
    _write_csv(
        brave / "query-results-register.csv",
        common_fields,
        [
            {
                "provider_result_id": "b1",
                "query_id": queries[0].query_id,
                "url": "https://reddit.com/r/example/comments/abc123/topic/",
                "title": "Replica bag AAA and mirror quality meanings",
                "snippet_or_content": "Replica bag users compare AAA and superfake tiers.",
                "status": "retained",
            }
        ],
    )
    _write_csv(
        zhipu / "query-results-register.csv",
        common_fields,
        [
            {
                "provider_result_id": "z1",
                "query_id": queries[1].query_id,
                "url": "https://forum.example.test/psp-console",
                "title": "Sony PSP game pictures",
                "snippet_or_content": "Handheld console lighting comparison.",
                "status": "retained",
            }
        ],
    )
    summaries = export_provider_comparison(
        Path("docs/examples/aaa-pillar-001.yaml"),
        ["terminology", "psp_qc", "handmade_provenance"],
        brave,
        zhipu,
        tmp_path / "output",
    )
    assert summaries[0]["reclassified_retained_sources"] == 1
    assert summaries[1]["psp_gaming_false_positive"] == 1
    assert (tmp_path / "output/provider-comparison-report.md").is_file()
    assert (tmp_path / "output/provider-comparison-register.csv").is_file()


def _write_csv(path: Path, fields: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
