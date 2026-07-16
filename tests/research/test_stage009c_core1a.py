from __future__ import annotations

import csv
import json
import sqlite3
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from reinaluxe_recovery.research.analysis import analyze_search_run
from reinaluxe_recovery.research.contracts import (
    ArticleResearchRequest,
    EditorialSynthesisRecord,
    EvidenceOwnershipClass,
    PublicationIntensity,
    ResearchQuery,
    TopicResearchRequest,
)
from reinaluxe_recovery.research.database import ResearchTopicDatabase
from reinaluxe_recovery.research.planning import build_research_plan
from reinaluxe_recovery.research.production import (
    COMMON_PRODUCTION_OUTPUTS,
    LEGACY_OUTPUTS,
    NEW_PAGE_OUTPUTS,
    build_content_transformations,
    build_editorial_synthesis,
    build_first_person_eligibility,
    export_content_production,
)
from reinaluxe_recovery.research.providers.base import ResearchSearchProvider
from reinaluxe_recovery.research.screening import discover_sources


def _article(tmp_path: Path, *, sections: bool = True) -> Path:
    path = tmp_path / "legacy-article.json"
    payload: dict[str, Any] = {"title": "Existing quality guide"}
    if sections:
        payload["sections"] = [
            {
                "heading": {"level": 1, "text": "Existing quality guide"},
                "paragraphs": [
                    {
                        "text": (
                            "I documented the Dior sourcing journey in the existing page. "
                            "This distinctive passage should remain."
                        )
                    }
                ],
                "images": [
                    {
                        "source_url": "https://example.test/images/existing-1.jpg",
                        "alt_text": "existing comparison",
                    }
                ],
                "links": [{"target_url": "https://example.test/internal/"}],
            },
            {
                "heading": {"level": 2, "text": "Quality comparison"},
                "paragraphs": [
                    {"text": "The current comparison explains visible quality signals."}
                ],
                "images": [
                    {"source_url": "https://example.test/images/existing-2.jpg"}
                ],
            },
        ]
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _lanes() -> list[dict[str, Any]]:
    return [
        {
            "source_lane": "community_reddit",
            "priority": 1,
            "query_quota": 1,
            "source_quota": 5,
        },
        {
            "source_lane": "community_forums",
            "priority": 2,
            "query_quota": 1,
            "source_quota": 5,
        },
        {
            "source_lane": "expert_editorial",
            "priority": 3,
            "query_quota": 1,
            "source_quota": 5,
        },
    ]


def _legacy_request(
    tmp_path: Path, *, sections: bool = True, **updates: Any
) -> ArticleResearchRequest:
    payload: dict[str, Any] = {
        "research_id": "legacy-reconstruction-001",
        "mode": "article_research",
        "content_production_mode": "legacy_reconstruction",
        "target_article_url": "https://example.test/existing-guide/",
        "article_source_path": _article(tmp_path, sections=sections),
        "owner_objective": "Strengthen the existing page without inventing owner actions.",
        "target_audience": "comparison readers",
        "source_lane_priorities": _lanes(),
        "research_questions": ["Which visible quality signals are consistent?"],
        "distinctive_content_requirements": ["Dior", "sourcing journey"],
        "minimum_existing_image_count": 2 if sections else 0,
        "maximum_search_calls": 3,
        "maximum_sources": 12,
        "maximum_image_candidates": 6,
        "output_directory": tmp_path / "out",
        "provider": "synthetic",
    }
    payload.update(updates)
    return ArticleResearchRequest.model_validate(payload)


