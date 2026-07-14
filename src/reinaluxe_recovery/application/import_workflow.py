"""Coordinate one offline HTML import with optional local persistence."""

from pydantic import BaseModel, ConfigDict

from reinaluxe_recovery.importing import (
    HtmlFileInput,
    ImportResult,
    ImportStatus,
    import_html_file,
)
from reinaluxe_recovery.persistence import ImportPersistenceService, SessionFactory
from reinaluxe_recovery.persistence.dto import PersistImportResult


class ImportWorkflowResult(BaseModel):
    """Stable output containing import and optional persistence outcomes."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    import_result: ImportResult
    persistence_result: PersistImportResult | None = None


class OfflineImportWorkflow:
    """Call the existing importer exactly once, then delegate persistence."""

    def __init__(self, session_factory: SessionFactory) -> None:
        self._persistence = ImportPersistenceService(session_factory)

    def run(
        self,
        import_input: HtmlFileInput,
        *,
        persist_failed: bool = True,
    ) -> ImportWorkflowResult:
        """Import once and persist according to the explicit failed policy."""
        import_result = import_html_file(import_input)
        persistence_result = None
        if import_result.status is ImportStatus.SUCCEEDED or persist_failed:
            persistence_result = self._persistence.save_import_result(import_result)
        return ImportWorkflowResult(
            import_result=import_result,
            persistence_result=persistence_result,
        )
