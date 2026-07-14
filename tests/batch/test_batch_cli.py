"""CLI tests for the owner-facing offline batch command."""

import json
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from reinaluxe_recovery.cli import app
from reinaluxe_recovery.persistence import (
    DatabaseLifecycleError,
    PersistenceWriteError,
)

FIXTURES = Path(__file__).parent / "fixtures" / "html"
runner = CliRunner()


def _copy(tmp_path: Path, target: str, fixture: str = "article-a.html") -> None:
    path = tmp_path / target
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        (FIXTURES / fixture).read_text(encoding="utf-8"),
        encoding="utf-8",
    )


def _entry(
    entry_id: str,
    path: str,
    *,
    enabled: bool = True,
) -> dict[str, Any]:
    return {
        "entry_id": entry_id,
        "html_path": path,
        "source_url": f"https://owner.example/{entry_id}/",
        "enabled": enabled,
    }


def _manifest(tmp_path: Path, entries: list[dict[str, Any]]) -> Path:
    path = tmp_path / "manifest.json"
    path.write_text(
        json.dumps(
            {
                "contract_version": "1.0",
                "batch_id": "cli-batch",
                "created_at": "2026-07-14T10:00:00+00:00",
                "default_fetched_at": "2026-07-14T09:00:00+00:00",
                "entries": entries,
            }
        ),
        encoding="utf-8",
    )
    return path


def test_import_batch_help() -> None:
    result = runner.invoke(
        app,
        ["import-batch", "--help"],
        terminal_width=180,
    )
    assert result.exit_code == 0
    assert "Usage:" in result.stdout
    assert "--database" in result.stdout
    assert "without network access" in result.stdout


def test_human_and_json_dry_run_are_successful_and_do_not_create_database(
    tmp_path: Path,
) -> None:
    _copy(tmp_path, "one.html")
    manifest = _manifest(tmp_path, [_entry("one", "one.html")])

    human = runner.invoke(app, ["import-batch", str(manifest)])
    structured = runner.invoke(app, ["import-batch", str(manifest), "--json"])

    assert human.exit_code == 0
    assert "Database: not persisted" in human.stdout
    assert "Overall status: succeeded" in human.stdout
    payload = json.loads(structured.stdout)
    assert structured.exit_code == 0
    assert payload["database_path"] is None
    assert payload["succeeded_entries"] == 1
    assert not (tmp_path / "data" / "reinaluxe-recovery.db").exists()


def test_persisted_batch_and_repeat_report_created_then_reused(tmp_path: Path) -> None:
    _copy(tmp_path, "one.html")
    manifest = _manifest(tmp_path, [_entry("one", "one.html")])
    database = tmp_path / "batch.db"
    args = [
        "import-batch",
        str(manifest),
        "--database",
        str(database),
        "--json",
    ]

    first = runner.invoke(app, args)
    repeated = runner.invoke(app, args)

    assert first.exit_code == 0
    assert repeated.exit_code == 0
    assert json.loads(first.stdout)["created_pages"] == 1
    payload = json.loads(repeated.stdout)
    assert payload["reused_pages"] == 1
    assert payload["reused_crawls"] == 1
    assert payload["reused_article_versions"] == 1


def test_mixed_failure_and_fail_fast_exit_one_with_stable_results(
    tmp_path: Path,
) -> None:
    _copy(tmp_path, "one.html")
    _copy(tmp_path, "three.html", "article-a-changed.html")
    manifest = _manifest(
        tmp_path,
        [
            _entry("one", "one.html"),
            _entry("missing", "missing.html"),
            _entry("three", "three.html"),
        ],
    )

    continued = runner.invoke(app, ["import-batch", str(manifest), "--json"])
    stopped = runner.invoke(
        app,
        ["import-batch", str(manifest), "--fail-fast", "--json"],
    )

    assert continued.exit_code == 1
    assert [item["status"] for item in json.loads(continued.stdout)["results"]] == [
        "succeeded",
        "failed",
        "succeeded",
    ]
    assert stopped.exit_code == 1
    assert [item["status"] for item in json.loads(stopped.stdout)["results"]] == [
        "succeeded",
        "failed",
        "not_attempted",
    ]