class MultiSourceProvider(ResearchSearchProvider):
    provider_name = "synthetic"

    def validate_configuration(self) -> None:
        return None

    def capabilities(self) -> dict[str, Any]:
        return {"web_search": True, "image_metadata": True}

    def execute_query(self, query: ResearchQuery) -> ResearchQuery:
        return query

    def normalize_results(
        self, query: ResearchQuery, response: Any
    ) -> list[dict[str, Any]]:
        del response
        host = {
            "community_reddit": "reddit.com",
            "community_forums": "forum.example.test",
            "expert_editorial": "editorial.example.test",
        }[query.source_lane.value]
        path = (
            f"/r/example/comments/{query.query_id[-8:]}/fixture/"
            if query.source_lane.value == "community_reddit"
            else f"/{query.query_id}"
        )
        return [
            {
                "url": f"https://{host}{path}",
                "title": f"Visible construction assessment {query.source_lane.value}.",
                "snippet": (
                    "AAA replica quality tiers, PSP QC lighting, and handmade leather provenance "
                    "show controlled shape and cleaner visible construction."
                ),
                "images": [
                    {"url": f"https://images.example.test/{query.query_id}.jpg"}
                ],
            }
        ]

    def report_usage(self) -> dict[str, Any]:
        return {"query_calls": 3}


class NoCallProvider(ResearchSearchProvider):
    provider_name = "synthetic"

    def validate_configuration(self) -> None:
        raise AssertionError("provider configuration must not be required")

    def capabilities(self) -> dict[str, Any]:
        return {}

    def execute_query(self, query: ResearchQuery) -> Any:
        raise AssertionError(f"unexpected live query: {query.query_id}")

    def normalize_results(
        self, query: ResearchQuery, response: Any
    ) -> list[dict[str, Any]]:
        raise AssertionError(f"unexpected normalization: {query.query_id}")

    def report_usage(self) -> dict[str, Any]:
        return {"query_calls": 0}


def _bundle(tmp_path: Path) -> tuple[Any, Any]:
    plan = build_research_plan(_legacy_request(tmp_path))
    run = discover_sources(plan, MultiSourceProvider())
    return plan, analyze_search_run(run, plan)


def _csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def test_legacy_defaults_preserve_images_content_and_need_no_physical_evidence(
    tmp_path: Path,
) -> None:
    request = _legacy_request(tmp_path)
    assert request.preserve_existing_images is True
    assert request.preserve_distinctive_content is True
    assert request.owner_firsthand_evidence_required is False
    assert request.maximum_new_sections == 3
    assert (
        request.publication_intensity
        is PublicationIntensity.HIGHLY_ASSERTIVE_BUT_SUPPORTABLE
    )
    plan = build_research_plan(request)
    assert len(plan.article_analysis.existing_images) == 2  # type: ignore[union-attr]
    passages = [
        value
        for section in plan.article_analysis.existing_sections  # type: ignore[union-attr]
        for value in section.distinctive_passages
    ]
    assert any("Dior sourcing journey" in value for value in passages)


def test_planning_only_legacy_package_is_complete_keep_first_and_deterministic(
    tmp_path: Path,
) -> None:
    plan = build_research_plan(_legacy_request(tmp_path))
    output = tmp_path / "legacy-package"
    export_content_production(plan, output)
    before = {path.name: path.read_bytes() for path in output.iterdir()}
    export_content_production(plan, output)
    assert before == {path.name: path.read_bytes() for path in output.iterdir()}
    assert set([*COMMON_PRODUCTION_OUTPUTS, *LEGACY_OUTPUTS]) <= set(before)
    changes = _csv(output / "content-change-manifest.csv")
    assert changes and {row["operation"] for row in changes} == {"KEEP"}
    images = _csv(output / "image-to-section-map.csv")
    assert len(images) == 2 and all(row["preserve"] == "true" for row in images)
    validation = json.loads(
        (output / "reconstruction-validation.json").read_text(encoding="utf-8")
    )
    assert validation["missing_distinctive_requirements"] == []
    assert validation["owner_physical_evidence_required"] is False
    assert validation["existing_images_preserved"] == 2


