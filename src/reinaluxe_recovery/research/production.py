"""Content-production modes and traceable assertive editorial synthesis."""

from __future__ import annotations

import csv
import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ValidationError

from reinaluxe_recovery.community.io import write_csv, write_json, write_text
from reinaluxe_recovery.community.normalization import normalize_text, stable_id
from reinaluxe_recovery.research.analysis import ResearchAnalysisBundle
from reinaluxe_recovery.research.contracts import (
    ContentChangeOperation,
    ContentProductionMode,
    ContentTransformationRecord,
    EditorialSynthesisRecord,
    EvidenceAssessment,
    EvidenceOwnershipClass,
    ExistingArticleSection,
    FirstPersonEligibilityRecord,
    NewPageAssetRecord,
    PublicationIntensity,
    ResearchPlan,
)
from reinaluxe_recovery.research.errors import ResearchArtifactError

LEGACY_OUTPUTS = (
    "page-reconstruction-brief.md",
    "existing-section-register.csv",
    "section-research-map.csv",
    "section-enrichment-copy.md",
    "image-to-section-map.csv",
    "visual-analysis-copy.csv",
    "claims-and-limitations.csv",
    "internal-link-plan.csv",
    "metadata-options.md",
    "content-change-manifest.csv",
    "reconstruction-validation.json",
)

NEW_PAGE_OUTPUTS = (
    "new-page-research-brief.md",
    "search-intent-map.csv",
    "topic-coverage-map.csv",
    "asset-coverage-register.csv",
    "evidence-gap-register.csv",
    "image-gap-register.csv",
    "page-blueprint.md",
    "section-evidence-map.csv",
    "image-placement-plan.csv",
    "internal-link-plan.csv",
    "metadata-options.md",
    "drafting-readiness.md",
)

COMMON_PRODUCTION_OUTPUTS = (
    "content-transformation-register.csv",
    "first-person-eligibility-register.csv",
    "assertive-narrative-register.csv",
    "publication-wording-options.csv",
    "prohibited-overclaim-register.csv",
)

_TOKEN = re.compile(r"[\w]+", re.UNICODE)
_INTENSITY_RANK = {
    PublicationIntensity.RESTRAINED: 0,
    PublicationIntensity.ASSERTIVE: 1,
    PublicationIntensity.HIGHLY_ASSERTIVE_BUT_SUPPORTABLE: 2,
}


def build_first_person_eligibility(plan: ResearchPlan) -> FirstPersonEligibilityRecord:
    """Allow only first-person phrases backed by explicit owner-activity flags."""
    evidence = plan.owner_voice_evidence
    permitted: list[str] = []
    if evidence.owner_reviewed:
        permitted.extend(["I reviewed", "in the discussions I reviewed"])
    if evidence.owner_compared:
        permitted.extend(["I compared", "based on the examples I examined"])
    if evidence.owner_analyzed:
        permitted.extend(["I analyzed", "what stood out to me", "my assessment is"])
    if evidence.owner_sourcing_conversation:
        permitted.append("in my sourcing conversations")
    if evidence.owner_received_physical_item:
        permitted.append("I received the physical bag")
    if evidence.owner_photographed:
        permitted.append("I photographed it")
    if evidence.owner_measured:
        permitted.append("I weighed it")
    if evidence.owner_physically_handled:
        permitted.append("in hand it felt")
    if evidence.owner_used_long_term:
        permitted.append("I used it for months")
    if evidence.authorized_client_case:
        permitted.append("my customer received it")

    controlled = [
        "I received the physical bag",
        "I photographed it",
        "I weighed it",
        "in hand it felt",
        "I used it for months",
        "my customer received it",
    ]
    analytical = [
        "I reviewed",
        "I compared",
        "I analyzed",
        "what stood out to me",
        "my assessment is",
        "based on the examples I examined",
        "in the discussions I reviewed",
        "in my sourcing conversations",
    ]
    prohibited = sorted(set([*controlled, *analytical]) - set(permitted))
    if evidence.owner_analyzed:
        strongest = "My assessment is grounded in the examples I analyzed."
    elif evidence.owner_compared:
        strongest = "Based on the examples I examined, the pattern is clear."
    elif evidence.owner_reviewed:
        strongest = "In the discussions I reviewed, this pattern was consistent."
    else:
        strongest = "The editorial assessment is grounded in the reviewed evidence."
    return FirstPersonEligibilityRecord(
        eligibility_id=stable_id("first_person", plan.research_id),
        research_id=plan.research_id,
        **evidence.model_dump(exclude={"schema_version"}),
        permitted_first_person_phrases=sorted(set(permitted)),
        prohibited_first_person_phrases=prohibited,
        strongest_owner_voice_wording=strongest,
    )


