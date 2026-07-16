"""Deterministic research artifact loading, writing, and owner-review export."""

from __future__ import annotations

import importlib
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ValidationError

from reinaluxe_recovery.community.io import (
    prepare_output,
    write_csv,
    write_json,
    write_text,
)
from reinaluxe_recovery.research.analysis import ResearchAnalysisBundle
from reinaluxe_recovery.research.contracts import (
    ArticleResearchRequest,
    ResearchMode,
    ResearchPlan,
    ResearchRequest,
    ResearchSnapshot,
    SearchRun,
    TopicResearchRequest,
)
from reinaluxe_recovery.research.errors import ResearchArtifactError

STANDARD_OUTPUTS = (
    "research-executive-brief.md",
    "research-plan.json",
    "query-plan.csv",
    "source-register.csv",
    "source-exclusions.csv",
    "candidate-claims.csv",
    "source-to-claim-map.csv",
    "corroboration-register.csv",
    "contradiction-register.csv",
    "insufficient-evidence.csv",
    "image-candidates.csv",
    "image-evidence-register.csv",
    "topic-knowledge-opportunities.csv",
    "article-content-opportunities.csv",
    "owner-review.md",
    "research-snapshot.json",
    "validation.json",
)


def load_research_request(path: Path) -> ResearchRequest:
    payload = _read_mapping(path)
    try:
        raw_mode = payload.get("mode")
        if not isinstance(raw_mode, str):
            raise ValueError("mode is required")
        mode = ResearchMode(raw_mode)
        model = (
            ArticleResearchRequest
            if mode
            in {
                ResearchMode.ARTICLE_RESEARCH,
                ResearchMode.CLAIM_VERIFY,
                ResearchMode.EVIDENCE_GAP_FILL,
                ResearchMode.VISUAL_RESEARCH,
            }
            and any(
                payload.get(key)
                for key in (
                    "target_article_url",
                    "article_version_id",
                    "article_source_path",
                )
            )
            else TopicResearchRequest
        )
        return model.model_validate(payload)
    except (ValueError, ValidationError) as error:
        raise ResearchArtifactError(
            f"invalid research request: {_validation(error)}"
        ) from error


def write_plan(plan: ResearchPlan, output: Path) -> None:
    prepare_output(output)
    write_json(output / "research-plan.json", plan.model_dump(mode="json"))
    write_csv(
        output / "query-plan.csv",
        [
            "query_id",
            "research_question_id",
            "source_lane",
            "search_text",
            "positive_terms",
            "exclusion_terms",
            "temporal_range",
            "brand_scope",
            "model_scope",
            "target_article_section",
            "expected_evidence_type",
            "stopping_criteria",
            "language",
        ],
        [item.model_dump(mode="json") for item in plan.queries],
    )


def load_plan(path: Path) -> ResearchPlan:
    return _load_model(_artifact(path, "research-plan.json"), ResearchPlan)


def write_run(run: SearchRun, plan: ResearchPlan, output: Path) -> None:
    prepare_output(output)
    write_plan(plan, output)
    write_json(output / "research-run.json", run.model_dump(mode="json"))
    write_csv(
        output / "source-register.csv",
        _fields(run.source_candidates),
        [item.model_dump(mode="json") for item in run.source_candidates],
    )
    write_csv(
        output / "source-exclusions.csv",
        ["query_id", "url", "reason", "duplicate_of_source_id"],
        run.exclusions,
    )
    write_csv(
        output / "image-candidates.csv",
        _fields(run.image_candidates),
        [item.model_dump(mode="json") for item in run.image_candidates],
    )


def load_run(path: Path) -> tuple[SearchRun, ResearchPlan]:
    return (
        _load_model(_artifact(path, "research-run.json"), SearchRun),
        load_plan(path),
    )


def write_analysis(bundle: ResearchAnalysisBundle, output: Path) -> None:
    prepare_output(output)
    write_run(bundle.run, bundle.plan, output)
    write_json(output / "research-analysis.json", bundle.model_dump(mode="json"))
    _write_analysis_csvs(bundle, output)


