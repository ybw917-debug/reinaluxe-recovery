"""End-to-end tests for the local database and persistence CLI workflow."""

import json
from pathlib import Path
from typing import Any, cast

import pytest
from typer.testing import CliRunner

from reinaluxe_recovery.application import OfflineImportWorkflow
from reinaluxe_recovery.cli import app
from reinaluxe_recovery.persistence import DatabaseLifecycleError
from reinaluxe_recovery.persistence.exceptions import PersistenceWriteError

FIXTURES = Path(__file__).parent / "importing" / "fixtures"
runner = CliRunner()


def _import_args(
    html_path: Path,
    database_path: Path | None,
    *,
    source_url: str = "https://owner.example/cli/",
    fetched_at: str = "2026-07-14T12:00:00+00:00",
) -> list[str]:
    args = [
        "import-html",
        str(html_path),
        "--source-url",
        source_url,
        "--fetched-at",
        fetched_at,
    ]
    if database_path is not None:
        args.extend(("--database", str(database_path)))
    return args


def _invoke_json(args: list[str], expected_exit: int = 0) -> dict[str, Any]:
    result = runner.invoke(app, args)
    assert result.exit_code == expected_exit, result.output
    return cast(dict[str, Any], json.loads(result.stdout))


def test_db_init_success_repeat_and_json_output(tmp_path: Path) -> None:
    """Database initialization is visible, healthy, and idempotent."""
    database = tmp_path / "nested" / "cli.db"
    first = _invoke_json(["db-init", "--database", str(database), "--json"])
    second = _invoke_json(["db-init", "--database", str(database), "--json"])

    assert database.exists()
    assert first["previous_revision"] is None
    assert first["migration_performed"] is True
    assert first["healthy"] is True
    assert second["migration_performed"] is False
    assert second["previous_revision"] == second["current_revision"]


def test_db_init_human_output(tmp_path: Path) -> None:
    """Human initialization output explains path, revision, migration, and health."""
    result = runner.invoke(
        app,
        ["db-init", "--database", str(tmp_path / "human.db")],
    )

    assert result.exit_code == 0
    assert "Database:" in result.stdout
    assert "Current revision:" in result.stdout
    assert "Migration: applied" in result.stdout
    assert "Health: healthy" in result.stdout


