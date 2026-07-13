"""Command-line entry point for ReinaLuxe Recovery OS."""

from __future__ import annotations

import typer
from rich.console import Console

from reinaluxe_recovery import __version__

app = typer.Typer(
    name="reinaluxe-recovery",
    help="ReinaLuxe Recovery OS command-line interface.",
    no_args_is_help=True,
    add_completion=False,
)
console = Console()


@app.command()
def version() -> None:
    """Display the package version."""
    console.print(__version__)


def main() -> None:
    """Run the command-line application."""
    app()


if __name__ == "__main__":
    main()
