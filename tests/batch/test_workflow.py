"""Application tests for sequential offline batch orchestration."""

import importlib
import json
from pathlib import Path
from typing import Any

import pytest

from reinaluxe_recovery.batch import (
    BatchEntryStatus,
    BatchImportOptions,
    BatchImportResult,
    BatchImportWorkflow,
    BatchManifestError,
    BatchPathError,
    BatchSelectionError,
)
from reinaluxe_recovery.persistence import PersistDisposition

BATCH_FIXTURES = Path(__file__).parent / "fixtures" / "html"


def _entry(
    entry_id: str,
    html_path: str,
    *,
    source_url: str | None = None,
    fetched_at: str | None = None,
    enabled: bool = True,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "entry_id": entry_id,
        "html_path": html_path,
        "source_url": source_url or f"https://owner.example/{entry_id}/",
        "enabled": enabled,
    }
    if fetched_at is not None:
        result["fetched_at"] = fetched_at
    return result


def _write_manifest(
    tmp_path: Path,
    entries: list[dict[str, Any]],
    *,
    name: str = "manifest.json",
) -> Path:
    path = tmp_path / name
    path.write_text(
        json.dumps(
            {
                "contract_version": "1.0",
                "batch_id": "workflow-batch",
                "created_at": "2026-07-14T10:00:00+00:00",
                "default_fetched_at": "2026-07-14T09:00:00+00:00",
                "entries": entries,
            }
        ),
        encoding="utf-8",
    )
    return path


def _copy(tmp_path: Path, target: str, fixture: str = "article-a.html") -> None:
    path = tmp_path / target
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        (BATCH_FIXTURES / fixture).read_text(encoding="utf-8"),
        encoding="utf-8",
    )


def test_successful_multi_entry_dry_run_preserves_order_and_skips_disabled(
    tmp_path: Path,
) -> None:
    _copy(tmp_path, "html/one.html")
    _copy(tmp_path, "html/two.html", "article-a-changed.html")
    _copy(tmp_path, "html/disabled.html", "fatal.html")
    manifest = _write_manifest(
        tmp_path,
        [
            _entry("one", "html/one.html"),
            _entry("disabled", "html/disabled.html", enabled=False),
            _entry("two", "html/two.html"),
        ],
    )

    result = BatchImportWorkflow().run(
        manifest,
        options=BatchImportOptions(dry_run=True),
    )

    assert [item.entry_id for item in result.results] == ["one", "disabled", "two"]
    assert [item.status for item in result.results] == [
        BatchEntryStatus.SUCCEEDED,
        BatchEntryStatus.SKIPPED,
        BatchEntryStatus.SUCCEEDED,
    ]
    assert result.database_path is None
    assert result.attempted_entries == 2
    assert result.skipped_entries == 1
    assert all(not item.persistence_success for item in result.results)


def test_each_selected_html_file_is_parsed_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _copy(tmp_path, "one.html")
    _copy(tmp_path, "two.html", "article-a-changed.html")
    manifest = _write_manifest(
        tmp_path,
        [_entry("one", "one.html"), _entry("two", "two.html")],
    )
    module = importlib.import_module("reinaluxe_recovery.batch.workflow")
    original = module.parse_html
    calls = 0

    def counted_parse(**kwargs: Any) -> Any:
        nonlocal calls
        calls += 1
        return original(**kwargs)

    monkeypatch.setattr(module, "parse_html", counted_parse)
    BatchImportWorkflow().run(manifest, options=BatchImportOptions(dry_run=True))
    assert calls == 2