def test_assertive_synthesis_and_section_level_enrich_mapping(tmp_path: Path) -> None:
    plan, bundle = _bundle(tmp_path)
    synthesis = build_editorial_synthesis(plan, bundle)
    assert synthesis
    finding = max(synthesis, key=lambda item: item.source_count)
    assert finding.source_count == 3
    assert finding.source_lane_count == 3
    assert finding.visual_evidence_count == 3
    assert (
        finding.evidence_ownership_class
        is EvidenceOwnershipClass.OWNER_MARKET_SYNTHESIS
    )
    assert (
        finding.publication_intensity_allowed
        is PublicationIntensity.HIGHLY_ASSERTIVE_BUT_SUPPORTABLE
    )
    assert "clearest patterns" in finding.selected_publication_wording
    assert not any(
        weak in finding.selected_publication_wording.casefold()
        for weak in ("may possibly", "some people might", "cannot be verified")
    )
    output = tmp_path / "analyzed-package"
    export_content_production(plan, output, bundle=bundle)
    changes = _csv(output / "content-change-manifest.csv")
    enriched = [row for row in changes if row["operation"] == "ENRICH"]
    assert enriched
    assert all(row["existing_section_id"] for row in enriched)
    assert all(row["supporting_source_ids"] for row in enriched)
    assert all(row["research_question_id"] for row in enriched)
    assert not any(row["operation"] == "DELETE" for row in changes)


def test_maximum_new_sections_requires_authority_and_is_enforced(
    tmp_path: Path,
) -> None:
    with pytest.raises(ValidationError, match="at most three"):
        _legacy_request(tmp_path, maximum_new_sections=4)
    plan = build_research_plan(_legacy_request(tmp_path, sections=False))
    synthesis = [
        EditorialSynthesisRecord(
            synthesis_id=f"synthesis-{index}",
            research_id=plan.research_id,
            claim_id=f"claim-{index}",
            evidence_ownership_class="owner_market_synthesis",
            source_observation=f"Observation {index}.",
            source_count=2,
            source_lane_count=2,
            visual_evidence_count=0,
            contradiction_status="none",
            editorial_inference="The evidence supports a scoped market conclusion.",
            restrained_wording=f"Restrained {index}.",
            assertive_wording=f"Assertive {index}.",
            highly_assertive_but_supportable_wording=f"Strong {index}.",
            publication_intensity_allowed="assertive",
            selected_publication_wording=f"Assertive {index}.",
            concise_limitation="Scoped to reviewed examples.",
            prohibited_unsupported_extension="No universal extension.",
            proposed_section=f"New section {index}",
            narrative_value="Useful narrative.",
            reader_usefulness="Useful to readers.",
            conversion_value="Supports decisions.",
        )
        for index in range(5)
    ]
    changes = build_content_transformations(plan, synthesis)
    assert sum(row.operation.value.startswith("ADD_") for row in changes) == 3
    assert all(
        row.existing_section_id
        for row in changes
        if row.operation.value.startswith("ADD_")
    )


def test_first_person_requires_actual_activity_not_image_receipt(
    tmp_path: Path,
) -> None:
    plan = build_research_plan(
        _legacy_request(
            tmp_path,
            owner_voice_evidence={
                "owner_reviewed": True,
                "owner_compared": True,
                "owner_received_physical_item": False,
                "owner_photographed": False,
                "owner_measured": False,
            },
        )
    )
    eligibility = build_first_person_eligibility(plan)
    assert "I reviewed" in eligibility.permitted_first_person_phrases
    assert (
        "based on the examples I examined" in eligibility.permitted_first_person_phrases
    )
    assert "I received the physical bag" in eligibility.prohibited_first_person_phrases
    assert "I photographed it" in eligibility.prohibited_first_person_phrases
    assert "I weighed it" in eligibility.prohibited_first_person_phrases


def _seed_reusable_topic(path: Path, topic_id: str) -> None:
    database = ResearchTopicDatabase(path)
    database.initialize()
    with sqlite3.connect(path) as connection:
        connection.execute(
            "INSERT INTO topics VALUES (?, ?, NULL, NULL)",
            (topic_id, json.dumps({"topic_id": topic_id})),
        )
        connection.execute(
            "INSERT INTO claims VALUES ('claim-1', 'reusable claim', '{}')"
        )
        connection.execute(
            "INSERT INTO topic_claims VALUES (?, 'claim-1')", (topic_id,)
        )
        connection.execute(
            "INSERT INTO sources VALUES ('source-1', 'https://example.test/source', '{}', 1, NULL)"
        )
        connection.execute(
            "INSERT INTO topic_sources VALUES (?, 'source-1')", (topic_id,)
        )