def build_editorial_synthesis(
    plan: ResearchPlan, bundle: ResearchAnalysisBundle | None = None
) -> list[EditorialSynthesisRecord]:
    """Generate traceable wording levels without inventing owner actions or facts."""
    if bundle is None:
        return []
    claims = {item.claim_id: item for item in bundle.candidate_claims}
    sources = {item.source_id: item for item in bundle.run.source_candidates}
    links_by_claim: dict[str, list[Any]] = defaultdict(list)
    for link in bundle.claim_evidence_links:
        links_by_claim[link.claim_id].append(link)
    contradiction_claims = {
        claim_id for item in bundle.contradictions for claim_id in item.claim_ids
    }
    output: list[EditorialSynthesisRecord] = []
    for cluster in bundle.claim_clusters:
        claim = claims[cluster.canonical_claim_id]
        links = links_by_claim[claim.claim_id]
        source_ids = sorted({item.source_id for item in links})
        source_clusters = {
            str(
                sources[source_id].metadata.get("seller_source_cluster")
                or sources[source_id].domain
            )
            for source_id in source_ids
        }
        lane_count = len({sources[source_id].source_lane for source_id in source_ids})
        visual_count = sum(
            1 for image in bundle.run.image_candidates if image.source_id in source_ids
        )
        contradiction = claim.claim_id in contradiction_claims
        allowed = _allowed_intensity(
            cluster.assessment, len(source_clusters), contradiction
        )
        selected_intensity = _lower_intensity(plan.publication_intensity, allowed)
        source_observation = claim.claim_text.rstrip(".") + "."
        inference = _editorial_inference(
            source_observation,
            len(source_clusters),
            lane_count,
            visual_count,
            contradiction,
        )
        restrained = f"The reviewed evidence indicates that {claim.claim_text.rstrip('.').lower()}."
        assertive = (
            f"{_sentence(claim.claim_text)} This is a consistent market observation "
            f"across the reviewed evidence."
        )
        highly = (
            f"{_sentence(claim.claim_text)} It is one of the clearest patterns in the "
            "reviewed examples and a practical quality signal for buyers."
        )
        wording = {
            PublicationIntensity.RESTRAINED: restrained,
            PublicationIntensity.ASSERTIVE: assertive,
            PublicationIntensity.HIGHLY_ASSERTIVE_BUT_SUPPORTABLE: highly,
        }[selected_intensity]
        limitation = (
            "The conclusion is scoped to the reviewed examples and source conditions."
            if not contradiction
            else "The sources disagree, so the conclusion must retain its stated scope."
        )
        output.append(
            EditorialSynthesisRecord(
                synthesis_id=stable_id("synthesis", claim.claim_id),
                research_id=plan.research_id,
                claim_id=claim.claim_id,
                evidence_ownership_class=(
                    EvidenceOwnershipClass.OWNER_MARKET_SYNTHESIS
                    if plan.content_production_mode
                    is ContentProductionMode.LEGACY_RECONSTRUCTION
                    else EvidenceOwnershipClass.OWNER_ANALYSIS_OF_EXTERNAL_EVIDENCE
                ),
                source_observation=source_observation,
                source_count=len(source_ids),
                source_lane_count=lane_count,
                visual_evidence_count=visual_count,
                contradiction_status="present" if contradiction else "none",
                editorial_inference=inference,
                restrained_wording=restrained,
                assertive_wording=assertive,
                highly_assertive_but_supportable_wording=highly,
                publication_intensity_allowed=allowed,
                selected_publication_wording=wording,
                concise_limitation=limitation,
                prohibited_unsupported_extension=(
                    "Do not extend this finding to material composition, authentic origin, "
                    "factory-wide consistency, receipt, handling, photography, measurement, "
                    "customer outcomes, or universal performance."
                ),
                proposed_section=(
                    claim.proposed_article_sections[0]
                    if claim.proposed_article_sections
                    else None
                ),
                narrative_value="Turns a source pattern into a clear editorial point.",
                reader_usefulness="Helps readers evaluate a concrete market signal.",
                conversion_value="Builds decision confidence without promising an outcome.",
            )
        )
    return sorted(output, key=lambda item: item.synthesis_id)


