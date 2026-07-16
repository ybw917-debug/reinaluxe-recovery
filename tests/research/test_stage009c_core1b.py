from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from reinaluxe_recovery.research.analysis import (
    SourceAnalysisProvider,
    SourceAnalysisResult,
)
from reinaluxe_recovery.research.assets import build_asset_manifest
from reinaluxe_recovery.research.contracts import (
    AssetManifestRecord,
    ImageSourceCategory,
    ResearchQuery,
    SourceCandidate,
    SourceLane,
    SourceLanePolicy,
    TopicResearchRequest,
)
from reinaluxe_recovery.research.errors import ResearchError
from reinaluxe_recovery.research.planning import build_research_plan
from reinaluxe_recovery.research.production import export_content_production
from reinaluxe_recovery.research.providers.base import ResearchSearchProvider
from reinaluxe_recovery.research.screening import screen_source_candidate
from reinaluxe_recovery.research.smoke import SMOKE_OUTPUTS, research_smoke


def _lanes() -> list[dict[str, Any]]:
    return [
        {
            "source_lane": lane,
            "priority": index,
            "query_quota": 3,
            "source_quota": 20,
        }
        for index, lane in enumerate(
            (
                "community_reddit",
                "community_forums",
                "primary_official",
                "expert_editorial",
                "commercial_observation",
                "visual_image",
            ),
            start=1,
        )
    ]