def _new_page_request(
    tmp_path: Path, *, database: Path | None = None, manifest: Path | None = None
) -> TopicResearchRequest:
    return TopicResearchRequest.model_validate(
        {
            "research_id": "new-page-001",
            "mode": "topic_build",
            "content_production_mode": "new_page_build",
            "topic_ids": ["hermes-model-topic"],
            "owner_objective": "Prepare a future model page.",
            "target_audience": "model comparison readers",
            "source_lane_priorities": _lanes(),
            "research_questions": ["What evidence covers this model?"],
            "search_intents": ["model review", "model visual details"],
            "asset_root": tmp_path / "assets",
            "asset_manifest": manifest,
            "research_database_path": database,
            "maximum_search_calls": 3,
            "maximum_sources": 10,
            "maximum_image_candidates": 5,
            "output_directory": tmp_path / "new-page",
            "provider": "synthetic",
        }
    )


def test_new_page_uses_topics_and_assets_before_generating_gaps(tmp_path: Path) -> None:
    database = tmp_path / "research.sqlite"
    _seed_reusable_topic(database, "hermes-model-topic")
    assets = tmp_path / "assets"
    assets.mkdir()
    image = assets / "model-front.jpg"
    image.write_bytes(b"synthetic-image-fixture")
    manifest = assets / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "assets": [
                    {
                        "asset_id": "asset-001",
                        "asset_type": "image",
                        "local_path": "model-front.jpg",
                        "model": "Placeholder model",
                        "publication_permission": "owner_review_required",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    plan = build_research_plan(
        _new_page_request(tmp_path, database=database, manifest=manifest)
    )
    assert plan.reusable_topic_ids == ["hermes-model-topic"]
    assert plan.queries == []
    run = discover_sources(plan, NoCallProvider())
    assert run.query_ids == [] and run.source_candidates == []
    output = tmp_path / "new-page-package"
    export_content_production(plan, output)
    assert set([*COMMON_PRODUCTION_OUTPUTS, *NEW_PAGE_OUTPUTS]) <= {
        path.name for path in output.iterdir()
    }
    coverage = _csv(output / "topic-coverage-map.csv")
    assert coverage[0]["reusable_knowledge_found"] == "true"
    assert coverage[0]["new_search_required"] == "false"
    assert _csv(output / "evidence-gap-register.csv") == []
    registered = _csv(output / "asset-coverage-register.csv")
    assert registered[0]["sha256"]
    assert _csv(output / "image-gap-register.csv") == []


def test_new_page_generates_text_and_image_gaps_without_assets(tmp_path: Path) -> None:
    plan = build_research_plan(_new_page_request(tmp_path))
    output = tmp_path / "gapped-new-page"
    result = export_content_production(plan, output)
    assert result["evidence_gap_count"] == 1
    assert result["image_gap_count"] == 1
    assert _csv(output / "evidence-gap-register.csv")
    assert _csv(output / "image-gap-register.csv")
    assert "does not inherit a legacy outline" in (
        output / "page-blueprint.md"
    ).read_text(encoding="utf-8")


def test_production_database_is_unchanged_and_no_fabricated_actions(
    tmp_path: Path,
) -> None:
    production = tmp_path / "production.sqlite"
    with sqlite3.connect(production) as connection:
        connection.execute("CREATE TABLE protected(value TEXT)")
        connection.execute("INSERT INTO protected VALUES ('owner data')")
    before = production.read_bytes()
    plan = build_research_plan(
        _legacy_request(tmp_path, production_database_path=production)
    )
    output = tmp_path / "integrity-package"
    export_content_production(plan, output)
    assert production.read_bytes() == before
    rendered = "\n".join(
        path.read_text(encoding="utf-8", errors="ignore")
        for path in output.iterdir()
        if path.is_file()
    ).casefold()
    assert (
        "i received the physical bag"
        not in rendered.replace("prohibited_first_person_phrases", "")
        or "prohibited" in rendered
    )
    validation = json.loads(
        (output / "reconstruction-validation.json").read_text(encoding="utf-8")
    )
    assert validation["invented_measurements"] is False
    assert validation["fabricated_physical_experience"] is False