def load_analysis(path: Path) -> ResearchAnalysisBundle:
    return _load_model(
        _artifact(path, "research-analysis.json"), ResearchAnalysisBundle
    )


def write_snapshot(snapshot: ResearchSnapshot, output: Path) -> None:
    prepare_output(output)
    write_json(output / "research-snapshot.json", snapshot.model_dump(mode="json"))


def load_snapshot(path: Path) -> ResearchSnapshot:
    return _load_model(_artifact(path, "research-snapshot.json"), ResearchSnapshot)


def export_review_package(
    bundle: ResearchAnalysisBundle,
    snapshot: ResearchSnapshot,
    output: Path,
) -> dict[str, Any]:
    """Export every standard artifact without drafting or modifying an article."""
    write_analysis(bundle, output)
    write_snapshot(snapshot, output)
    corroborated = [
        item
        for item in bundle.claim_clusters
        if item.assessment.value == "corroborated"
    ]
    insufficient = [
        item
        for item in bundle.claim_clusters
        if item.assessment.value in {"single_source", "insufficient_evidence"}
    ]
    brief = (
        f"# Research executive brief: {bundle.research_id}\n\n"
        f"- Screened sources: {len(bundle.run.source_candidates)}\n"
        f"- Atomic candidate claims: {len(bundle.candidate_claims)}\n"
        f"- Corroborated claim clusters: {len(corroborated)}\n"
        f"- Preserved contradictions: {len(bundle.contradictions)}\n"
        f"- Insufficient-evidence clusters: {len(insufficient)}\n"
        f"- Image candidates requiring permission review: {len(bundle.run.image_candidates)}\n\n"
        "This package contains research opportunities only. It does not draft, publish, "
        "shorten, or modify article content.\n"
    )
    write_text(output / "research-executive-brief.md", brief)
    write_text(output / "owner-review.md", _owner_review(bundle, snapshot))
    validation = {
        "schema_version": "1.0",
        "research_id": bundle.research_id,
        "valid": True,
        "standard_outputs_present": list(STANDARD_OUTPUTS),
        "wordpress_modified": False,
        "production_sqlite_modified": False,
        "article_copy_drafted": False,
        "live_api_used_during_export": False,
        "credentials_serialized": False,
        "images_downloaded": False,
        "visual_authenticity_inferred": False,
        "source_traceability_complete": all(
            any(link.claim_id == claim.claim_id for link in bundle.claim_evidence_links)
            for claim in bundle.candidate_claims
        ),
        "snapshot_hash": snapshot.snapshot_hash,
    }
    write_json(output / "validation.json", validation)
    missing = [name for name in STANDARD_OUTPUTS if not (output / name).is_file()]
    if missing:
        raise ResearchArtifactError(
            "review export omitted standard outputs: " + ", ".join(missing)
        )
    return validation


def _write_analysis_csvs(bundle: ResearchAnalysisBundle, output: Path) -> None:
    write_csv(
        output / "candidate-claims.csv",
        _fields(bundle.candidate_claims),
        [item.model_dump(mode="json") for item in bundle.candidate_claims],
    )
    write_csv(
        output / "source-to-claim-map.csv",
        _fields(bundle.claim_evidence_links),
        [item.model_dump(mode="json") for item in bundle.claim_evidence_links],
    )
    write_csv(
        output / "corroboration-register.csv",
        _fields(bundle.claim_clusters),
        [item.model_dump(mode="json") for item in bundle.claim_clusters],
    )
    write_csv(
        output / "contradiction-register.csv",
        _fields(bundle.contradictions),
        [item.model_dump(mode="json") for item in bundle.contradictions],
    )
    insufficient = [
        item.model_dump(mode="json")
        for item in bundle.claim_clusters
        if item.assessment.value in {"single_source", "insufficient_evidence"}
    ]
    write_csv(
        output / "insufficient-evidence.csv",
        _fields(bundle.claim_clusters),
        insufficient,
    )
    write_csv(
        output / "image-evidence-register.csv",
        _fields(bundle.image_evidence_records),
        [item.model_dump(mode="json") for item in bundle.image_evidence_records],
    )
    write_csv(
        output / "topic-knowledge-opportunities.csv",
        ["topic_id", "claim_id", "source_ids", "opportunity"],
        bundle.topic_knowledge_opportunities,
    )
    write_csv(
        output / "article-content-opportunities.csv",
        _fields(bundle.article_content_opportunities),
        [item.model_dump(mode="json") for item in bundle.article_content_opportunities],
    )


