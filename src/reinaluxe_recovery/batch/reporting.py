"""Pure aggregation for stable batch reports."""

from datetime import datetime
from pathlib import Path

from reinaluxe_recovery.batch.contracts import (
    BatchEntryResult,
    BatchEntryStatus,
    BatchImportResult,
    BatchManifest,
    BatchOverallStatus,
)
from reinaluxe_recovery.persistence import PersistDisposition


def build_batch_result(
    *,
    manifest: BatchManifest,
    manifest_path: Path,
    database_path: Path | None,
    started_at: datetime,
    completed_at: datetime,
    results: list[BatchEntryResult],
) -> BatchImportResult:
    """Derive every aggregate count from immutable ordered entry results."""
    attempted = [
        item
        for item in results
        if item.status in {BatchEntryStatus.SUCCEEDED, BatchEntryStatus.FAILED}
    ]
    failed = [item for item in results if item.status is BatchEntryStatus.FAILED]
    return BatchImportResult(
        batch_id=manifest.batch_id,
        manifest_path=manifest_path,
        database_path=database_path,
        started_at=started_at,
        completed_at=completed_at,
        total_entries=len(manifest.entries),
        enabled_entries=sum(entry.enabled for entry in manifest.entries),
        attempted_entries=len(attempted),
        succeeded_entries=sum(
            item.status is BatchEntryStatus.SUCCEEDED for item in results
        ),
        failed_entries=len(failed),
        skipped_entries=sum(
            item.status in {BatchEntryStatus.SKIPPED, BatchEntryStatus.NOT_ATTEMPTED}
            for item in results
        ),
        created_pages=sum(
            item.page_disposition is PersistDisposition.CREATED for item in results
        ),
        reused_pages=sum(
            item.page_disposition is PersistDisposition.REUSED for item in results
        ),
        created_crawls=sum(
            item.crawl_disposition is PersistDisposition.CREATED for item in results
        ),
        reused_crawls=sum(
            item.crawl_disposition is PersistDisposition.REUSED for item in results
        ),
        created_article_versions=sum(
            item.article_disposition
            in {PersistDisposition.CREATED, PersistDisposition.VERSION_CREATED}
            for item in results
        ),
        reused_article_versions=sum(
            item.article_disposition is PersistDisposition.REUSED for item in results
        ),
        results=results,
        overall_status=(
            BatchOverallStatus.COMPLETED_WITH_FAILURES
            if failed
            else BatchOverallStatus.SUCCEEDED
        ),
    )
