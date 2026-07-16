from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from reinaluxe_recovery.research.artifacts import load_research_request
from reinaluxe_recovery.research.contracts import (
    ResearchQuery,
    SourceLane,
    SourceLanePolicy,
)
from reinaluxe_recovery.research.diagnostics import audit_original_smoke
from reinaluxe_recovery.research.planning import build_research_plan
from reinaluxe_recovery.research.preview import PREVIEW_OUTPUTS, preview_queries
from reinaluxe_recovery.research.providers.base import ResearchSearchProvider
from reinaluxe_recovery.research.query_integrity import (
    build_preview_queries,
    evaluate_query_quality,
)
from reinaluxe_recovery.research.screening import (
    discover_sources,
    qualify_visual_candidate,
    screen_source_candidate,
)
from reinaluxe_recovery.research.workflow import research_preview_queries


def _request(tmp_path: Path) -> Path:
    article = tmp_path / "article.json"
    article.write_text(
        json.dumps(
            {
                "title": "AAA guide with CarryAll Vibe MM context",
                "sections": [
                    {
                        "heading": {"level": 1, "text": "AAA terminology"},
                        "paragraphs": [{"text": "Existing owner context."}],
                        "images": [
                            {
                                "src": "carryall-vibe-product-id-M46292.jpg",
                                "alt": "Louis Vuitton CarryAll Vibe MM",
                            }
                        ],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    request = tmp_path / "request.json"
    request.write_text(
        json.dumps(
            {
                "research_id": "core1b1a-preview",
                "mode": "article_research",
                "article_source_path": str(article),
                "owner_objective": "Preview focused AAA research queries.",
                "target_audience": "comparison readers",
                "source_lane_priorities": [
                    {"source_lane": "community_reddit", "priority": 1},
                    {"source_lane": "community_forums", "priority": 2},
                    {"source_lane": "expert_editorial", "priority": 3},
                    {"source_lane": "primary_official", "priority": 4},
                ],
                "brand_scope": ["cross-brand", "Louis Vuitton"],
                "model_scope": ["CarryAll Vibe MM", "M46292"],
                "query_families": [
                    "terminology",
                    "PSP and QC limits",
                    "handmade and tannery provenance",
                ],
                "maximum_search_calls": 6,
                "maximum_sources": 20,
                "maximum_image_candidates": 10,
                "output_directory": str(tmp_path / "unused"),
                "provider": "synthetic",
            }
        ),
        encoding="utf-8",
    )
    return request


def _queries(tmp_path: Path) -> list[ResearchQuery]:
    request = load_research_request(_request(tmp_path))
    return build_preview_queries(
        build_research_plan(request),
        ["terminology", "psp_qc", "handmade_provenance"],
    )


class CountingProvider(ResearchSearchProvider):
    provider_name = "synthetic"

    def __init__(self) -> None:
        self.calls = 0

    def validate_configuration(self) -> None:
        return None

    def capabilities(self) -> dict[str, Any]:
        return {"web_search": True, "requested_result_count": 10}

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


def _policies() -> dict[SourceLane, SourceLanePolicy]:
    return {
        lane: SourceLanePolicy(source_lane=lane, priority=index)
        for index, lane in enumerate(SourceLane, start=1)
    }


def test_preview_preserves_exact_queries_and_makes_zero_calls(tmp_path: Path) -> None:
    output = tmp_path / "preview"
    validation = research_preview_queries(
        _request(tmp_path),
        ["terminology", "psp_qc", "handmade_provenance"],
        output,
    )
    assert validation["valid"] is True
    assert validation["provider_calls_made"] == 0
    assert validation["glm_calls_made"] == 0
    assert set(PREVIEW_OUTPUTS) == {path.name for path in output.iterdir()}
    rows = _read_csv(output / "query-preview.csv")
    assert [row["requested_source_lane"] for row in rows] == [
        "community_reddit",
        "community_forums",
        "expert_editorial",
    ]
    assert rows[0]["search_domain_filter"] == "reddit.com"
    for row in rows:
        assert row["exact_search_query"]
        assert row["query_hash"]
        assert "CarryAll" not in row["exact_search_query"]
        assert "Louis Vuitton" not in row["exact_search_query"]
        assert "M46292" not in row["exact_search_query"]


def test_preview_outputs_are_deterministic(tmp_path: Path) -> None:
    request = _request(tmp_path)
    first = tmp_path / "first"
    second = tmp_path / "second"
    preview_queries(request, ["terminology", "psp_qc", "handmade_provenance"], first)
    preview_queries(request, ["terminology", "psp_qc", "handmade_provenance"], second)
    assert {name: (first / name).read_bytes() for name in PREVIEW_OUTPUTS} == {
        name: (second / name).read_bytes() for name in PREVIEW_OUTPUTS
    }


def test_query_quality_rejects_contamination_and_blocks_paid_call(
    tmp_path: Path,
) -> None:
    request = load_research_request(_request(tmp_path))
    plan = build_research_plan(request)
    bad = ResearchQuery(
        query_id="bad-carryall-query",
        research_question_id=plan.questions[0].question_id,
        query_family="terminology",
        source_lane="community_reddit",
        search_text="site:reddit.com/r/ CarryAll Louis Vuitton product M46292",
        required_topic_anchors=["AAA replica bags"],
        prohibited_unrelated_entities=["CarryAll", "Louis Vuitton", "M46292"],
        clear_research_question="How are AAA replica bag grades described?",
        expected_evidence_type="Reddit post",
        stopping_criteria="one call",
    )
    quality = evaluate_query_quality(bad, [bad])
    assert quality.passed is False
    assert set(quality.prohibited_entity_hits) == {
        "CarryAll",
        "Louis Vuitton",
        "M46292",
    }
    provider = CountingProvider()
    discover_sources(plan.model_copy(update={"queries": [bad]}), provider)
    assert provider.calls == 0


def test_requested_and_classified_lanes_are_independent(tmp_path: Path) -> None:
    query = _queries(tmp_path)[1]
    candidate, reason = screen_source_candidate(
        query,
        {
            "url": "https://news.qq.com/article/psp-qc-lighting",
            "title": "PSP QC lighting and received-item analysis",
        },
        _policies(),
    )
    assert candidate is None
    assert reason == "source_lane_mismatch"


def test_reddit_query_requires_reddit_post_permalink(tmp_path: Path) -> None:
    query = _queries(tmp_path)[0]
    assert query.search_domain_filter == "reddit.com"
    assert "site:reddit.com/r/" in query.exact_search_query
    rejected, reason = screen_source_candidate(
        query,
        {
            "url": "https://news.example.test/aaa-quality-tiers",
            "title": "AAA replica quality tiers",
        },
        _policies(),
    )
    assert rejected is None and reason == "source_lane_mismatch"


def test_official_homepage_and_unrelated_product_fail_relevance(
    tmp_path: Path,
) -> None:
    query = _queries(tmp_path)[2]
    homepage, homepage_reason = screen_source_candidate(
        query,
        {"url": "https://www.louisvuitton.com/", "title": "Louis Vuitton"},
        _policies(),
    )
    product, product_reason = screen_source_candidate(
        query,
        {
            "url": "https://us.louisvuitton.com/products/carryall-vibe-mm",
            "title": "CarryAll Vibe MM product page",
        },
        _policies(),
    )
    assert homepage is None and homepage_reason == "source_lane_mismatch"
    assert product is None and product_reason == "source_lane_mismatch"


def test_regional_official_pages_share_organization_and_independent_cluster(
    tmp_path: Path,
) -> None:
    query = _queries(tmp_path)[2].model_copy(
        update={
            "query_family": None,
            "source_lane": SourceLane.PRIMARY_OFFICIAL,
            "requested_source_lane": SourceLane.PRIMARY_OFFICIAL,
        }
    )
    candidates = []
    for host in (
        "de.louisvuitton.com",
        "ca.louisvuitton.com",
        "me.louisvuitton.com",
        "www.louisvuitton.cn",
    ):
        candidate, reason = screen_source_candidate(
            query,
            {
                "url": f"https://{host}/products/leather-provenance-reference",
                "title": "Leather provenance reference",
            },
            _policies(),
        )
        assert reason is None and candidate is not None
        candidates.append(candidate)
    assert {item.registrable_domain for item in candidates} == {
        "louisvuitton.com",
        "louisvuitton.cn",
    }
    assert len({item.organization_cluster_id for item in candidates}) == 1
    assert len({item.independent_source_cluster_id for item in candidates}) == 1
    assert {item.regional_variant for item in candidates} == {"de", "ca", "me", None}


def test_image_candidate_requires_real_locator_and_media_label_is_unresolved(
    tmp_path: Path,
) -> None:
    query = _queries(tmp_path)[1]
    source, reason = screen_source_candidate(
        query,
        {
            "url": "https://forum.example.test/thread/psp-qc-lighting",
            "title": "Replica handbag buyer forum PSP QC lighting comparison",
        },
        _policies(),
    )
    assert reason is None and source is not None
    resolved, unresolved = qualify_visual_candidate(
        source, {"url": "https://images.example.test/psp.jpg", "alt": "PSP"}
    )
    assert resolved is not None and unresolved is None
    assert resolved.actual_image_reference_available is True
    invalid, visual_page = qualify_visual_candidate(source, {"media": "LV media label"})
    assert invalid is None and visual_page is not None
    assert visual_page.candidate_resolution_status == "visual_page_candidate"
    assert visual_page.actual_image_reference_available is False


def test_original_smoke_audit_generates_no_claims(tmp_path: Path) -> None:
    captured = tmp_path / "captured"
    captured.mkdir()
    _write_csv(
        captured / "retained-source-register.csv",
        ["source_id", "query_family", "normalized_url", "title", "snippet"],
        [
            {
                "source_id": "one",
                "query_family": "terminology",
                "normalized_url": "https://de.louisvuitton.com/products/carryall",
                "title": "CarryAll product page",
                "snippet": "Official product details",
            },
            {
                "source_id": "two",
                "query_family": "terminology",
                "normalized_url": "https://ca.louisvuitton.com/products/carryall",
                "title": "CarryAll product page",
                "snippet": "Official product details",
            },
        ],
    )
    _write_csv(
        captured / "image-source-candidates.csv",
        ["image_id", "source_id", "source_page_url", "provider_media_metadata"],
        [
            {
                "image_id": "image-one",
                "source_id": "one",
                "source_page_url": "https://de.louisvuitton.com/products/carryall",
                "provider_media_metadata": json.dumps({"media": "LV media label"}),
            }
        ],
    )
    summary = audit_original_smoke(captured, tmp_path / "diagnostic")
    assert summary["topic_relevance_passed"] == 0
    assert summary["organization_cluster_count"] == 1
    assert summary["organization_cluster_reduction"] == 1
    assert summary["valid_resolved_image_candidates"] == 0
    assert summary["unresolved_visual_page_candidates"] == 1
    assert summary["claims_generated"] == 0


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _write_csv(path: Path, fields: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
