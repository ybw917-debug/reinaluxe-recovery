"""Command-line entry point for ReinaLuxe Recovery OS."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

import typer
from pydantic import ValidationError
from rich.console import Console
from rich.table import Table
from sqlalchemy import Engine

from reinaluxe_recovery import __version__
from reinaluxe_recovery.acquisition import (
    AcquisitionError,
    AcquisitionRequest,
    AcquisitionSourceType,
    AcquisitionWorkflow,
    DiscoveryError,
    NoEligibleUrlsError,
    UnsafeTargetError,
    render_acquisition,
)
from reinaluxe_recovery.acquisition.discovery import load_url_list
from reinaluxe_recovery.application import (
    ArticleAuditWorkflow,
    OfflineImportWorkflow,
    PageNotFoundError,
    PageQueryService,
)
from reinaluxe_recovery.audit import (
    AuditOptions,
    AuditRuleCode,
    AuditSeverity,
    NoMatchingArticlesError,
    render_site_audit,
)
from reinaluxe_recovery.batch import (
    BatchFailureKind,
    BatchImportOptions,
    BatchImportResult,
    BatchImportWorkflow,
    BatchManifestError,
    BatchPathError,
    BatchSelectionError,
)
from reinaluxe_recovery.community import (
    CommunityWorkflowError,
    apply_community_decisions,
    build_community_knowledge_base,
    export_community_review,
    import_community_manifest,
)
from reinaluxe_recovery.content_ops import (
    ContentOpsError,
    apply_opportunity_decisions,
    build_content_change_manifest,
    build_knowledge_snapshot,
    build_page_context,
    export_opportunity_review,
    map_content_opportunities,
)
from reinaluxe_recovery.importing import (
    HtmlFileInput,
    ImportStatus,
    import_html_file,
)
from reinaluxe_recovery.persistence import (
    DatabaseConfigurationError,
    DatabaseLifecycleError,
    DatabaseLifecycleResult,
    PersistenceError,
    create_database_engine,
    create_session_factory,
    initialize_database,
)
from reinaluxe_recovery.research.errors import ResearchError
from reinaluxe_recovery.research.workflow import (
    research_analyze as run_research_analyze,
)
from reinaluxe_recovery.research.workflow import (
    research_build_snapshot as run_research_build_snapshot,
)
from reinaluxe_recovery.research.workflow import (
    research_discover as run_research_discover,
)
from reinaluxe_recovery.research.workflow import (
    research_export_review as run_research_export_review,
)
from reinaluxe_recovery.research.workflow import (
    research_image_review as run_research_image_review,
)
from reinaluxe_recovery.research.workflow import (
    research_plan as run_research_plan,
)
from reinaluxe_recovery.research.workflow import (
    research_refresh as run_research_refresh,
)

app = typer.Typer(
    name="reinaluxe-recovery",
    help="ReinaLuxe Recovery OS command-line interface.",
    no_args_is_help=True,
    add_completion=False,
)
console = Console()
error_console = Console(stderr=True)

EXIT_CONTENT_FAILURE = 1
EXIT_INPUT_ERROR = 2
EXIT_DATABASE_ERROR = 3
EXIT_PERSISTENCE_ERROR = 4
EXIT_QUERY_ERROR = 5
EXIT_COMMUNITY_ERROR = 6
EXIT_CONTENT_OPS_ERROR = 7
EXIT_RESEARCH_ERROR = 8


@app.command()
def version() -> None:
    """Display the package version."""
    console.print(__version__)


@app.command("db-init")
def db_init(
    database: Annotated[
        Path | None,
        typer.Option("--database", help="Local SQLite database path."),
    ] = None,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Print stable JSON output."),
    ] = False,
) -> None:
    """Initialize or safely upgrade the local database."""
    try:
        result = initialize_database(database)
    except (DatabaseConfigurationError, DatabaseLifecycleError) as error:
        error_console.print(f"Database initialization error: {error}", style="red")
        raise typer.Exit(code=EXIT_DATABASE_ERROR) from error

    if json_output:
        _print_json(result.model_dump_json(indent=2))
        return
    console.print(f"Database: {result.database_path}")
    console.print(f"Database URL: {result.database_url}")
    console.print(f"Previous revision: {result.previous_revision or 'none'}")
    console.print(f"Current revision: {result.current_revision}")
    console.print(
        "Migration: " + ("applied" if result.migration_performed else "already current")
    )
    console.print(f"Health: {'healthy' if result.healthy else 'unhealthy'}")


@app.command("import-html")
def import_html(
    html_path: Annotated[
        Path,
        typer.Argument(
            exists=True,
            file_okay=True,
            dir_okay=False,
            readable=True,
            help="Local UTF-8 HTML file to import.",
        ),
    ],
    source_url: Annotated[
        str,
        typer.Option("--source-url", help="Original HTTP(S) source URL."),
    ],
    fetched_at: Annotated[
        str,
        typer.Option(
            "--fetched-at",
            help="Timezone-aware ISO 8601 timestamp for the local observation.",
        ),
    ],
    output: Annotated[
        Path | None,
        typer.Option(
            "--output",
            "--json-output",
            help="Optional local path for result JSON.",
        ),
    ] = None,
    database: Annotated[
        Path | None,
        typer.Option("--database", help="Persist to this local SQLite database."),
    ] = None,
    persist_failed: Annotated[
        bool,
        typer.Option(
            "--persist-failed/--no-persist-failed",
            help="Store controlled failed-import diagnostics when using a database.",
        ),
    ] = True,
) -> None:
    """Import owner-provided HTML deterministically without network access."""
    try:
        import_input = HtmlFileInput.model_validate(
            {
                "html_path": html_path,
                "source_url": source_url,
                "fetched_at": fetched_at,
            }
        )
    except (OSError, ValidationError) as error:
        error_console.print(f"Offline import input error: {error}", style="red")
        raise typer.Exit(code=EXIT_INPUT_ERROR) from error

    if database is None:
        _run_json_only_import(import_input, output)
        return

    try:
        lifecycle = initialize_database(database)
    except (DatabaseConfigurationError, DatabaseLifecycleError) as error:
        error_console.print(f"Database initialization error: {error}", style="red")
        raise typer.Exit(code=EXIT_DATABASE_ERROR) from error

    engine = create_database_engine(lifecycle.database_url)
    try:
        workflow = OfflineImportWorkflow(create_session_factory(engine))
        workflow_result = workflow.run(
            import_input,
            persist_failed=persist_failed,
        )
    except PersistenceError as error:
        error_console.print(f"Import persistence error: {error}", style="red")
        raise typer.Exit(code=EXIT_PERSISTENCE_ERROR) from error
    finally:
        engine.dispose()

    rendered = workflow_result.model_dump_json(indent=2)
    try:
        if output is None:
            _print_json(rendered)
        else:
            output.write_text(f"{rendered}\n", encoding="utf-8")
            console.print(f"Wrote offline import and persistence results to {output}")
    except OSError as error:
        error_console.print(f"Offline import output error: {error}", style="red")
        raise typer.Exit(code=EXIT_INPUT_ERROR) from error

    if workflow_result.import_result.status is ImportStatus.FAILED:
        raise typer.Exit(code=EXIT_CONTENT_FAILURE)


def _run_json_only_import(import_input: HtmlFileInput, output: Path | None) -> None:
    """Preserve the original no-database ImportResult-only command behavior."""
    try:
        result = import_html_file(import_input)
        rendered = result.model_dump_json(indent=2)
        if output is None:
            console.print(rendered, markup=False)
        else:
            output.write_text(f"{rendered}\n", encoding="utf-8")
            console.print(f"Wrote offline import result to {output}")
    except OSError as error:
        error_console.print(f"Offline import input error: {error}", style="red")
        raise typer.Exit(code=EXIT_INPUT_ERROR) from error

    if result.status is ImportStatus.FAILED:
        raise typer.Exit(code=EXIT_CONTENT_FAILURE)


@app.command("import-batch")
def import_batch(
    manifest_path: Annotated[
        Path,
        typer.Argument(
            exists=True,
            file_okay=True,
            dir_okay=False,
            readable=True,
            help="Local UTF-8 JSON batch manifest.",
        ),
    ],
    database: Annotated[
        Path | None,
        typer.Option("--database", help="Persist to this local SQLite database."),
    ] = None,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Validate and parse without database writes."),
    ] = False,
    continue_on_error: Annotated[
        bool,
        typer.Option(
            "--continue-on-error/--fail-fast",
            help="Continue after entry failures or stop before later entries.",
        ),
    ] = True,
    persist_failed: Annotated[
        bool,
        typer.Option(
            "--persist-failed/--no-persist-failed",
            help="Store controlled failed-import diagnostics when persisting.",
        ),
    ] = True,
    entry_ids: Annotated[
        list[str] | None,
        typer.Option(
            "--entry-id",
            help="Select one entry ID; repeat to select multiple entries.",
        ),
    ] = None,
    limit: Annotated[
        int | None,
        typer.Option("--limit", min=1, help="Maximum selected enabled entries."),
    ] = None,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Print stable JSON output."),
    ] = False,
    output: Annotated[
        Path | None,
        typer.Option("--output", help="Write UTF-8 result JSON to a new local file."),
    ] = None,
) -> None:
    """Import an ordered local JSON manifest without network access."""
    if output is not None and output.exists():
        error_console.print(
            f"Batch output error: refusing to overwrite existing file: {output}",
            style="red",
        )
        raise typer.Exit(code=EXIT_INPUT_ERROR)

    try:
        options = BatchImportOptions(
            continue_on_error=continue_on_error,
            persist_failed=persist_failed,
            dry_run=dry_run or database is None,
            limit=limit,
            entry_ids=entry_ids,
        )
        result = BatchImportWorkflow().run(
            manifest_path,
            options=options,
            database_path=database,
        )
    except ValidationError as error:
        error_console.print(f"Batch option error: {error}", style="red")
        raise typer.Exit(code=EXIT_INPUT_ERROR) from error
    except (BatchManifestError, BatchPathError) as error:
        error_console.print(f"Batch manifest error: {error}", style="red")
        raise typer.Exit(code=EXIT_INPUT_ERROR) from error
    except BatchSelectionError as error:
        error_console.print(f"Batch selection error: {error}", style="red")
        raise typer.Exit(code=EXIT_QUERY_ERROR) from error
    except (DatabaseConfigurationError, DatabaseLifecycleError) as error:
        error_console.print(f"Database initialization error: {error}", style="red")
        raise typer.Exit(code=EXIT_DATABASE_ERROR) from error

    rendered = result.model_dump_json(indent=2)
    if output is not None:
        try:
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(f"{rendered}\n", encoding="utf-8")
        except OSError as error:
            error_console.print(f"Batch output error: {error}", style="red")
            raise typer.Exit(code=EXIT_INPUT_ERROR) from error

    if json_output:
        _print_json(rendered)
    else:
        _print_batch_result(result, output)

    if any(
        item.failure_kind is BatchFailureKind.PERSISTENCE for item in result.results
    ):
        error_console.print(
            "Batch completed with a persistence-system failure.", style="red"
        )
        raise typer.Exit(code=EXIT_PERSISTENCE_ERROR)
    if result.failed_entries:
        error_console.print(
            f"Batch completed with {result.failed_entries} failed entry or entries.",
            style="yellow",
        )
        raise typer.Exit(code=EXIT_CONTENT_FAILURE)


def _print_batch_result(result: BatchImportResult, output: Path | None) -> None:
    """Render one concise owner-facing batch summary and ordered entry table."""
    console.print(f"Batch: {result.batch_id}")
    console.print(f"Manifest: {result.manifest_path}")
    console.print(
        f"Database: {result.database_path if result.database_path else 'not persisted'}"
    )
    console.print(
        "Counts: "
        f"total={result.total_entries}, enabled={result.enabled_entries}, "
        f"attempted={result.attempted_entries}, "
        f"succeeded={result.succeeded_entries}, failed={result.failed_entries}, "
        f"skipped={result.skipped_entries}"
    )
    console.print(
        "Persistence: "
        f"pages created/reused={result.created_pages}/{result.reused_pages}, "
        f"crawls created/reused={result.created_crawls}/{result.reused_crawls}, "
        "Article versions created/reused="
        f"{result.created_article_versions}/{result.reused_article_versions}"
    )
    table = Table(title="Batch entries")
    table.add_column("Entry")
    table.add_column("Status")
    table.add_column("Page")
    table.add_column("Crawl")
    table.add_column("Article")
    table.add_column("Version", justify="right")
    table.add_column("Message")
    for item in result.results:
        table.add_row(
            item.entry_id,
            item.status.value,
            item.page_disposition.value if item.page_disposition else "-",
            item.crawl_disposition.value if item.crawl_disposition else "-",
            item.article_disposition.value if item.article_disposition else "-",
            str(item.article_version_number or "-"),
            item.error_message or "",
        )
    console.print(table)
    console.print(f"Overall status: {result.overall_status.value}")
    if output is not None:
        console.print(f"Wrote batch result JSON to {output}")


@app.command("list-pages")
def list_pages(
    database: Annotated[
        Path | None,
        typer.Option("--database", help="Local SQLite database path."),
    ] = None,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Print stable JSON output."),
    ] = False,
    limit: Annotated[
        int | None,
        typer.Option("--limit", min=1, help="Maximum pages to return."),
    ] = None,
    offset: Annotated[
        int,
        typer.Option("--offset", min=0, help="Number of pages to skip."),
    ] = 0,
) -> None:
    """List locally persisted pages in deterministic URL order."""
    lifecycle, engine = _open_current_database(database)
    del lifecycle
    try:
        result = PageQueryService(create_session_factory(engine)).list_pages(
            limit=limit,
            offset=offset,
        )
    except PersistenceError as error:
        error_console.print(f"Page query error: {error}", style="red")
        raise typer.Exit(code=EXIT_QUERY_ERROR) from error
    finally:
        engine.dispose()

    if json_output:
        _print_json(result.model_dump_json(indent=2))
        return
    table = Table(title="Local pages")
    table.add_column("Canonical URL")
    table.add_column("Version", justify="right")
    table.add_column("First seen")
    table.add_column("Last seen")
    table.add_column("Crawls", justify="right")
    table.add_column("Versions", justify="right")
    for page in result.items:
        table.add_row(
            page.canonical_url,
            str(page.current_version_number or "-"),
            page.first_seen_at.isoformat(),
            page.last_seen_at.isoformat(),
            str(page.crawl_count),
            str(page.article_version_count),
        )
    console.print(table)
    if not result.items:
        console.print("No pages have been imported yet.")


@app.command("show-page")
def show_page(
    url: Annotated[str, typer.Argument(help="Canonical or source page URL.")],
    database: Annotated[
        Path | None,
        typer.Option("--database", help="Local SQLite database path."),
    ] = None,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Print stable JSON output."),
    ] = False,
    include_history: Annotated[
        bool,
        typer.Option(
            "--include-history", help="Include crawl, version, and warning history."
        ),
    ] = False,
) -> None:
    """Show one locally persisted page and optional history."""
    lifecycle, engine = _open_current_database(database)
    del lifecycle
    try:
        details = PageQueryService(create_session_factory(engine)).show_page(
            url,
            include_history=include_history,
        )
    except PageNotFoundError as error:
        error_console.print(str(error), style="yellow")
        raise typer.Exit(code=EXIT_QUERY_ERROR) from error
    except PersistenceError as error:
        error_console.print(f"Page query error: {error}", style="red")
        raise typer.Exit(code=EXIT_QUERY_ERROR) from error
    finally:
        engine.dispose()

    if json_output:
        _print_json(details.model_dump_json(indent=2))
        return
    console.print(f"Page: {details.page.canonical_url}")
    console.print(f"Current version: {details.page.current_version_number or 'none'}")
    console.print(f"First seen: {details.page.first_seen_at.isoformat()}")
    console.print(f"Last seen: {details.page.last_seen_at.isoformat()}")
    console.print(f"Crawls: {details.page.crawl_count}")
    console.print(f"Article versions: {details.page.article_version_count}")
    if details.latest_article is not None:
        console.print(f"Title: {details.latest_article.article.title}")
    if include_history:
        console.print("History:")
        for crawl in details.crawl_history:
            console.print(
                f"- Crawl {crawl.id}: {crawl.fetched_at.isoformat()} "
                f"({crawl.import_status.value})"
            )
        for version_item in details.article_version_history:
            console.print(
                f"- Version {version_item.version_number}: {version_item.article.title}"
            )
        for group in details.warnings_by_crawl:
            for warning in group.warnings:
                console.print(
                    f"- Warning for crawl {group.crawl.id}: "
                    f"{warning.code} — {warning.message}"
                )


@app.command("audit-articles")
def audit_articles(
    database: Annotated[
        Path | None, typer.Option("--database", help="Local SQLite database path.")
    ] = None,
    all_versions: Annotated[
        bool,
        typer.Option(
            "--all-versions",
            help="Audit all stored versions instead of only current versions.",
        ),
    ] = False,
    page_urls: Annotated[
        list[str] | None,
        typer.Option(
            "--page-url", help="Select a page URL; repeat for multiple pages."
        ),
    ] = None,
    rules: Annotated[
        list[str] | None,
        typer.Option("--rule", help="Select a rule code; repeat for multiple rules."),
    ] = None,
    include_info: Annotated[
        bool,
        typer.Option(
            "--include-info/--exclude-info",
            help="Include or exclude informational findings.",
        ),
    ] = True,
    limit: Annotated[
        int | None,
        typer.Option("--limit", min=1, help="Maximum Article versions to audit."),
    ] = None,
    json_output: Annotated[
        bool, typer.Option("--json", help="Print stable JSON output.")
    ] = False,
    output: Annotated[
        Path | None,
        typer.Option("--output", help="Write UTF-8 result JSON to a new file."),
    ] = None,
    fail_on_errors: Annotated[
        bool,
        typer.Option(
            "--fail-on-errors", help="Exit 1 when error-severity findings exist."
        ),
    ] = False,
) -> None:
    """Audit persisted normalized Articles deterministically and offline."""
    if output is not None and output.exists():
        error_console.print(
            f"Audit output error: refusing to overwrite existing file: {output}",
            style="red",
        )
        raise typer.Exit(code=EXIT_INPUT_ERROR)
    try:
        selected_rules = (
            frozenset(AuditRuleCode(value) for value in rules) if rules else None
        )
        options = AuditOptions(
            include_info=include_info,
            rule_codes=selected_rules,
            latest_only=not all_versions,
            page_urls=tuple(page_urls) if page_urls else None,
            limit=limit,
            fail_on_error_severity=fail_on_errors,
        )
    except (ValueError, ValidationError) as error:
        error_console.print(f"Audit option error: {error}", style="red")
        raise typer.Exit(code=EXIT_INPUT_ERROR) from error
    _, engine = _open_current_database(database)
    try:
        result = ArticleAuditWorkflow(create_session_factory(engine)).run(options)
    except NoMatchingArticlesError as error:
        error_console.print(str(error), style="yellow")
        raise typer.Exit(code=EXIT_QUERY_ERROR) from error
    except (PersistenceError, ValidationError) as error:
        error_console.print(f"Audit system error: {error}", style="red")
        raise typer.Exit(code=EXIT_PERSISTENCE_ERROR) from error
    finally:
        engine.dispose()
    rendered = result.model_dump_json(indent=2)
    if output is not None:
        try:
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(f"{rendered}\n", encoding="utf-8")
        except OSError as error:
            error_console.print(f"Audit output error: {error}", style="red")
            raise typer.Exit(code=EXIT_INPUT_ERROR) from error
    if json_output:
        _print_json(rendered)
    else:
        console.print(render_site_audit(result), markup=False)
        if output is not None:
            console.print(f"Wrote audit result JSON to {output}")
    if fail_on_errors and result.severity_counts.get(AuditSeverity.ERROR, 0):
        raise typer.Exit(code=EXIT_CONTENT_FAILURE)


@app.command("community-import")
def community_import(
    manifest: Annotated[
        Path,
        typer.Option("--manifest", exists=True, file_okay=True, dir_okay=False),
    ],
    output: Annotated[Path, typer.Option("--output", file_okay=False)],
) -> None:
    """Normalize owner-provided community records deterministically and offline."""
    try:
        summary = import_community_manifest(manifest, output)
    except CommunityWorkflowError as error:
        error_console.print(f"Community import error: {error}", style="red")
        raise typer.Exit(code=EXIT_COMMUNITY_ERROR) from error
    console.print(
        "Community import complete: "
        f"sources={summary['source_record_count']}, "
        f"claims={summary['candidate_claim_count']}, "
        f"evidence={summary['evidence_record_count']}"
    )
    console.print(f"Output: {output}")


@app.command("community-export-review")
def community_export_review(
    input_directory: Annotated[
        Path,
        typer.Option("--input", exists=True, file_okay=False, dir_okay=True),
    ],
    output: Annotated[Path, typer.Option("--output", file_okay=False)],
) -> None:
    """Export an owner review queue without pre-approving any claim."""
    try:
        summary = export_community_review(input_directory, output)
    except CommunityWorkflowError as error:
        error_console.print(f"Community review export error: {error}", style="red")
        raise typer.Exit(code=EXIT_COMMUNITY_ERROR) from error
    console.print(f"Review queue created for {summary['claim_count']} claims.")
    console.print(f"Output: {output}")


@app.command("community-apply-decisions")
def community_apply_decisions(
    review: Annotated[
        Path,
        typer.Option("--review", exists=True, file_okay=True, dir_okay=False),
    ],
    input_directory: Annotated[
        Path,
        typer.Option("--input", exists=True, file_okay=False, dir_okay=True),
    ],
    output: Annotated[Path, typer.Option("--output", file_okay=False)],
) -> None:
    """Apply explicit owner decisions and retain pending/rejected audit records."""
    try:
        summary = apply_community_decisions(review, input_directory, output)
    except CommunityWorkflowError as error:
        error_console.print(f"Community decision error: {error}", style="red")
        raise typer.Exit(code=EXIT_COMMUNITY_ERROR) from error
    console.print(
        f"Decisions applied: {summary['decision_count']}; "
        f"pending: {summary['pending_count']}"
    )
    console.print(f"Output: {output}")


@app.command("community-build-kb")
def community_build_kb(
    input_directory: Annotated[
        Path,
        typer.Option("--input", exists=True, file_okay=False, dir_okay=True),
    ],
    output: Annotated[Path, typer.Option("--output", file_okay=False)],
) -> None:
    """Build a scoped knowledge base from approved human decisions only."""
    try:
        summary = build_community_knowledge_base(input_directory, output)
    except CommunityWorkflowError as error:
        error_console.print(f"Community knowledge error: {error}", style="red")
        raise typer.Exit(code=EXIT_COMMUNITY_ERROR) from error
    console.print(
        f"Knowledge base created with {summary['approved_knowledge_count']} entries."
    )
    console.print(f"Output: {output}")


@app.command("community-build-snapshot")
def community_build_snapshot(
    inputs: Annotated[
        list[Path],
        typer.Option("--inputs", exists=True, file_okay=False, dir_okay=True),
    ],
    output: Annotated[Path, typer.Option("--output", file_okay=False)],
) -> None:
    """Build an immutable approved-knowledge snapshot from local KB batches."""
    try:
        manifest = build_knowledge_snapshot(inputs, output)
    except (ContentOpsError, ValidationError, OSError) as error:
        error_console.print(f"Knowledge snapshot error: {error}", style="red")
        raise typer.Exit(code=EXIT_CONTENT_OPS_ERROR) from error
    console.print(
        f"Knowledge snapshot {manifest.snapshot_id}: entries={manifest.entry_count}, "
        f"internal={manifest.internal_only_count}"
    )
    console.print(f"Output: {output}")


@app.command("content-build-page-context")
def content_build_page_context(
    role_matrix: Annotated[
        Path, typer.Option("--role-matrix", exists=True, file_okay=True, dir_okay=False)
    ],
    finding_register: Annotated[
        Path,
        typer.Option("--finding-register", exists=True, file_okay=True, dir_okay=False),
    ],
    roadmap: Annotated[
        Path, typer.Option("--roadmap", exists=True, file_okay=True, dir_okay=False)
    ],
    output: Annotated[Path, typer.Option("--output", file_okay=False)],
    database: Annotated[
        Path,
        typer.Option("--database", exists=True, file_okay=True, dir_okay=False),
    ] = Path("data/reinaluxe-recovery.db"),
    readiness: Annotated[
        Path | None,
        typer.Option("--readiness", exists=True, file_okay=True, dir_okay=False),
    ] = None,
) -> None:
    """Snapshot the authoritative 25-page plan and current read-only page state."""
    try:
        manifest = build_page_context(
            role_matrix,
            finding_register,
            roadmap,
            output,
            database,
            readiness,
        )
    except (ContentOpsError, ValidationError, OSError) as error:
        error_console.print(f"Page context error: {error}", style="red")
        raise typer.Exit(code=EXIT_CONTENT_OPS_ERROR) from error
    console.print(
        f"Page context {manifest['page_context_snapshot_id']}: "
        f"pages={manifest['page_count']}"
    )
    console.print(f"Output: {output}")


@app.command("community-map-opportunities")
def community_map_opportunities(
    knowledge_snapshot: Annotated[
        Path,
        typer.Option(
            "--knowledge-snapshot", exists=True, file_okay=False, dir_okay=True
        ),
    ],
    page_context: Annotated[
        Path,
        typer.Option("--page-context", exists=True, file_okay=False, dir_okay=True),
    ],
    output: Annotated[Path, typer.Option("--output", file_okay=False)],
) -> None:
    """Map knowledge to reviewable opportunities with transparent local rules."""
    try:
        summary = map_content_opportunities(knowledge_snapshot, page_context, output)
    except (ContentOpsError, ValidationError, OSError) as error:
        error_console.print(f"Opportunity mapping error: {error}", style="red")
        raise typer.Exit(code=EXIT_CONTENT_OPS_ERROR) from error
    console.print(f"Mapped {summary['opportunity_count']} pending opportunities.")
    console.print(f"Output: {output}")


@app.command("community-export-opportunity-review")
def community_export_opportunity_review(
    input_directory: Annotated[
        Path, typer.Option("--input", exists=True, file_okay=False, dir_okay=True)
    ],
    output: Annotated[Path, typer.Option("--output", file_okay=False)],
) -> None:
    """Export a blank owner review queue for mapped opportunities."""
    try:
        summary = export_opportunity_review(input_directory, output)
    except (ContentOpsError, ValidationError, OSError) as error:
        error_console.print(f"Opportunity review export error: {error}", style="red")
        raise typer.Exit(code=EXIT_CONTENT_OPS_ERROR) from error
    console.print(
        f"Review queue created for {summary['opportunity_count']} opportunities."
    )
    console.print(f"Output: {output}")


@app.command("community-apply-opportunity-decisions")
def community_apply_opportunity_decisions(
    review: Annotated[
        Path, typer.Option("--review", exists=True, file_okay=True, dir_okay=False)
    ],
    input_directory: Annotated[
        Path, typer.Option("--input", exists=True, file_okay=False, dir_okay=True)
    ],
    output: Annotated[Path, typer.Option("--output", file_okay=False)],
) -> None:
    """Validate owner opportunity decisions without changing content."""
    try:
        summary = apply_opportunity_decisions(review, input_directory, output)
    except (ContentOpsError, ValidationError, OSError) as error:
        error_console.print(f"Opportunity decision error: {error}", style="red")
        raise typer.Exit(code=EXIT_CONTENT_OPS_ERROR) from error
    console.print(
        f"Opportunity decisions={summary['decision_count']}; "
        f"pending={summary['pending_count']}"
    )
    console.print(f"Output: {output}")


@app.command("content-build-change-manifest")
def content_build_change_manifest(
    decisions: Annotated[
        Path, typer.Option("--decisions", exists=True, file_okay=False, dir_okay=True)
    ],
    knowledge_snapshot: Annotated[
        Path,
        typer.Option(
            "--knowledge-snapshot", exists=True, file_okay=False, dir_okay=True
        ),
    ],
    page_context: Annotated[
        Path,
        typer.Option("--page-context", exists=True, file_okay=False, dir_okay=True),
    ],
    output: Annotated[Path, typer.Option("--output", file_okay=False)],
    database: Annotated[
        Path,
        typer.Option("--database", exists=True, file_okay=True, dir_okay=False),
    ] = Path("data/reinaluxe-recovery.db"),
) -> None:
    """Build the hash-locked owner-approved future drafting manifest."""
    try:
        manifest = build_content_change_manifest(
            decisions, knowledge_snapshot, page_context, output, database
        )
    except (ContentOpsError, ValidationError, OSError) as error:
        error_console.print(f"Change manifest error: {error}", style="red")
        raise typer.Exit(code=EXIT_CONTENT_OPS_ERROR) from error
    console.print(
        f"Change manifest {manifest.change_manifest_id}: "
        f"opportunities={len(manifest.approved_opportunity_ids)}"
    )
    console.print(f"Output: {output}")


@app.command("research-plan")
def research_plan_command(
    request: Annotated[
        Path,
        typer.Option("--request", exists=True, file_okay=True, dir_okay=False),
    ],
    output: Annotated[Path, typer.Option("--output", file_okay=False)],
) -> None:
    """Understand an article/topic and create a bounded multi-source plan."""
    try:
        run_research_plan(request, output)
    except (ResearchError, ValidationError, OSError) as error:
        error_console.print(f"Research planning error: {error}", style="red")
        raise typer.Exit(code=EXIT_RESEARCH_ERROR) from error
    console.print(f"Research plan: {output}")


@app.command("research-discover")
def research_discover_command(
    plan: Annotated[
        Path, typer.Option("--plan", exists=True, file_okay=True, dir_okay=True)
    ],
    output: Annotated[Path, typer.Option("--output", file_okay=False)],
) -> None:
    """Search configured public-source lanes with the plan-selected provider."""
    try:
        run_research_discover(plan, output)
    except (ResearchError, ValidationError, OSError) as error:
        error_console.print(f"Research discovery error: {error}", style="red")
        raise typer.Exit(code=EXIT_RESEARCH_ERROR) from error
    console.print(f"Research run: {output}")


@app.command("research-analyze")
def research_analyze_command(
    run: Annotated[
        Path, typer.Option("--run", exists=True, file_okay=True, dir_okay=True)
    ],
    output: Annotated[Path, typer.Option("--output", file_okay=False)],
    glm_assisted: Annotated[
        bool,
        typer.Option(
            "--glm-assisted/--deterministic-analysis",
            help="Use configured GLM analysis after deterministic screening.",
        ),
    ] = False,
) -> None:
    """Extract atomic claims, evidence links, disagreement and opportunities."""
    try:
        run_research_analyze(run, output, glm_assisted=glm_assisted)
    except (ResearchError, ValidationError, OSError) as error:
        error_console.print(f"Research analysis error: {error}", style="red")
        raise typer.Exit(code=EXIT_RESEARCH_ERROR) from error
    console.print(f"Research analysis: {output}")


@app.command("research-build-snapshot")
def research_build_snapshot_command(
    analysis: Annotated[
        Path,
        typer.Option("--analysis", exists=True, file_okay=True, dir_okay=True),
    ],
    output: Annotated[Path, typer.Option("--output", file_okay=False)],
    research_database: Annotated[
        Path,
        typer.Option(
            "--research-database", help="Separate runtime research SQLite path."
        ),
    ] = Path("data/research/runtime/research.sqlite"),
) -> None:
    """Persist a versioned snapshot in the separate research database."""
    try:
        snapshot = run_research_build_snapshot(
            analysis, output, database_path=research_database
        )
    except (ResearchError, ValidationError, OSError) as error:
        error_console.print(f"Research snapshot error: {error}", style="red")
        raise typer.Exit(code=EXIT_RESEARCH_ERROR) from error
    console.print(f"Research snapshot {snapshot.snapshot_id}: {output}")


@app.command("research-export-review")
def research_export_review_command(
    analysis: Annotated[
        Path,
        typer.Option("--analysis", exists=True, file_okay=True, dir_okay=True),
    ],
    output: Annotated[Path, typer.Option("--output", file_okay=False)],
    research_database: Annotated[
        Path,
        typer.Option(
            "--research-database", help="Separate runtime research SQLite path."
        ),
    ] = Path("data/research/runtime/research.sqlite"),
) -> None:
    """Export the compact, blank-decision owner review package."""
    try:
        run_research_export_review(analysis, output, database_path=research_database)
    except (ResearchError, ValidationError, OSError) as error:
        error_console.print(f"Research review export error: {error}", style="red")
        raise typer.Exit(code=EXIT_RESEARCH_ERROR) from error
    console.print(f"Research review package: {output}")


@app.command("research-refresh")
def research_refresh_command(
    request: Annotated[
        Path,
        typer.Option("--request", exists=True, file_okay=True, dir_okay=False),
    ],
    output: Annotated[Path, typer.Option("--output", file_okay=False)],
    glm_assisted: Annotated[
        bool,
        typer.Option("--glm-assisted/--deterministic-analysis"),
    ] = False,
    research_database: Annotated[Path, typer.Option("--research-database")] = Path(
        "data/research/runtime/research.sqlite"
    ),
) -> None:
    """Run a bounded topic/article refresh and retain each stage artifact."""
    try:
        run_research_refresh(
            request,
            output,
            glm_assisted=glm_assisted,
            database_path=research_database,
        )
    except (ResearchError, ValidationError, OSError) as error:
        error_console.print(f"Research refresh error: {error}", style="red")
        raise typer.Exit(code=EXIT_RESEARCH_ERROR) from error
    console.print(f"Research refresh package: {output}")


@app.command("research-image-review")
def research_image_review_command(
    analysis: Annotated[
        Path,
        typer.Option("--analysis", exists=True, file_okay=True, dir_okay=True),
    ],
    output: Annotated[Path, typer.Option("--output", file_okay=False)],
) -> None:
    """Export source-linked image metadata for permission and owner review."""
    try:
        run_research_image_review(analysis, output)
    except (ResearchError, ValidationError, OSError) as error:
        error_console.print(f"Research image review error: {error}", style="red")
        raise typer.Exit(code=EXIT_RESEARCH_ERROR) from error
    console.print(f"Research image review: {output}")


@app.command("acquire-site")
def acquire_site(
    sitemaps: Annotated[
        list[str] | None,
        typer.Option("--sitemap", help="Sitemap URL; repeat for multiple sitemaps."),
    ] = None,
    url_list: Annotated[
        Path | None, typer.Option("--url-list", help="Local JSON or newline URL list.")
    ] = None,
    allowed_hosts: Annotated[
        list[str] | None,
        typer.Option("--allowed-host", help="Allowed public host; repeat as needed."),
    ] = None,
    output_directory: Annotated[
        Path,
        typer.Option(
            "--output-directory", help="Root directory for acquisition output."
        ),
    ] = Path("acquisitions"),
    acquisition_id: Annotated[
        str,
        typer.Option("--acquisition-id", help="Stable local acquisition identifier."),
    ] = "site-acquisition",
    user_agent: Annotated[
        str,
        typer.Option("--user-agent", help="Owner-controlled acquisition User-Agent."),
    ] = "ReinaLuxeRecovery/0.1 (+read-only acquisition)",
    timeout: Annotated[
        float, typer.Option("--timeout", min=0.01, help="Request timeout in seconds.")
    ] = 20.0,
    delay: Annotated[
        float,
        typer.Option(
            "--delay", min=0.0, help="Delay between page requests in seconds."
        ),
    ] = 1.0,
    maximum_urls: Annotated[
        int | None,
        typer.Option("--maximum-urls", min=1, help="Maximum eligible page URLs."),
    ] = None,
    include_patterns: Annotated[
        list[str] | None,
        typer.Option("--include-pattern", help="Include URL glob; repeat as needed."),
    ] = None,
    exclude_patterns: Annotated[
        list[str] | None,
        typer.Option("--exclude-pattern", help="Exclude URL glob; repeat as needed."),
    ] = None,
    overwrite_existing: Annotated[
        bool,
        typer.Option(
            "--overwrite-existing",
            help="Allow replacement of acquisition report files.",
        ),
    ] = False,
    json_output: Annotated[
        bool, typer.Option("--json", help="Print stable JSON output.")
    ] = False,
    result_output: Annotated[
        Path | None,
        typer.Option(
            "--result-output",
            help="Write an additional result JSON file without overwriting.",
        ),
    ] = None,
) -> None:
    """Acquire approved public HTML snapshots without modifying the website."""
    if bool(sitemaps) == bool(url_list):
        error_console.print(
            "Acquisition input error: provide exactly one of --sitemap or --url-list",
            style="red",
        )
        raise typer.Exit(code=EXIT_INPUT_ERROR)
    if not allowed_hosts:
        error_console.print(
            "Acquisition input error: at least one --allowed-host is required",
            style="red",
        )
        raise typer.Exit(code=EXIT_INPUT_ERROR)
    if result_output is not None and result_output.exists():
        error_console.print(
            f"Acquisition output error: refusing to overwrite {result_output}",
            style="red",
        )
        raise typer.Exit(code=EXIT_INPUT_ERROR)
    explicit: list[str] | None = None
    if url_list is not None:
        try:
            explicit = load_url_list(url_list)
        except DiscoveryError as error:
            error_console.print(f"Acquisition URL-list error: {error}", style="red")
            raise typer.Exit(code=EXIT_INPUT_ERROR) from error
    try:
        request = AcquisitionRequest(
            created_at=datetime.now(UTC),
            acquisition_id=acquisition_id,
            source_type=AcquisitionSourceType.SITEMAP
            if sitemaps
            else AcquisitionSourceType.URL_LIST,
            sitemap_urls=tuple(sitemaps) if sitemaps else None,  # type: ignore[arg-type]
            explicit_urls=tuple(explicit) if explicit else None,  # type: ignore[arg-type]
            allowed_hosts=frozenset(allowed_hosts),
            output_directory=output_directory / acquisition_id,
            user_agent=user_agent,
            request_timeout_seconds=timeout,
            delay_between_requests_seconds=delay,
            maximum_urls=maximum_urls,
            include_patterns=tuple(include_patterns) if include_patterns else None,
            exclude_patterns=tuple(exclude_patterns) if exclude_patterns else None,
            overwrite_existing=overwrite_existing,
        )
        result = AcquisitionWorkflow().run(request)
    except NoEligibleUrlsError as error:
        error_console.print(f"Acquisition selection error: {error}", style="yellow")
        raise typer.Exit(code=EXIT_QUERY_ERROR) from error
    except (ValidationError, OSError) as error:
        error_console.print(f"Acquisition input error: {error}", style="red")
        raise typer.Exit(code=EXIT_INPUT_ERROR) from error
    except DiscoveryError as error:
        error_console.print(f"Acquisition discovery error: {error}", style="red")
        raise typer.Exit(code=EXIT_DATABASE_ERROR) from error
    except (UnsafeTargetError, AcquisitionError) as error:
        error_console.print(f"Acquisition system error: {error}", style="red")
        raise typer.Exit(code=EXIT_PERSISTENCE_ERROR) from error
    rendered = result.model_dump_json(indent=2)
    if result_output is not None:
        try:
            result_output.parent.mkdir(parents=True, exist_ok=True)
            result_output.write_text(f"{rendered}\n", encoding="utf-8")
        except OSError as error:
            error_console.print(f"Acquisition output error: {error}", style="red")
            raise typer.Exit(code=EXIT_INPUT_ERROR) from error
    _print_json(rendered) if json_output else console.print(
        render_acquisition(result), markup=False
    )
    if result.failed_count:
        raise typer.Exit(code=EXIT_CONTENT_FAILURE)


def _open_current_database(
    database: Path | None,
) -> tuple[DatabaseLifecycleResult, Engine]:
    """Safely initialize/upgrade and open a database for a CLI command."""
    try:
        lifecycle = initialize_database(database)
        return lifecycle, create_database_engine(lifecycle.database_url)
    except (DatabaseConfigurationError, DatabaseLifecycleError) as error:
        error_console.print(f"Database initialization error: {error}", style="red")
        raise typer.Exit(code=EXIT_DATABASE_ERROR) from error


def _print_json(rendered: str) -> None:
    """Print prevalidated JSON without Rich inserting line-wrap characters."""
    console.print(rendered, markup=False, soft_wrap=True)


def main() -> None:
    """Run the command-line application."""
    app()


if __name__ == "__main__":
    main()
