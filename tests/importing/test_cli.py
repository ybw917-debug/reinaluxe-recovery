"""Tests for the thin offline HTML import command."""

import json
from pathlib import Path

from typer.testing import CliRunner

from reinaluxe_recovery.cli import app

FIXTURES = Path(__file__).parent / "fixtures"
runner = CliRunner()


def test_cli_success_writes_validated_result(tmp_path: Path) -> None:
    """The command writes a successful ImportResult JSON file."""
    output = tmp_path / "result.json"
    result = runner.invoke(
        app,
        [
            "import-html",
            str(FIXTURES / "minimal-article.html"),
            "--source-url",
            "https://owner.example/minimal/",
            "--fetched-at",
            "2026-07-14T12:00:00+08:00",
            "--output",
            str(output),
        ],
    )

    assert result.exit_code == 0
    assert json.loads(output.read_text(encoding="utf-8"))["status"] == "succeeded"


def test_cli_fatal_import_returns_nonzero(tmp_path: Path) -> None:
    """A controlled fatal import writes diagnostics and exits with code one."""
    output = tmp_path / "fatal.json"
    result = runner.invoke(
        app,
        [
            "import-html",
            str(FIXTURES / "no-article-body.html"),
            "--source-url",
            "https://owner.example/empty/",
            "--fetched-at",
            "2026-07-14T12:00:00+08:00",
            "--output",
            str(output),
        ],
    )

    assert result.exit_code == 1
    assert json.loads(output.read_text(encoding="utf-8"))["status"] == "failed"