def test_db_init_migration_failure_has_exit_three(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Expected lifecycle errors are concise and deterministic."""

    def fail(database: Path | None) -> None:
        del database
        raise DatabaseLifecycleError("injected migration failure")

    monkeypatch.setattr("reinaluxe_recovery.cli.initialize_database", fail)
    result = runner.invoke(
        app,
        ["db-init", "--database", str(tmp_path / "failure.db")],
    )

    assert result.exit_code == 3
    assert "injected migration failure" in result.stderr
    assert "Traceback" not in result.output


def test_json_only_import_remains_unwrapped_and_alias_is_compatible(
    tmp_path: Path,
) -> None:
    """Without --database the original ImportResult-only output remains stable."""
    output = tmp_path / "legacy.json"
    result = runner.invoke(
        app,
        [
            *_import_args(FIXTURES / "minimal-article.html", None),
            "--json-output",
            str(output),
        ],
    )

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert result.exit_code == 0
    assert payload["status"] == "succeeded"
    assert "import_result" not in payload
    assert "persistence_result" not in payload


def test_persisted_import_auto_initializes_and_repeats_idempotently(
    tmp_path: Path,
) -> None:
    """A missing database is safely initialized and exact repeats are reused."""
    database = tmp_path / "automatic.db"
    args = _import_args(FIXTURES / "minimal-article.html", database)

    first = _invoke_json(args)
    second = _invoke_json(args)

    assert database.exists()
    assert first["import_result"]["status"] == "succeeded"
    assert first["persistence_result"]["article_version_number"] == 1
    assert second["persistence_result"]["crawl_disposition"] == "reused"
    assert second["persistence_result"]["article_disposition"] == "reused"


def test_unchanged_then_changed_content_versioning(tmp_path: Path) -> None:
    """New observations reuse unchanged content and version meaningful changes."""
    database = tmp_path / "versions.db"
    first_html = tmp_path / "first.html"
    second_html = tmp_path / "second.html"
    original = (FIXTURES / "minimal-article.html").read_text(encoding="utf-8")
    first_html.write_text(original, encoding="utf-8")
    second_html.write_text(
        original.replace("Minimal Offline Article", "Revised Offline Article"),
        encoding="utf-8",
    )

    _invoke_json(_import_args(first_html, database))
    unchanged = _invoke_json(
        _import_args(
            first_html,
            database,
            fetched_at="2026-07-14T13:00:00+00:00",
        )
    )
    changed = _invoke_json(
        _import_args(
            second_html,
            database,
            fetched_at="2026-07-14T14:00:00+00:00",
        )
    )

    assert unchanged["persistence_result"]["crawl_disposition"] == "created"
    assert unchanged["persistence_result"]["article_disposition"] == "reused"
    assert unchanged["persistence_result"]["article_version_number"] == 1
    assert changed["persistence_result"]["article_disposition"] == "version_created"
    assert changed["persistence_result"]["article_version_number"] == 2


def test_failed_import_policy_can_persist_or_skip_diagnostics(tmp_path: Path) -> None:
    """Failed imports persist by default and may be explicitly skipped."""
    persisted = _invoke_json(
        _import_args(
            FIXTURES / "no-article-body.html",
            tmp_path / "failed.db",
            source_url="https://owner.example/failed/",
        ),
        expected_exit=1,
    )
    skipped = _invoke_json(
        [
            *_import_args(
                FIXTURES / "no-article-body.html",
                tmp_path / "skipped.db",
                source_url="https://owner.example/skipped/",
            ),
            "--no-persist-failed",
        ],
        expected_exit=1,
    )

    assert persisted["persistence_result"]["article_disposition"] == "failed"
    assert skipped["persistence_result"] is None


def test_persistence_failure_has_exit_four(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Persistence failures are distinct from input and migration failures."""

    def fail(*args: object, **kwargs: object) -> None:
        del args, kwargs
        raise PersistenceWriteError("injected persistence failure")

    monkeypatch.setattr(OfflineImportWorkflow, "run", fail)
    result = runner.invoke(
        app,
        _import_args(FIXTURES / "minimal-article.html", tmp_path / "failure.db"),
    )

    assert result.exit_code == 4
    assert "injected persistence failure" in result.stderr
    assert "Traceback" not in result.output


def test_list_pages_empty_human_and_json(tmp_path: Path) -> None:
    """An empty automatically initialized database is clear in both formats."""
    database = tmp_path / "empty.db"
    human = runner.invoke(app, ["list-pages", "--database", str(database)])
    payload = _invoke_json(["list-pages", "--database", str(database), "--json"])

    assert human.exit_code == 0
    assert "No pages have been imported yet." in human.stdout
    assert payload == {"items": [], "limit": None, "offset": 0}


def test_list_pages_table_json_pagination_and_order(tmp_path: Path) -> None:
    """Inventory is deterministic and includes versions and aggregate counts."""
    database = tmp_path / "inventory.db"
    for url in ("https://owner.example/b/", "https://owner.example/a/"):
        _invoke_json(
            _import_args(
                FIXTURES / "minimal-article.html",
                database,
                source_url=url,
            )
        )

    human = runner.invoke(app, ["list-pages", "--database", str(database)])
    payload = _invoke_json(
        [
            "list-pages",
            "--database",
            str(database),
            "--limit",
            "1",
            "--offset",
            "1",
            "--json",
        ]
    )

    assert human.exit_code == 0
    assert "Canonical URL" in human.stdout
    assert "Local pages" in human.stdout
    assert payload["limit"] == 1
    assert payload["offset"] == 1
    item = payload["items"][0]
    assert item["canonical_url"] == "https://owner.example/b/"
    assert item["current_version_number"] == 1
    assert item["crawl_count"] == 1
    assert item["article_version_count"] == 1


def test_show_page_human_json_history_and_not_found(tmp_path: Path) -> None:
    """Page details distinguish normal, historical, warning, and absent states."""
    database = tmp_path / "details.db"
    url = "https://owner.example/details/"
    _invoke_json(
        _import_args(
            FIXTURES / "malformed-json-ld.html",
            database,
            source_url=url,
        )
    )

    human = runner.invoke(
        app,
        ["show-page", url, "--database", str(database), "--include-history"],
    )
    payload = _invoke_json(
        [
            "show-page",
            url,
            "--database",
            str(database),
            "--include-history",
            "--json",
        ]
    )
    missing = runner.invoke(
        app,
        [
            "show-page",
            "https://owner.example/missing/",
            "--database",
            str(database),
        ],
    )

    assert human.exit_code == 0
    assert f"Page: {url}" in human.stdout
    assert "History:" in human.stdout
    assert "Warning for crawl" in human.stdout
    assert payload["page"]["canonical_url"] == url
    assert len(payload["crawl_history"]) == 1
    assert len(payload["article_version_history"]) == 1
    assert len(payload["warnings_by_crawl"][0]["warnings"]) == 1
    assert missing.exit_code == 5
    assert "page not found" in missing.stderr
    assert "Traceback" not in missing.output