def test_hash_mismatch_prevents_parsing_and_persistence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _copy(tmp_path, "hash.html")
    entry = _entry("hash", "hash.html")
    entry["expected_source_hash"] = "0" * 64
    manifest = _write_manifest(tmp_path, [entry])
    module = importlib.import_module("reinaluxe_recovery.batch.workflow")

    def forbidden_parse(**kwargs: Any) -> Any:
        del kwargs
        pytest.fail("hash mismatch must prevent parsing")

    monkeypatch.setattr(module, "parse_html", forbidden_parse)
    database = tmp_path / "hash.db"
    result = BatchImportWorkflow().run(
        manifest,
        options=BatchImportOptions(),
        database_path=database,
    )

    assert result.failed_entries == 1
    assert result.results[0].source_hash is None
    assert "source hash mismatch" in (result.results[0].error_message or "")


def test_continue_on_error_and_fail_fast_mark_remaining_entries(tmp_path: Path) -> None:
    _copy(tmp_path, "one.html")
    _copy(tmp_path, "three.html", "article-a-changed.html")
    entries = [
        _entry("one", "one.html"),
        _entry("missing", "missing.html"),
        _entry("three", "three.html"),
    ]
    manifest = _write_manifest(tmp_path, entries)

    continued = BatchImportWorkflow().run(
        manifest,
        options=BatchImportOptions(dry_run=True, continue_on_error=True),
    )
    stopped = BatchImportWorkflow().run(
        manifest,
        options=BatchImportOptions(dry_run=True, continue_on_error=False),
    )

    assert [item.status for item in continued.results] == [
        BatchEntryStatus.SUCCEEDED,
        BatchEntryStatus.FAILED,
        BatchEntryStatus.SUCCEEDED,
    ]
    assert [item.status for item in stopped.results] == [
        BatchEntryStatus.SUCCEEDED,
        BatchEntryStatus.FAILED,
        BatchEntryStatus.NOT_ATTEMPTED,
    ]


def test_persisted_batch_is_idempotent_and_unchanged_content_reuses_version(
    tmp_path: Path,
) -> None:
    _copy(tmp_path, "html/first.html")
    _copy(tmp_path, "html/second.html")
    entries = [
        _entry(
            "first",
            "html/first.html",
            source_url="https://owner.example/batch/article-a/",
            fetched_at="2026-07-14T09:00:00+00:00",
        ),
        _entry(
            "second",
            "html/second.html",
            source_url="https://owner.example/batch/article-a/",
            fetched_at="2026-07-14T10:00:00+00:00",
        ),
    ]
    manifest = _write_manifest(tmp_path, entries)
    database = tmp_path / "batch.db"
    workflow = BatchImportWorkflow()

    first = workflow.run(
        manifest,
        options=BatchImportOptions(),
        database_path=database,
    )
    repeated = workflow.run(
        manifest,
        options=BatchImportOptions(),
        database_path=database,
    )

    assert first.created_pages == 1
    assert first.created_crawls == 2
    assert first.created_article_versions == 1
    assert first.reused_article_versions == 1
    assert repeated.reused_pages == 2
    assert repeated.reused_crawls == 2
    assert repeated.reused_article_versions == 2
    assert {item.article_version_number for item in repeated.results} == {1}


def test_changed_content_creates_next_version(tmp_path: Path) -> None:
    _copy(tmp_path, "html/original.html")
    _copy(tmp_path, "html/changed.html", "article-a-changed.html")
    manifest = _write_manifest(
        tmp_path,
        [
            _entry(
                "original",
                "html/original.html",
                fetched_at="2026-07-14T09:00:00+00:00",
            ),
            _entry(
                "changed",
                "html/changed.html",
                fetched_at="2026-07-14T10:00:00+00:00",
            ),
        ],
    )

    result = BatchImportWorkflow().run(
        manifest,
        options=BatchImportOptions(),
        database_path=tmp_path / "changed.db",
    )

    assert [item.article_disposition for item in result.results] == [
        PersistDisposition.CREATED,
        PersistDisposition.VERSION_CREATED,
    ]
    assert [item.article_version_number for item in result.results] == [1, 2]


