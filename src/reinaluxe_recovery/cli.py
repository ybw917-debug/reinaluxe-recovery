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