def _owner_review(bundle: ResearchAnalysisBundle, snapshot: ResearchSnapshot) -> str:
    lines = [
        f"# Owner research review: {bundle.research_id}",
        "",
        "All decisions are intentionally blank. Review citations and limitations before approving reuse.",
        "",
        "## Claim and article opportunities",
        "",
        "| Opportunity | Assessment | Target section | Owner decision |",
        "|---|---|---|---|",
    ]
    cluster_by_claim = {item.canonical_claim_id: item for item in bundle.claim_clusters}
    for item in bundle.article_content_opportunities:
        assessment = (
            cluster_by_claim[item.claim_ids[0]].assessment.value
            if item.claim_ids
            else "n/a"
        )
        lines.append(
            f"| {item.opportunity_id} | {assessment} | {item.target_section or ''} | |"
        )
    lines.extend(
        [
            "",
            "## Image candidates",
            "",
            "| Image | Source | Permission | Owner decision |",
            "|---|---|---|---|",
        ]
    )
    for image_candidate in bundle.run.image_candidates:
        lines.append(
            f"| {image_candidate.image_id} | {image_candidate.source_page_url} | "
            f"{image_candidate.publication_permission_status.value} | |"
        )
    lines.extend(
        [
            "",
            "## Safeguards",
            "",
            "- Images are not proof of provenance or authenticity.",
            "- No image is approved for publication until permission is reviewed.",
            "- Contradictions remain unresolved unless evidence supports a scoped resolution.",
            "- No WordPress or production article modification is authorized.",
            "",
            f"Snapshot: `{snapshot.snapshot_id}`",
            "",
        ]
    )
    return "\n".join(lines)


def _read_mapping(path: Path) -> dict[str, Any]:
    try:
        text = path.read_text(encoding="utf-8-sig")
    except OSError as error:
        raise ResearchArtifactError(
            f"could not read research artifact: {path}"
        ) from error
    try:
        value = json.loads(text)
    except json.JSONDecodeError as json_error:
        try:
            yaml_module: Any = importlib.import_module("yaml")
            value = yaml_module.safe_load(text)
        except (ImportError, Exception) as error:
            raise ResearchArtifactError(
                "request YAML requires PyYAML; JSON syntax is valid in .yaml templates"
            ) from (error if not isinstance(error, ImportError) else json_error)
    if not isinstance(value, dict):
        raise ResearchArtifactError("research artifact must contain an object")
    return value


def _load_model[ModelT: BaseModel](path: Path, model: type[ModelT]) -> ModelT:
    try:
        return model.model_validate_json(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValidationError) as error:
        raise ResearchArtifactError(
            f"invalid research artifact: {path.name}"
        ) from error


def _artifact(path: Path, name: str) -> Path:
    return path / name if path.is_dir() else path


def _fields(records: Sequence[BaseModel]) -> list[str]:
    return list(records[0].model_dump(mode="json")) if records else ["schema_version"]


def _validation(error: Exception) -> str:
    if isinstance(error, ValidationError):
        return "; ".join(
            f"{'.'.join(str(value) for value in item['loc'])}: {item['msg']}"
            for item in error.errors(include_url=False, include_input=False)
        )
    return str(error)