def test_failed_entry_does_not_roll_back_successful_earlier_entry(
    tmp_path: Path,
) -> None:
    _copy(tmp_path, "valid.html")
    manifest = _write_manifest(
        tmp_path,
        [_entry("valid", "valid.html"), _entry("missing", "missing.html")],
    )
    database = tmp_path / "partial.db"
    workflow = BatchImportWorkflow()

    first = workflow.run(
        manifest,
        options=BatchImportOptions(),
        database_path=database,
    )
    resumed = workflow.run(
        manifest,
        options=BatchImportOptions(),
        database_path=database,
    )

    assert first.results[0].status is BatchEntryStatus.SUCCEEDED
    assert first.results[1].status is BatchEntryStatus.FAILED
    assert resumed.results[0].page_disposition is PersistDisposition.REUSED
    assert resumed.results[0].crawl_disposition is PersistDisposition.REUSED


def test_invalid_manifest_and_path_violation_cause_zero_database_writes(
    tmp_path: Path,
) -> None:
    duplicate = _write_manifest(
        tmp_path,
        [_entry("same", "one.html"), _entry("same", "two.html")],
        name="duplicate.json",
    )
    traversal = _write_manifest(
        tmp_path,
        [_entry("escape", "../outside.html")],
        name="traversal.json",
    )
    database = tmp_path / "must-not-exist.db"

    with pytest.raises(BatchManifestError):
        BatchImportWorkflow().run(
            duplicate,
            options=BatchImportOptions(),
            database_path=database,
        )
    with pytest.raises(BatchPathError):
        BatchImportWorkflow().run(
            traversal,
            options=BatchImportOptions(),
            database_path=database,
        )
    assert not database.exists()


def test_dry_run_never_creates_supplied_database(tmp_path: Path) -> None:
    _copy(tmp_path, "valid.html")
    manifest = _write_manifest(tmp_path, [_entry("valid", "valid.html")])
    database = tmp_path / "dry-run.db"
    result = BatchImportWorkflow().run(
        manifest,
        options=BatchImportOptions(dry_run=True),
        database_path=database,
    )
    assert result.database_path is None
    assert not database.exists()


def test_persist_failed_policy_is_explicit(tmp_path: Path) -> None:
    _copy(tmp_path, "fatal.html", "fatal.html")
    manifest = _write_manifest(tmp_path, [_entry("fatal", "fatal.html")])

    persisted = BatchImportWorkflow().run(
        manifest,
        options=BatchImportOptions(persist_failed=True),
        database_path=tmp_path / "persisted.db",
    )
    skipped = BatchImportWorkflow().run(
        manifest,
        options=BatchImportOptions(persist_failed=False),
        database_path=tmp_path / "skipped.db",
    )

    assert persisted.results[0].status is BatchEntryStatus.FAILED
    assert persisted.results[0].persistence_success is True
    assert persisted.results[0].article_disposition is PersistDisposition.FAILED
    assert skipped.results[0].persistence_success is False


def test_entry_filter_unknown_filter_limit_and_round_trip(tmp_path: Path) -> None:
    for name in ("one", "two", "three"):
        _copy(tmp_path, f"{name}.html")
    manifest = _write_manifest(
        tmp_path,
        [
            _entry("one", "one.html"),
            _entry("two", "two.html"),
            _entry("three", "three.html"),
        ],
    )
    result = BatchImportWorkflow().run(
        manifest,
        options=BatchImportOptions(
            dry_run=True,
            entry_ids=["three", "one"],
            limit=1,
        ),
    )

    assert [item.status for item in result.results] == [
        BatchEntryStatus.SUCCEEDED,
        BatchEntryStatus.SKIPPED,
        BatchEntryStatus.SKIPPED,
    ]
    assert result.attempted_entries == 1
    assert BatchImportResult.model_validate_json(result.model_dump_json()) == result

    with pytest.raises(BatchSelectionError, match="unknown entry_id"):
        BatchImportWorkflow().run(
            manifest,
            options=BatchImportOptions(dry_run=True, entry_ids=["unknown"]),
        )