def _request(tmp_path: Path, *, production: Path | None = None) -> Path:
    article = tmp_path / "article.json"
    article.write_text(
        json.dumps(
            {
                "title": "Existing AAA guide",
                "sections": [
                    {
                        "heading": {"level": 1, "text": "AAA terminology"},
                        "paragraphs": [{"text": "Existing owner-authored context."}],
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
                "research_id": "core1b-smoke-001",
                "mode": "article_research",
                "content_production_mode": "legacy_reconstruction",
                "target_article_url": "https://example.test/aaa-guide/",
                "article_source_path": str(article),
                "production_database_path": str(production) if production else None,
                "owner_objective": "Test bounded public discovery.",
                "target_audience": "comparison readers",
                "source_lane_priorities": _lanes(),
                "brand_scope": ["cross-brand"],
                "model_scope": ["AAA guide"],
                "query_families": [
                    "terminology",
                    "PSP and QC limits",
                    "handmade and tannery provenance",
                ],
                "maximum_search_calls": 12,
                "maximum_sources": 30,
                "maximum_image_candidates": 20,
                "output_directory": str(tmp_path / "unused"),
                "provider": "synthetic",
            }
        ),
        encoding="utf-8",
    )
    return request


class SmokeProvider(ResearchSearchProvider):
    provider_name = "synthetic"

    def __init__(self, *, results_per_call: int = 5, fail: bool = False) -> None:
        self.results_per_call = results_per_call
        self.fail = fail
        self.calls: list[str] = []

    def validate_configuration(self) -> None:
        return None

    def capabilities(self) -> dict[str, Any]:
        return {"web_search": True, "requested_result_count": 15}

    def execute_query(self, query: ResearchQuery) -> list[dict[str, Any]]:
        self.calls.append(query.query_id)
        if self.fail:
            raise ResearchError("synthetic provider failure; credentials were redacted")
        call = len(self.calls)
        output = []
        for index in range(self.results_per_call):
            if query.source_lane is SourceLane.COMMUNITY_REDDIT:
                url = (
                    f"https://www.reddit.com/r/Example/comments/a{call}{index}/"
                    f"fixture/?utm_source=smoke"
                )
            elif query.source_lane is SourceLane.COMMUNITY_FORUMS:
                url = f"https://forum{index}.example.test/thread/{call}-{index}"
            else:
                url = f"https://reference{index}.example.gov/guide/{call}-{index}"
            output.append(
                {
                    "provider_result_id": f"provider-{call}-{index}",
                    "url": url,
                    "title": f"Scoped provider record {call}-{index}.",
                    "snippet": (
                        "Repeated market observations show terminology varies by seller. "
                        f"This provider record belongs to lane {query.source_lane.value}."
                    ),
                    "published_at": "2026-07-01T00:00:00Z",
                    "images": (
                        [
                            {
                                "url": f"https://images.example.test/{call}-{index}.jpg",
                                "alt": "provider-returned comparison",
                            }
                        ]
                        if index == 0
                        else []
                    ),
                    "provider_access_classification": "provider_returned_content",
                }
            )
        return output

    def normalize_results(
        self, query: ResearchQuery, response: Any
    ) -> list[dict[str, Any]]:
        del query
        return list(response)

    def report_usage(self) -> dict[str, Any]:
        return {"query_calls": len(self.calls)}


class StructuredAnalyzer(SourceAnalysisProvider):
    def analyze(self, source: SourceCandidate, plan: Any) -> SourceAnalysisResult:
        del plan
        return SourceAnalysisResult(
            source_lane_classification=source.source_lane,
            relevance=0.92,
            first_hand_status="mixed",
            specificity=0.8,
            commercial_promotion_risk="low",
            source_access_quality="snippet_only",
            evidence_summary="Three scoped market observations were identified.",
            key_observations=[
                "Terminology varies across reviewed seller descriptions."
            ],
            claims=[
                "AAA terminology varies across reviewed seller descriptions.",
                "Provider-returned discussions distinguish visible quality signals.",
                "Public sources describe limits in seller grading language.",
            ],
            limitations=["Only provider-returned content was analyzed."],
            proposed_topic_ids=["replica-quality-terminology"],
            proposed_article_sections=["AAA terminology"],
            image_presence_assessment=(
                "present" if source.has_images else "not_returned"
            ),
        )


class URLClaimAnalyzer(StructuredAnalyzer):
    def analyze(self, source: SourceCandidate, plan: Any) -> SourceAnalysisResult:
        result = super().analyze(source, plan)
        return result.model_copy(
            update={
                "claims": [
                    "See https://invented.example/model-source",
                    "The reviewed bag weighs 999 kg.",
                ]
            }
        )


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def test_smoke_limits_traceability_visuals_and_assertive_outputs(
    tmp_path: Path,
) -> None:
    provider = SmokeProvider()
    output = tmp_path / "smoke"
    validation = research_smoke(
        _request(tmp_path),
        ["terminology", "psp_qc", "handmade_provenance"],
        output,
        research_database=tmp_path / "research.sqlite",
        glm_assisted=True,
        provider=provider,
        analyzer=StructuredAnalyzer(),
    )
    assert len(provider.calls) == 3
    assert validation["calls_made"] == 3
    assert validation["raw_results_processed"] == 15
    assert validation["retained_sources"] <= 20
    assert validation["source_lane_count"] >= 2
    assert validation["reddit_sources"] >= 3
    assert validation["image_candidates"] >= 1
    assert validation["candidate_claims"] >= 3
    assert validation["recommendation"] == "full_run_recommended"
    assert set(SMOKE_OUTPUTS) <= {path.name for path in output.iterdir()}
    assert validation["source_integrity"]["claim_to_source_traceability_valid"]
    assert validation["source_integrity"]["all_retained_urls_provider_returned"]
    assert all(
        int(row["requested_result_limit"]) <= 15 and row["retry_count"] == "0"
        for row in _read_csv(output / "provider-call-register.csv")
    )
    narratives = _read_csv(output / "assertive-narrative-register.csv")
    strongest = max(narratives, key=lambda row: int(row["source_count"]))
    assert int(strongest["independent_source_cluster_count"]) >= 2
    assert strongest["publication_intensity_allowed"] == (
        "highly_assertive_but_supportable"
    )
    images = _read_csv(output / "image-source-candidates.csv")
    assert images
    assert all(row["image_source_category"] != "owner_original" for row in images)


def test_smoke_caps_each_call_at_fifteen_results(tmp_path: Path) -> None:
    provider = SmokeProvider(results_per_call=30)
    output = tmp_path / "limited"
    validation = research_smoke(
        _request(tmp_path),
        ["terminology"],
        output,
        research_database=tmp_path / "research.sqlite",
        glm_assisted=True,
        provider=provider,
        analyzer=StructuredAnalyzer(),
    )
    assert len(provider.calls) == 1
    assert validation["raw_results_processed"] == 15
    assert len(_read_csv(output / "query-results-register.csv")) == 15


def test_provider_failure_is_not_retried_and_exports_honest_result(
    tmp_path: Path,
) -> None:
    provider = SmokeProvider(fail=True)
    output = tmp_path / "failed"
    validation = research_smoke(
        _request(tmp_path),
        ["terminology", "psp_qc", "handmade_provenance"],
        output,
        research_database=tmp_path / "research.sqlite",
        glm_assisted=True,
        provider=provider,
        analyzer=StructuredAnalyzer(),
    )
    assert len(provider.calls) == 1
    assert validation["recommendation"] == "provider_coverage_insufficient"
    calls = _read_csv(output / "provider-call-register.csv")
    assert calls[0]["status"] == "provider_failed"
    assert calls[0]["retry_count"] == "0"


def test_reddit_post_normalization_and_rejection() -> None:
    query = ResearchQuery(
        query_id="query-reddit",
        research_question_id="question-reddit",
        query_family="terminology",
        source_lane="community_reddit",
        search_text="site:reddit.com terminology",
        expected_evidence_type="public post",
        stopping_criteria="one call",
    )
    policies = {
        SourceLane.COMMUNITY_REDDIT: SourceLanePolicy(
            source_lane="community_reddit", priority=1
        )
    }
    candidate, reason = screen_source_candidate(
        query,
        {
            "url": (
                "https://old.reddit.com/r/Example/comments/abc123/title/comment9/"
                "?utm_source=test"
            ),
            "title": "Post by u/private-name",
            "snippet": "u/private-name compared examples.",
        },
        policies,
    )
    assert reason is None and candidate is not None
    assert str(candidate.normalized_url) == (
        "https://reddit.com/r/Example/comments/abc123/"
    )
    assert "private-name" not in f"{candidate.title} {candidate.snippet}"
    invalid = [
        "https://reddit.com/search/?q=aaa",
        "https://reddit.com/user/private-name/",
        "https://reddit.com/r/Example/",
        "https://reddit.com/login/",
        "https://reddit.com/media/?url=https://example.test/image.jpg",
        "https://not-reddit.example/post/1",
    ]
    for url in invalid:
        rejected, rejection = screen_source_candidate(
            query, {"url": url, "title": "invalid"}, policies
        )
        assert rejected is None and rejection


def test_strict_lane_signals_reclassify_official_brand_domains() -> None:
    query = ResearchQuery(
        query_id="query-forum",
        research_question_id="question-forum",
        source_lane="community_forums",
        search_text="public forum terminology",
        brand_scope=["Louis Vuitton"],
        expected_evidence_type="public discussion",
        stopping_criteria="one call",
    )
    policies = {
        SourceLane.COMMUNITY_FORUMS: SourceLanePolicy(
            source_lane="community_forums", priority=1
        ),
        SourceLane.PRIMARY_OFFICIAL: SourceLanePolicy(
            source_lane="primary_official", priority=2
        ),
    }
    official, reason = screen_source_candidate(
        query,
        {"url": "https://us.louisvuitton.com/eng-us/stories/example"},
        policies,
    )
    assert reason is None and official is not None
    assert official.source_lane is SourceLane.PRIMARY_OFFICIAL
    mismatched, mismatch_reason = screen_source_candidate(
        query,
        {"url": "https://news.example.test/general-article"},
        policies,
    )
    assert mismatched is None and mismatch_reason == "source_lane_mismatch"


class DuplicateProvider(SmokeProvider):
    def execute_query(self, query: ResearchQuery) -> list[dict[str, Any]]:
        self.calls.append(query.query_id)
        return [
            {
                "provider_result_id": "one",
                "url": "https://forum.example.test/thread/a?utm_source=x",
                "title": "Same title",
                "snippet": "Same returned content",
            },
            {
                "provider_result_id": "two",
                "url": "https://forum.example.test/thread/a",
                "title": "Same title",
                "snippet": "Same returned content",
            },
            {
                "provider_result_id": "three",
                "url": "https://forum.example.test/thread/b",
                "title": "Same title",
                "snippet": "Same returned content",
            },
            {
                "provider_result_id": "four",
                "url": "https://forum.example.test/thread/c",
                "title": "Different title",
                "snippet": "Different returned content",
            },
        ]


def test_exact_content_duplicates_and_domain_clusters_are_reported(
    tmp_path: Path,
) -> None:
    output = tmp_path / "duplicates"
    research_smoke(
        _request(tmp_path),
        ["terminology"],
        output,
        research_database=tmp_path / "research.sqlite",
        glm_assisted=True,
        provider=DuplicateProvider(),
        analyzer=StructuredAnalyzer(),
    )
    duplicates = _read_csv(output / "duplicate-source-register.csv")
    assert {row["duplicate_reason"] for row in duplicates} == {
        "exact_duplicate_url",
        "identical_title_snippet_duplicate",
    }
    retained = _read_csv(output / "retained-source-register.csv")
    assert len(retained) == 2
    assert len({row["source_cluster_id"] for row in retained}) == 1
    assert all(row["repeated_domain_count"] == "2" for row in retained)


def test_model_generated_urls_and_ungrounded_numbers_are_not_claims(
    tmp_path: Path,
) -> None:
    output = tmp_path / "no-model-url"
    research_smoke(
        _request(tmp_path),
        ["terminology"],
        output,
        research_database=tmp_path / "research.sqlite",
        glm_assisted=True,
        provider=SmokeProvider(),
        analyzer=URLClaimAnalyzer(),
    )
    rendered = (output / "candidate-claims.csv").read_text(encoding="utf-8")
    assert "invented.example" not in rendered
    assert "999" not in rendered
    with pytest.raises(ValidationError):
        SourceAnalysisResult.model_validate(
            {
                **StructuredAnalyzer()
                .analyze(
                    SourceCandidate.model_validate(
                        {
                            "source_id": "source-1",
                            "query_id": "query-1",
                            "provider": "synthetic",
                            "source_url": "https://example.test/source",
                            "normalized_url": "https://example.test/source",
                            "source_lane": "expert_editorial",
                            "domain": "example.test",
                        }
                    ),
                    None,
                )
                .model_dump(mode="json"),
                "url": "https://invented.example/source",
            }
        )


def test_asset_manifest_hashes_duplicates_relative_paths_and_owner_protection(
    tmp_path: Path,
) -> None:
    root = tmp_path / "assets"
    seller = root / "seller-shot"
    owner = root / "owner-original"
    seller.mkdir(parents=True)
    owner.mkdir()
    first = seller / "front.txt"
    second = seller / "front-copy.txt"
    owner_file = owner / "private-note.txt"
    first.write_bytes(b"same synthetic fixture")
    second.write_bytes(b"same synthetic fixture")
    owner_file.write_bytes(b"different owner fixture")
    before = {path: path.read_bytes() for path in (first, second, owner_file)}
    manifest = root / "manifest.csv"
    records = build_asset_manifest(
        root, manifest, brand="Hermes", model="Birkin", size="25"
    )
    assert len(records) == 3
    assert all(not item.relative_path.is_absolute() for item in records)
    assert all(len(item.sha256) == 64 for item in records)
    duplicate = next(
        item for item in records if item.relative_path == Path("seller-shot/front.txt")
    )
    duplicate_peer = next(
        item
        for item in records
        if item.relative_path == Path("seller-shot/front-copy.txt")
    )
    assert "exact_duplicate_of=" in f"{duplicate.notes} {duplicate_peer.notes}"
    protected = next(
        item
        for item in records
        if item.relative_path == Path("owner-original/private-note.txt")
    )
    assert protected.source_category is None
    assert "explicit owner record required" in protected.notes
    assert {path: path.read_bytes() for path in before} == before
    with pytest.raises(ValidationError, match="explicit owner"):
        AssetManifestRecord.model_validate(
            {
                "asset_id": "unsafe-owner-original",
                "relative_path": "owner-original/front.jpg",
                "file_type": "image/jpeg",
                "sha256": "0" * 64,
                "source_category": ImageSourceCategory.OWNER_ORIGINAL,
            }
        )
    second_run = build_asset_manifest(
        root, manifest, brand="Hermes", model="Birkin", size="25"
    )
    assert [item.asset_id for item in records] == [item.asset_id for item in second_run]


def test_generated_csv_manifest_is_consumed_by_new_page_build(tmp_path: Path) -> None:
    root = tmp_path / "assets"
    (root / "official-reference").mkdir(parents=True)
    (root / "official-reference" / "model-note.txt").write_text(
        "Synthetic model note", encoding="utf-8"
    )
    manifest = root / "manifest.csv"
    build_asset_manifest(root, manifest, brand="Hermes", model="Kelly", size="28")
    request = TopicResearchRequest.model_validate(
        {
            "research_id": "asset-new-page",
            "mode": "topic_build",
            "content_production_mode": "new_page_build",
            "topic_ids": ["hermes-kelly-28"],
            "owner_objective": "Prepare a future page.",
            "target_audience": "model readers",
            "source_lane_priorities": _lanes(),
            "query_families": ["model details"],
            "asset_root": root,
            "asset_manifest": manifest,
            "maximum_search_calls": 3,
            "maximum_sources": 10,
            "maximum_image_candidates": 5,
            "output_directory": tmp_path / "new-page",
            "provider": "synthetic",
        }
    )
    plan = build_research_plan(request)
    output = tmp_path / "new-page-output"
    result = export_content_production(plan, output)
    assert result["asset_count"] == 1
    coverage = _read_csv(output / "asset-coverage-register.csv")
    assert coverage[0]["sha256"]
    assert coverage[0]["relative_path"] == "official-reference/model-note.txt"


def test_smoke_preserves_production_sqlite_bytes(tmp_path: Path) -> None:
    production = tmp_path / "production.sqlite"
    production.write_bytes(b"synthetic protected production bytes")
    before = production.read_bytes()
    research_smoke(
        _request(tmp_path, production=production),
        ["terminology"],
        tmp_path / "integrity-smoke",
        research_database=tmp_path / "research.sqlite",
        glm_assisted=True,
        provider=SmokeProvider(),
        analyzer=StructuredAnalyzer(),
    )
    assert production.read_bytes() == before
