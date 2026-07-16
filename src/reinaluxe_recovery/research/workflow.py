"""Application boundary for research CLI stages."""

from __future__ import annotations

from pathlib import Path

from reinaluxe_recovery.research.analysis import (
    SourceAnalysisProvider,
    analyze_search_run,
)
from reinaluxe_recovery.research.artifacts import (
    export_review_package,
    load_analysis,
    load_plan,
    load_research_request,
    load_run,
    load_snapshot,
    write_analysis,
    write_plan,
    write_run,
    write_snapshot,
)
from reinaluxe_recovery.research.contracts import ResearchSnapshot
from reinaluxe_recovery.research.database import (
    DEFAULT_RESEARCH_DATABASE,
    build_research_snapshot,
)
from reinaluxe_recovery.research.planning import build_research_plan
from reinaluxe_recovery.research.production import export_content_production
from reinaluxe_recovery.research.providers import (
    ResearchProviderRegistry,
    ResearchSearchProvider,
    ZhipuGLMSourceAnalyzer,
    default_provider_registry,
)
from reinaluxe_recovery.research.screening import discover_sources


def research_plan(request_path: Path, output: Path) -> None:
    request = load_research_request(request_path)
    plan = build_research_plan(request)
    write_plan(plan, output)
    export_content_production(plan, output)


def research_discover(
    plan_path: Path,
    output: Path,
    *,
    provider: ResearchSearchProvider | None = None,
    registry: ResearchProviderRegistry | None = None,
) -> None:
    plan = load_plan(plan_path)
    selected = provider or (registry or default_provider_registry()).create(
        plan.provider
    )
    write_run(discover_sources(plan, selected), plan, output)


def research_analyze(
    run_path: Path,
    output: Path,
    *,
    analyzer: SourceAnalysisProvider | None = None,
    glm_assisted: bool = False,
) -> None:
    run, plan = load_run(run_path)
    selected = analyzer or (ZhipuGLMSourceAnalyzer() if glm_assisted else None)
    bundle = analyze_search_run(run, plan, selected)
    write_analysis(bundle, output)
    export_content_production(plan, output, bundle=bundle)


def research_build_snapshot(
    analysis_path: Path,
    output: Path,
    *,
    database_path: Path = DEFAULT_RESEARCH_DATABASE,
    production_database_path: Path | None = None,
) -> ResearchSnapshot:
    bundle = load_analysis(analysis_path)
    snapshot = build_research_snapshot(
        bundle,
        database_path,
        production_database_path=production_database_path,
    )
    write_analysis(bundle, output)
    export_content_production(bundle.plan, output, bundle=bundle)
    write_snapshot(snapshot, output)
    return snapshot


def research_export_review(
    analysis_path: Path,
    output: Path,
    *,
    database_path: Path = DEFAULT_RESEARCH_DATABASE,
    production_database_path: Path | None = None,
) -> dict[str, object]:
    bundle = load_analysis(analysis_path)
    snapshot_path = (
        analysis_path / "research-snapshot.json"
        if analysis_path.is_dir()
        else analysis_path.with_name("research-snapshot.json")
    )
    snapshot = (
        load_snapshot(snapshot_path)
        if snapshot_path.is_file()
        else build_research_snapshot(
            bundle,
            database_path,
            production_database_path=production_database_path,
        )
    )
    return export_review_package(bundle, snapshot, output)


def research_refresh(
    request_path: Path,
    output: Path,
    *,
    provider: ResearchSearchProvider | None = None,
    analyzer: SourceAnalysisProvider | None = None,
    glm_assisted: bool = False,
    database_path: Path = DEFAULT_RESEARCH_DATABASE,
) -> None:
    """Run the bounded refresh pipeline while retaining stage artifacts."""
    plan_dir = output / "plan"
    run_dir = output / "run"
    analysis_dir = output / "analysis"
    review_dir = output / "review"
    research_plan(request_path, plan_dir)
    research_discover(plan_dir, run_dir, provider=provider)
    research_analyze(
        run_dir,
        analysis_dir,
        analyzer=analyzer,
        glm_assisted=glm_assisted,
    )
    research_build_snapshot(analysis_dir, analysis_dir, database_path=database_path)
    research_export_review(analysis_dir, review_dir, database_path=database_path)


def research_image_review(analysis_path: Path, output: Path) -> None:
    """Export image metadata and blank owner decisions without downloading images."""
    bundle = load_analysis(analysis_path)
    output.mkdir(parents=True, exist_ok=True)
    from reinaluxe_recovery.community.io import write_csv, write_text

    fields = [
        "image_id",
        "source_id",
        "image_url",
        "source_page_url",
        "alt_text",
        "caption",
        "publication_permission_status",
        "owner_review_status",
        "owner_decision",
        "owner_rationale",
    ]
    rows = [
        {
            **item.model_dump(mode="json"),
            "owner_decision": "",
            "owner_rationale": "",
        }
        for item in bundle.run.image_candidates
    ]
    write_csv(output / "image-review.csv", fields, rows)
    write_text(
        output / "image-review.md",
        "# Image research review\n\nNo images were downloaded or approved. Appearance does not prove provenance or authenticity.\n",
    )
