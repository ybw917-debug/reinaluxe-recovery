"""Sequential application workflow for deterministic offline batch imports."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter_ns

from sqlalchemy import Engine

from reinaluxe_recovery.batch.contracts import (
    BatchEntryResult,
    BatchEntryStatus,
    BatchFailureKind,
    BatchImportOptions,
    BatchImportResult,
    BatchManifest,
    BatchManifestEntry,
)
from reinaluxe_recovery.batch.exceptions import (
    BatchEntryFileError,
    BatchSelectionError,
)
from reinaluxe_recovery.batch.loader import (
    load_batch_manifest,
    load_html_entry,
    validate_manifest_paths,
)
from reinaluxe_recovery.batch.reporting import build_batch_result
from reinaluxe_recovery.importing import (
    ImportResult,
    ImportSourceType,
    ImportStatus,
    ImportWarningSeverity,
    normalize_document,
    parse_html,
)
from reinaluxe_recovery.persistence import (
    ImportPersistenceService,
    PersistenceError,
    PersistImportResult,
    create_database_engine,
    create_session_factory,
    initialize_database,
)

Clock = Callable[[], datetime]


def _utc_now() -> datetime:
    return datetime.now(UTC)


class BatchImportWorkflow:
    """Validate once, then process selected entries sequentially and offline."""

    def __init__(self, *, clock: Clock = _utc_now) -> None:
        self._clock = clock

    def run(
        self,
        manifest_path: Path,
        *,
        options: BatchImportOptions,
        database_path: Path | None = None,
    ) -> BatchImportResult:
        """Run one batch without parallel work, retries, or network access."""
        resolved_manifest_path = manifest_path.expanduser().resolve()
        manifest = load_batch_manifest(resolved_manifest_path)
        validate_manifest_paths(resolved_manifest_path, manifest)
        selected_ids = self._selected_ids(manifest, options)
        persistence_requested = database_path is not None and not options.dry_run
        lifecycle_path: Path | None = None
        engine: Engine | None = None
        persistence: ImportPersistenceService | None = None
        if persistence_requested:
            lifecycle = initialize_database(database_path)
            lifecycle_path = lifecycle.database_path
            engine = create_database_engine(lifecycle.database_url)
            persistence = ImportPersistenceService(create_session_factory(engine))

        started_at = self._clock()
        results: list[BatchEntryResult] = []
        failed_fast = False
        try:
            for entry in manifest.entries:
                if not entry.enabled:
                    results.append(
                        self._not_processed(entry, BatchEntryStatus.SKIPPED, "disabled")
                    )
                    continue
                if entry.entry_id not in selected_ids:
                    results.append(
                        self._not_processed(
                            entry, BatchEntryStatus.SKIPPED, "not selected"
                        )
                    )
                    continue
                if failed_fast:
                    results.append(
                        self._not_processed(
                            entry,
                            BatchEntryStatus.NOT_ATTEMPTED,
                            "not attempted after fail-fast stopped the batch",
                        )
                    )
                    continue
                result = self._run_entry(
                    resolved_manifest_path,
                    manifest,
                    entry,
                    persistence,
                    persist_failed=options.persist_failed,
                )
                results.append(result)
                if (
                    result.status is BatchEntryStatus.FAILED
                    and not options.continue_on_error
                ):
                    failed_fast = True
        finally:
            if engine is not None:
                engine.dispose()
        completed_at = self._clock()
        return build_batch_result(
            manifest=manifest,
            manifest_path=resolved_manifest_path,
            database_path=lifecycle_path,
            started_at=started_at,
            completed_at=completed_at,
            results=results,
        )

    @staticmethod
    def _selected_ids(
        manifest: BatchManifest,
        options: BatchImportOptions,
    ) -> set[str]:
        all_ids = {entry.entry_id for entry in manifest.entries}
        requested = set(options.entry_ids or all_ids)
        unknown = requested - all_ids
        if unknown:
            raise BatchSelectionError(
                "unknown entry_id filter(s): " + ", ".join(sorted(unknown))
            )
        selected = [
            entry.entry_id
            for entry in manifest.entries
            if entry.enabled and entry.entry_id in requested
        ]
        if options.limit is not None:
            selected = selected[: options.limit]
        if not selected:
            raise BatchSelectionError("no matching enabled manifest entries")
        return set(selected)

    def _run_entry(
        self,
        manifest_path: Path,
        manifest: BatchManifest,
        entry: BatchManifestEntry,
        persistence: ImportPersistenceService | None,
        *,
        persist_failed: bool,
    ) -> BatchEntryResult:
        started_at = self._clock()
        timer = perf_counter_ns()
        try:
            loaded = load_html_entry(manifest_path, entry)
            document = parse_html(
                source_url=entry.source_url,
                fetched_at=manifest.effective_fetched_at(entry),
                status_code=entry.status_code,
                headers=manifest.effective_headers(entry),
                html_body=loaded.html_body,
            )
            import_result = normalize_document(document, ImportSourceType.HTML_FILE)
            persisted = self._persist(import_result, persistence, persist_failed)
            completed_at = self._clock()
            return self._completed_result(
                entry,
                import_result,
                persisted,
                started_at,
                completed_at,
                timer,
            )
        except BatchEntryFileError as error:
            return self._failed_result(
                entry,
                started_at,
                timer,
                BatchFailureKind.FILE,
                str(error),
            )
        except PersistenceError as error:
            return self._failed_result(
                entry,
                started_at,
                timer,
                BatchFailureKind.PERSISTENCE,
                str(error),
            )

    @staticmethod
    def _persist(
        import_result: ImportResult,
        persistence: ImportPersistenceService | None,
        persist_failed: bool,
    ) -> PersistImportResult | None:
        if persistence is None:
            return None
        if import_result.status is ImportStatus.FAILED and not persist_failed:
            return None
        return persistence.save_import_result(import_result)

    def _completed_result(
        self,
        entry: BatchManifestEntry,
        import_result: ImportResult,
        persisted: PersistImportResult | None,
        started_at: datetime,
        completed_at: datetime,
        timer: int,
    ) -> BatchEntryResult:
        import_success = import_result.status is ImportStatus.SUCCEEDED
        fatal = [
            warning.message
            for warning in import_result.warnings
            if warning.severity is ImportWarningSeverity.FATAL
        ]
        return BatchEntryResult(
            entry_id=entry.entry_id,
            html_path=entry.html_path,
            source_url=entry.source_url,
            status=(
                BatchEntryStatus.SUCCEEDED
                if import_success
                else BatchEntryStatus.FAILED
            ),
            import_success=import_success,
            persistence_success=persisted is not None,
            page_disposition=(persisted.page_disposition if persisted else None),
            crawl_disposition=(persisted.crawl_disposition if persisted else None),
            article_disposition=(persisted.article_disposition if persisted else None),
            article_version_number=(
                persisted.article_version_number if persisted else None
            ),
            warnings=import_result.warnings,
            fatal_diagnostics=fatal,
            error_message="; ".join(fatal) or None,
            failure_kind=(None if import_success else BatchFailureKind.IMPORT),
            started_at=started_at,
            completed_at=completed_at,
            duration_ms=max(0, (perf_counter_ns() - timer) // 1_000_000),
            source_hash=import_result.source_hash,
        )

    def _failed_result(
        self,
        entry: BatchManifestEntry,
        started_at: datetime,
        timer: int,
        kind: BatchFailureKind,
        message: str,
    ) -> BatchEntryResult:
        completed_at = self._clock()
        return BatchEntryResult(
            entry_id=entry.entry_id,
            html_path=entry.html_path,
            source_url=entry.source_url,
            status=BatchEntryStatus.FAILED,
            import_success=False,
            persistence_success=False,
            error_message=message,
            failure_kind=kind,
            started_at=started_at,
            completed_at=completed_at,
            duration_ms=max(0, (perf_counter_ns() - timer) // 1_000_000),
        )

    def _not_processed(
        self,
        entry: BatchManifestEntry,
        status: BatchEntryStatus,
        reason: str,
    ) -> BatchEntryResult:
        now = self._clock()
        return BatchEntryResult(
            entry_id=entry.entry_id,
            html_path=entry.html_path,
            source_url=entry.source_url,
            status=status,
            import_success=False,
            persistence_success=False,
            error_message=reason,
            started_at=now,
            completed_at=now,
            duration_ms=0,
        )