def build_content_transformations(
    plan: ResearchPlan,
    synthesis: list[EditorialSynthesisRecord],
    bundle: ResearchAnalysisBundle | None = None,
) -> list[ContentTransformationRecord]:
    sections = plan.article_analysis.existing_sections if plan.article_analysis else []
    if plan.content_production_mode is not ContentProductionMode.LEGACY_RECONSTRUCTION:
        return []
    source_ids_by_claim: dict[str, list[str]] = defaultdict(list)
    question_by_claim: dict[str, str] = {}
    if bundle is not None:
        query_by_id = {item.query_id: item for item in plan.queries}
        source_by_id = {item.source_id: item for item in bundle.run.source_candidates}
        for link in bundle.claim_evidence_links:
            source_ids_by_claim[link.claim_id].append(link.source_id)
            source = source_by_id[link.source_id]
            question_by_claim.setdefault(
                link.claim_id, query_by_id[source.query_id].research_question_id
            )
    image_ids_by_source: dict[str, list[str]] = defaultdict(list)
    if bundle is not None:
        for image in bundle.run.image_candidates:
            image_ids_by_source[image.source_id].append(image.image_id)
    output: list[ContentTransformationRecord] = []
    enriched_sections: set[str] = set()
    new_sections = 0
    for item in synthesis:
        section = _match_section(item.proposed_section, sections)
        operation = ContentChangeOperation.ENRICH
        if section is None:
            if new_sections >= plan.maximum_new_sections:
                continue
            operation = ContentChangeOperation.ADD_AFTER
            new_sections += 1
            section = sections[-1] if sections else None
        else:
            enriched_sections.add(section.section_id)
        source_ids = sorted(set(source_ids_by_claim.get(item.claim_id or "", [])))
        image_ids = sorted(
            {
                image_id
                for source_id in source_ids
                for image_id in image_ids_by_source[source_id]
            }
            | (set(section.image_ids) if section else set())
        )
        output.append(
            ContentTransformationRecord(
                transformation_id=stable_id(
                    "transformation",
                    {
                        "synthesis_id": item.synthesis_id,
                        "section_id": section.section_id if section else None,
                    },
                ),
                research_id=plan.research_id,
                existing_section_id=section.section_id if section else None,
                research_question_id=question_by_claim.get(item.claim_id or ""),
                supporting_source_ids=source_ids,
                relevant_image_ids=image_ids,
                source_observation=item.source_observation,
                editorial_inference=item.editorial_inference,
                publication_wording=item.selected_publication_wording,
                concise_limitation=item.concise_limitation,
                operation=operation,
                preserves_distinctive_content=plan.preserve_distinctive_content,
                preserves_existing_images=plan.preserve_existing_images,
            )
        )
    for section in sections:
        if section.section_id in enriched_sections:
            continue
        mapped_question = next(
            (
                question.question_id
                for question in plan.questions
                if _match_section(
                    question.target_article_section or question.question, sections
                )
                == section
            ),
            None,
        )
        if mapped_question is None and plan.questions:
            mapped_question = plan.questions[
                section.order % len(plan.questions)
            ].question_id
        output.append(
            ContentTransformationRecord(
                transformation_id=stable_id("transformation_keep", section.section_id),
                research_id=plan.research_id,
                existing_section_id=section.section_id,
                research_question_id=mapped_question,
                relevant_image_ids=section.image_ids,
                source_observation="The existing section remains part of the published page structure.",
                editorial_inference="Retain the section unless later evidence supports a scoped enrichment.",
                publication_wording="Existing wording retained in the planning-only package.",
                concise_limitation="No new evidence-backed wording is proposed for this section yet.",
                operation=ContentChangeOperation.KEEP,
                preserves_distinctive_content=True,
                preserves_existing_images=True,
            )
        )
    return sorted(output, key=lambda item: item.transformation_id)


