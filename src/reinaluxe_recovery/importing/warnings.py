"""Warnings emitted by deterministic offline imports."""

from enum import StrEnum

from pydantic import Field

from reinaluxe_recovery.domain.base import DomainModel, NonEmptyText


class ImportWarningSeverity(StrEnum):
    """Whether an import issue is recoverable or fatal."""

    WARNING = "warning"
    FATAL = "fatal"


class ImportWarningCode(StrEnum):
    """Stable machine-readable import warning codes."""

    MALFORMED_JSON_LD = "malformed_json_ld"
    UNSUPPORTED_JSON_LD = "unsupported_json_ld"
    INVALID_CANONICAL_URL = "invalid_canonical_url"
    INVALID_RESOURCE_URL = "invalid_resource_url"
    INVALID_DATE = "invalid_date"
    INVALID_LANGUAGE = "invalid_language"
    INCOMPLETE_FAQ = "incomplete_faq"
    MISSING_TITLE = "missing_title"
    MISSING_LANGUAGE = "missing_language"
    MISSING_ARTICLE_BODY = "missing_article_body"
    NORMALIZATION_FAILED = "normalization_failed"


class ImportWarning(DomainModel):
    """A recoverable extraction issue or controlled fatal failure."""

    severity: ImportWarningSeverity
    code: ImportWarningCode
    message: NonEmptyText
    location: str | None = Field(default=None, max_length=500)
