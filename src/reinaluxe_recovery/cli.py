"""Command-line entry point for ReinaLuxe Recovery OS."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from pydantic import ValidationError
from rich.console import Console

from reinaluxe_recovery import __version__
from reinaluxe_recovery.importing import (
    HtmlFileInput,
    ImportStatus,
    import_html_file,
)

app = typer.Typer(
    name="reinaluxe-recovery",
    help="ReinaLuxe Recovery OS command-line interface.",
    no_args_is_help=True,
    add_completion=False,
)
console = Console()
error_console = Console(stderr=True)


@app.command()
def version() -> None:
    """Display the package version."""
    console.print(__version__)


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
        typer.Option("--output", help="Optional local path for result JSON."),
    ] = None,
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
        result = import_html_file(import_input)
        rendered = result.model_dump_json(indent=2)
        if output is None:
            console.print(rendered, markup=False)
        else:
            output.write_text(f"{rendered}\n", encoding="utf-8")
            console.print(f"Wrote offline import result to {output}")
    except (OSError, ValidationError) as error:
        error_console.print(f"Offline import input error: {error}", style="red")
        raise typer.Exit(code=2) from error

    if result.status is ImportStatus.FAILED:
        raise typer.Exit(code=1)


def main() -> None:
    """Run the command-line application."""
    app()


if __name__ == "__main__":
    main()