def export_content_production(
    plan: ResearchPlan,
    output: Path,
    *,
    bundle: ResearchAnalysisBundle | None = None,
) -> dict[str, Any]:
    """Write common synthesis registers and the selected mode-specific package."""
    output.mkdir(parents=True, exist_ok=True)
    synthesis = build_editorial_synthesis(plan, bundle)
    eligibility = build_first_person_eligibility(plan)
    transformations = build_content_transformations(plan, synthesis, bundle)
    _write_models(
        output / "content-transformation-register.csv",
        ContentTransformationRecord,
        transformations,
    )
    _write_models(
        output / "first-person-eligibility-register.csv",
        FirstPersonEligibilityRecord,
        [eligibility],
    )
    _write_models(
        output / "assertive-narrative-register.csv",
        EditorialSynthesisRecord,
        synthesis,
    )
    wording_rows = [
        {
            "synthesis_id": item.synthesis_id,
            "restrained": item.restrained_wording,
            "assertive": item.assertive_wording,
            "highly_assertive_but_supportable": item.highly_assertive_but_supportable_wording,
            "allowed": item.publication_intensity_allowed.value,
            "selected": item.selected_publication_wording,
        }
        for item in synthesis
    ]
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
        wording_rows,
    )
    write_csv(
        output / "prohibited-overclaim-register.csv",
        ["synthesis_id", "claim_id", "prohibited_unsupported_extension"],
        [
            {
                "synthesis_id": item.synthesis_id,
                "claim_id": item.claim_id,
                "prohibited_unsupported_extension": item.prohibited_unsupported_extension,
            }
            for item in synthesis
        ],
    )
    if plan.content_production_mode is ContentProductionMode.LEGACY_RECONSTRUCTION:
        result = _export_legacy(plan, output, synthesis, transformations, bundle)
    elif plan.content_production_mode is ContentProductionMode.NEW_PAGE_BUILD:
        result = _export_new_page(plan, output)
    else:
        result = {"mode": ContentProductionMode.RESEARCH_ONLY.value}
    return {
        **result,
        "synthesis_count": len(synthesis),
        "transformation_count": len(transformations),
    }


def load_asset_manifest(plan: ResearchPlan) -> list[NewPageAssetRecord]:
    path = plan.asset_manifest
    if path is None or not path.is_file():
        return []
    try:
        if path.suffix.casefold() == ".csv":
            with path.open("r", encoding="utf-8-sig", newline="") as handle:
                raw_records: Any = list(csv.DictReader(handle))
        else:
            raw = json.loads(path.read_text(encoding="utf-8-sig"))
            raw_records = raw.get("assets", []) if isinstance(raw, dict) else raw
    except (OSError, json.JSONDecodeError) as error:
        raise ResearchArtifactError(f"could not read asset manifest: {path}") from error
    if not isinstance(raw_records, list):
        raise ResearchArtifactError("asset manifest must contain an asset list")
    root = (plan.asset_root or path.parent).resolve()
    records: list[NewPageAssetRecord] = []
    for raw_record in raw_records:
        if not isinstance(raw_record, dict):
            raise ResearchArtifactError("asset manifest records must be objects")
        payload = {
            str(key): value
            for key, value in raw_record.items()
            if value is not None and value != ""
        }
        local_value = payload.get("local_path")
        if local_value:
            candidate = Path(str(local_value))
            resolved = (
                candidate.resolve()
                if candidate.is_absolute()
                else (root / candidate).resolve()
            )
            if not resolved.is_relative_to(root):
                raise ResearchArtifactError(
                    "asset local_path escapes the configured asset root"
                )
            payload["local_path"] = resolved
            if resolved.is_file():
                payload["sha256"] = hashlib.sha256(resolved.read_bytes()).hexdigest()
        try:
            records.append(NewPageAssetRecord.model_validate(payload))
        except ValidationError as error:
            raise ResearchArtifactError("invalid asset manifest record") from error
    return sorted(records, key=lambda item: item.asset_id)


