"""Command-line entry point for ReinaLuxe Recovery OS."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from pydantic import ValidationError
from rich.console import Console
from rich.table import Table
from sqlalchemy import Engine

from reinaluxe_recovery import __version__
from reinaluxe_recovery.application import (
    OfflineImportWorkflow,
    PageNotFoundError,
    PageQueryService,
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