@pytest.mark.parametrize(
    ("entry", "expected_exit"),
    [
        (_entry("missing", "missing.html"), 1),
        (_entry("escape", "../outside.html"), 2),
    ],
)
def test_missing_file_and_path_traversal_exit_policy(
    tmp_path: Path,
    entry: dict[str, Any],
    expected_exit: int,
) -> None:
    manifest = _manifest(tmp_path, [entry])
    result = runner.invoke(app, ["import-batch", str(manifest), "--json"])
    assert result.exit_code == expected_exit
    assert "Traceback" not in result.output


def test_invalid_manifest_and_database_failure_are_concise(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    invalid = tmp_path / "invalid.json"
    invalid.write_text("{}", encoding="utf-8")
    invalid_result = runner.invoke(app, ["import-batch", str(invalid)])
    assert invalid_result.exit_code == 2
    assert "Batch manifest error" in invalid_result.stderr

    _copy(tmp_path, "one.html")
    manifest = _manifest(tmp_path, [_entry("one", "one.html")])

    def fail(database: Path | str | None) -> None:
        del database
        raise DatabaseLifecycleError("injected batch lifecycle failure")

    monkeypatch.setattr(
        "reinaluxe_recovery.batch.workflow.initialize_database",
        fail,
    )
    database_result = runner.invoke(
        app,
        ["import-batch", str(manifest), "--database", str(tmp_path / "fail.db")],
    )
    assert database_result.exit_code == 3
    assert "injected batch lifecycle failure" in database_result.stderr
    assert "Traceback" not in database_result.output


def test_output_creates_requested_parents_and_never_overwrites(tmp_path: Path) -> None:
    _copy(tmp_path, "one.html")
    manifest = _manifest(tmp_path, [_entry("one", "one.html")])
    output = tmp_path / "reports" / "batch.json"

    written = runner.invoke(
        app,
        ["import-batch", str(manifest), "--output", str(output)],
    )
    refused = runner.invoke(
        app,
        ["import-batch", str(manifest), "--output", str(output)],
    )

    assert written.exit_code == 0
    assert json.loads(output.read_text(encoding="utf-8"))["batch_id"] == "cli-batch"
    assert refused.exit_code == 2
    assert "refusing to overwrite" in refused.stderr


def test_duplicate_entry_filters_are_a_concise_input_error(tmp_path: Path) -> None:
    _copy(tmp_path, "one.html")
    manifest = _manifest(tmp_path, [_entry("one", "one.html")])
    result = runner.invoke(
        app,
        [
            "import-batch",
            str(manifest),
            "--entry-id",
            "one",
            "--entry-id",
            "one",
        ],
    )
    assert result.exit_code == 2
    assert "Batch option error" in result.stderr
    assert "Traceback" not in result.output


def test_persistence_system_failure_exits_four(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _copy(tmp_path, "one.html")
    manifest = _manifest(tmp_path, [_entry("one", "one.html")])

    def fail(*args: object, **kwargs: object) -> None:
        del args, kwargs
        raise PersistenceWriteError("injected batch persistence failure")

    monkeypatch.setattr(
        "reinaluxe_recovery.batch.workflow.ImportPersistenceService.save_import_result",
        fail,
    )
    result = runner.invoke(
        app,
        [
            "import-batch",
            str(manifest),
            "--database",
            str(tmp_path / "persistence.db"),
            "--json",
        ],
    )
    assert result.exit_code == 4
    assert json.loads(result.stdout)["results"][0]["failure_kind"] == "persistence"
    assert "injected batch persistence failure" in result.stdout
    assert "Traceback" not in result.output