def _export_legacy(
    plan: ResearchPlan,
    output: Path,
    synthesis: list[EditorialSynthesisRecord],
    transformations: list[ContentTransformationRecord],
    bundle: ResearchAnalysisBundle | None,
) -> dict[str, Any]:
    analysis = plan.article_analysis
    if analysis is None:
        raise ResearchArtifactError("legacy reconstruction requires article analysis")
    sections = analysis.existing_sections
    images = analysis.existing_images
    brief = (
        f"# Page reconstruction brief: {plan.research_id}\n\n"
        f"Mode: `{plan.content_production_mode.value}`\n\n"
        "Strengthen the published page through ENRICH-first changes while preserving its "
        "structure, legitimate first-person passages, distinctive material, and existing "
        "images. New owner-handled physical evidence is not required.\n\n"
        f"Maximum new sections: {plan.maximum_new_sections}. Publication intensity: "
        f"`{plan.publication_intensity.value}`.\n"
    )
    write_text(output / "page-reconstruction-brief.md", brief)
    _write_models(
        output / "existing-section-register.csv", ExistingArticleSection, sections
    )
    source_ids_by_question = _source_ids_by_question(plan, bundle)
    section_rows = []
    for question in plan.questions:
        section = _match_section(
            question.target_article_section or question.question, sections
        )
        section_rows.append(
            {
                "existing_section_id": section.section_id if section else "",
                "existing_heading": section.heading if section else "",
                "research_question_id": question.question_id,
                "research_question": question.question,
                "supporting_source_ids": source_ids_by_question.get(
                    question.question_id, []
                ),
                "status": "mapped" if section else "new_section_candidate",
            }
        )
    write_csv(
        output / "section-research-map.csv",
        [
            "existing_section_id",
            "existing_heading",
            "research_question_id",
            "research_question",
            "supporting_source_ids",
            "status",
        ],
        section_rows,
    )
    copy_lines = [f"# Section enrichment copy: {plan.research_id}", ""]
    if not synthesis:
        copy_lines.extend(
            [
                "Planning-only package: evidence-backed enrichment wording remains pending.",
                "",
            ]
        )
    for section in sections:
        items = [
            item
            for item in synthesis
            if _match_section(item.proposed_section, sections) == section
        ]
        if not items:
            continue
        copy_lines.extend(
            [
                f"## {section.heading}",
                "",
                "Scope: conclusions below apply to the reviewed examples and source conditions.",
                "",
            ]
        )
        copy_lines.extend(f"{item.selected_publication_wording}\n" for item in items)
    write_text(
        output / "section-enrichment-copy.md", "\n".join(copy_lines).rstrip() + "\n"
    )
    write_csv(
        output / "image-to-section-map.csv",
        ["image_id", "source_url", "section_id", "preserve", "reason"],
        [
            {
                "image_id": image.image_id,
                "source_url": image.source_url,
                "section_id": image.section_id,
                "preserve": True,
                "reason": "existing page image retained as a primary visual-analysis input",
            }
            for image in images
        ],
    )
    write_csv(
        output / "visual-analysis-copy.csv",
        ["image_id", "section_id", "visual_analysis_copy", "limitation"],
        [
            {
                "image_id": image.image_id,
                "section_id": image.section_id,
                "visual_analysis_copy": "Review shape, proportion, construction details, and visible comparison signals.",
                "limitation": "Appearance alone does not establish material composition, origin, or authenticity.",
            }
            for image in images
        ],
    )
    write_csv(
        output / "claims-and-limitations.csv",
        [
            "synthesis_id",
            "source_observation",
            "editorial_inference",
            "wording",
            "limitation",
        ],
        [
            {
                "synthesis_id": item.synthesis_id,
                "source_observation": item.source_observation,
                "editorial_inference": item.editorial_inference,
                "wording": item.selected_publication_wording,
                "limitation": item.concise_limitation,
            }
            for item in synthesis
        ],
    )
    _write_internal_links(output, sections)
    _write_metadata(output, analysis.title or analysis.h1 or plan.research_id)
    _write_models(
        output / "content-change-manifest.csv",
        ContentTransformationRecord,
        transformations,
    )
    new_section_count = sum(
        item.operation
        in {ContentChangeOperation.ADD_BEFORE, ContentChangeOperation.ADD_AFTER}
        for item in transformations
    )
    distinctive_text = " ".join(
        passage for section in sections for passage in section.distinctive_passages
    ).casefold()
    missing_distinctive = [
        requirement
        for requirement in plan.distinctive_content_requirements
        if requirement.casefold() not in distinctive_text
    ]
    validation = {
        "schema_version": "1.0",
        "research_id": plan.research_id,
        "mode": plan.content_production_mode.value,
        "planning_only": bundle is None,
        "wordpress_modified": False,
        "article_published": False,
        "article_content_modified": False,
        "live_search_used": False,
        "owner_physical_evidence_required": plan.owner_firsthand_evidence_required,
        "existing_sections_preserved": len(sections),
        "existing_images_preserved": len(images),
        "minimum_existing_image_count_met": len(images)
        >= plan.minimum_existing_image_count,
        "missing_distinctive_requirements": missing_distinctive,
        "delete_operations": sum(
            item.operation is ContentChangeOperation.DELETE for item in transformations
        ),
        "enrich_operations": sum(
            item.operation is ContentChangeOperation.ENRICH for item in transformations
        ),
        "new_section_count": new_section_count,
        "maximum_new_sections": plan.maximum_new_sections,
        "maximum_new_sections_respected": new_section_count
        <= plan.maximum_new_sections,
        "invented_measurements": False,
        "fabricated_physical_experience": False,
    }
    write_json(output / "reconstruction-validation.json", validation)
    _require_outputs(output, LEGACY_OUTPUTS)
    return validation


