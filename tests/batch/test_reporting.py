"""Pure aggregate-count tests for batch reporting."""

from datetime import UTC, datetime
from pathlib import Path

from reinaluxe_recovery.batch import (
    BatchEntryResult,
    BatchEntryStatus,
    BatchManifest,
    BatchOverallStatus,
    build_batch_result,
)
from reinaluxe_recovery.persistence import PersistDisposition


def test_counts_are_derived_from_entry_results() -> None:
    now = datetime(2026, 7, 14, tzinfo=UTC)
    manifest = BatchManifest.model_validate(
        {
            "contract_version": "1.0",
            "batch_id": "report",
            "created_at": now,
            "default_fetched_at": now,
            "entries": [
                {
                    "entry_id": "created",
                    "html_path": "created.html",
                    "source_url": "https://owner.example/created/",
                },
                {
                    "entry_id": "failed",
                    "html_path": "failed.html",
                    "source_url": "https://owner.example/failed/",
                },
                {
                    "entry_id": "disabled",
                    "html_path": "disabled.html",
                    "source_url": "https://owner.example/disabled/",
                    "enabled": False,
                },
            ],
        }
    )
    results = [
        BatchEntryResult(
            entry_id="created",
            html_path=Path("created.html"),
            source_url="https://owner.example/created/",
            status=BatchEntryStatus.SUCCEEDED,
            import_success=True,
            persistence_success=True,
            page_disposition=PersistDisposition.CREATED,
            crawl_disposition=PersistDisposition.CREATED,
            article_disposition=PersistDisposition.CREATED,
            article_version_number=1,
            started_at=now,
            completed_at=now,
            duration_ms=0,
        ),
        BatchEntryResult(
            entry_id="failed",
            html_path=Path("failed.html"),
            source_url="https://owner.example/failed/",
            status=BatchEntryStatus.FAILED,
            import_success=False,
            persistence_success=False,
            started_at=now,
            completed_at=now,
            duration_ms=0,
        ),
        BatchEntryResult(
            entry_id="disabled",
            html_path=Path("disabled.html"),
            source_url="https://owner.example/disabled/",
            status=BatchEntryStatus.SKIPPED,
            import_success=False,
            persistence_success=False,
            started_at=now,
            completed_at=now,
            duration_ms=0,
        ),
    ]

    report = build_batch_result(
        manifest=manifest,
        manifest_path=Path("manifest.json"),
        database_path=Path("batch.db"),
        started_at=now,
        completed_at=now,
        results=results,
    )

    assert report.total_entries == 3
    assert report.enabled_entries == 2
    assert report.attempted_entries == 2
    assert report.succeeded_entries == 1
    assert report.failed_entries == 1
    assert report.skipped_entries == 1
    assert report.created_pages == 1
    assert report.created_crawls == 1
    assert report.created_article_versions == 1
    assert report.overall_status is BatchOverallStatus.COMPLETED_WITH_FAILURES