def _export_new_page(plan: ResearchPlan, output: Path) -> dict[str, Any]:
    assets = load_asset_manifest(plan)
    image_assets = [item for item in assets if item.asset_type == "image"]
    reusable = set(plan.reusable_topic_ids)
    write_text(
        output / "new-page-research-brief.md",
        f"# New page research brief: {plan.research_id}\n\n"
        "Inspect reusable topic evidence and the prepared asset manifest before targeted "
        "research. The page architecture does not inherit a legacy page. Owner-handled "
        "physical evidence is useful but not mandatory.\n",
    )
    write_csv(
        output / "search-intent-map.csv",
        ["search_intent", "priority", "research_required"],
        [
            {"search_intent": value, "priority": index + 1, "research_required": True}
            for index, value in enumerate(plan.search_intents)
        ],
    )
    topic_rows = [
        {
            "topic_id": topic_id,
            "reusable_knowledge_found": topic_id in reusable,
            "new_search_required": topic_id not in reusable,
        }
        for topic_id in sorted(
            {topic for question in plan.questions for topic in question.topic_ids}
        )
    ]
    write_csv(
        output / "topic-coverage-map.csv",
        ["topic_id", "reusable_knowledge_found", "new_search_required"],
        topic_rows,
    )
    _write_models(output / "asset-coverage-register.csv", NewPageAssetRecord, assets)
    evidence_gaps = [
        {
            "topic_id": row["topic_id"],
            "gap_type": "text_evidence",
            "query_requirement": f"Target only missing evidence for {row['topic_id']}",
        }
        for row in topic_rows
        if row["new_search_required"]
    ]
    write_csv(
        output / "evidence-gap-register.csv",
        ["topic_id", "gap_type", "query_requirement"],
        evidence_gaps,
    )
    image_gaps = (
        []
        if image_assets
        else [
            {
                "gap_id": stable_id("image_gap", plan.research_id),
                "gap": "No prepared image asset is registered.",
                "query_requirement": "Find source-linked visual evidence or prepare an owner-approved asset.",
            }
        ]
    )
    write_csv(
        output / "image-gap-register.csv",
        ["gap_id", "gap", "query_requirement"],
        image_gaps,
    )
    blueprint = [
        f"# Page blueprint: {plan.research_id}",
        "",
        "## Proposed architecture",
        "",
    ]
    for index, row in enumerate(topic_rows, start=1):
        blueprint.append(f"{index}. Evidence-led section for `{row['topic_id']}`")
    blueprint.extend(
        [
            "",
            "The final architecture must follow evidence and search intent; it does not inherit a legacy outline.",
            "",
        ]
    )
    write_text(output / "page-blueprint.md", "\n".join(blueprint))
    write_csv(
        output / "section-evidence-map.csv",
        ["topic_id", "evidence_status", "source"],
        [
            {
                "topic_id": row["topic_id"],
                "evidence_status": "reusable"
                if row["reusable_knowledge_found"]
                else "gap",
                "source": "research topic database"
                if row["reusable_knowledge_found"]
                else "targeted research required",
            }
            for row in topic_rows
        ],
    )
    write_csv(
        output / "image-placement-plan.csv",
        ["asset_id", "proposed_section", "permission", "status"],
        [
            {
                "asset_id": item.asset_id,
                "proposed_section": item.model or "owner review required",
                "permission": item.publication_permission,
                "status": "candidate",
            }
            for item in image_assets
        ],
    )
    write_csv(
        output / "internal-link-plan.csv",
        ["source_section", "target", "status"],
        [
            {
                "source_section": "page introduction",
                "target": "relevant existing hub selected during owner review",
                "status": "planning_only",
            }
        ],
    )
    _write_metadata(output, plan.research_id.replace("-", " ").title())
    readiness = (
        "# Drafting readiness\n\n"
        f"Reusable topics: {len(reusable)}. Registered assets: {len(assets)}. "
        f"Text evidence gaps: {len(evidence_gaps)}. Image gaps: {len(image_gaps)}.\n\n"
        "Drafting remains blocked until owner review resolves the listed evidence and image gaps.\n"
    )
    write_text(output / "drafting-readiness.md", readiness)
    _require_outputs(output, NEW_PAGE_OUTPUTS)
    return {
        "mode": plan.content_production_mode.value,
        "asset_count": len(assets),
        "reusable_topic_count": len(reusable),
        "evidence_gap_count": len(evidence_gaps),
        "image_gap_count": len(image_gaps),
        "owner_physical_evidence_required": plan.owner_firsthand_evidence_required,
    }


def _allowed_intensity(
    assessment: EvidenceAssessment, source_count: int, contradiction: bool
) -> PublicationIntensity:
    if (
        assessment is EvidenceAssessment.CORROBORATED
        and source_count >= 2
        and not contradiction
    ):
        return PublicationIntensity.HIGHLY_ASSERTIVE_BUT_SUPPORTABLE
    if source_count >= 2:
        return PublicationIntensity.ASSERTIVE
    return PublicationIntensity.RESTRAINED


def _lower_intensity(
    requested: PublicationIntensity, allowed: PublicationIntensity
) -> PublicationIntensity:
    return (
        requested if _INTENSITY_RANK[requested] <= _INTENSITY_RANK[allowed] else allowed
    )


def _editorial_inference(
    observation: str,
    source_count: int,
    lane_count: int,
    visual_count: int,
    contradiction: bool,
) -> str:
    if contradiction:
        return (
            "The pattern is editorially useful, but disagreement requires a scoped conclusion "
            "rather than a universal rule."
        )
    if source_count >= 2 and (lane_count >= 2 or visual_count):
        return "Independent observations converge strongly enough to support a clear market-level conclusion."
    return f"The observation is useful but remains narrowly supported: {observation}"


def _sentence(value: str) -> str:
    normalized = normalize_text(value).rstrip(".")
    return normalized[:1].upper() + normalized[1:] + "."


def _match_section(
    proposed: str | None, sections: list[ExistingArticleSection]
) -> ExistingArticleSection | None:
    if not sections:
        return None
    if not proposed:
        return sections[0]
    proposed_tokens = set(_TOKEN.findall(proposed.casefold()))
    scored = [
        (
            len(proposed_tokens & set(_TOKEN.findall(section.heading.casefold()))),
            -section.order,
            section,
        )
        for section in sections
    ]
    score, _, section = max(scored, key=lambda item: (item[0], item[1]))
    return section if score else None


def _source_ids_by_question(
    plan: ResearchPlan, bundle: ResearchAnalysisBundle | None
) -> dict[str, list[str]]:
    if bundle is None:
        return {}
    query_by_id = {item.query_id: item for item in plan.queries}
    output: dict[str, list[str]] = defaultdict(list)
    for source in bundle.run.source_candidates:
        query = query_by_id[source.query_id]
        output[query.research_question_id].append(source.source_id)
    return {key: sorted(set(value)) for key, value in output.items()}


def _write_internal_links(output: Path, sections: list[ExistingArticleSection]) -> None:
    write_csv(
        output / "internal-link-plan.csv",
        ["section_id", "target_url", "operation", "reason"],
        [
            {
                "section_id": section.section_id,
                "target_url": link,
                "operation": "KEEP",
                "reason": "preserve existing relevant internal link",
            }
            for section in sections
            for link in section.internal_links
        ],
    )


def _write_metadata(output: Path, title: str) -> None:
    write_text(
        output / "metadata-options.md",
        f"# Metadata options\n\n1. Preserve the current title intent: **{title}**\n"
        "2. Enrich the title only after evidence-backed section changes receive owner approval.\n",
    )


def _write_models[ModelT: BaseModel](
    path: Path, model: type[ModelT], records: list[ModelT]
) -> None:
    fields = list(model.model_fields)
    write_csv(path, fields, [item.model_dump(mode="json") for item in records])


def _require_outputs(output: Path, names: tuple[str, ...]) -> None:
    missing = [name for name in names if not (output / name).is_file()]
    if missing:
        raise ResearchArtifactError(
            "content production package is incomplete: " + ", ".join(missing)
        )
