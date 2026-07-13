"""Validated contracts for deterministic offline content imports."""

from enum import StrEnum
from pathlib import Path
from typing import Literal, Self

from pydantic import (
    AwareDatetime,
    Field,
    FilePath,
    HttpUrl,
    JsonValue,
    model_validator,
)

from reinaluxe_recovery.domain import Article, CrawlSnapshot
from reinaluxe_recovery.domain.base import DomainModel, NonEmptyText, Sha256Digest
from reinaluxe_recovery.domain.enums import LinkType, SchemaType
from reinaluxe_recovery.importing.warnings import ImportWarning


class ImportSourceType(StrEnum):
    """Supported local input forms."""

    HTML_FILE = "html_file"
    JSON_FIXTURE = "json_fixture"


class ImportStatus(StrEnum):
    """Overall outcome of an import attempt."""

    SUCCEEDED = "succeeded"
    FAILED = "failed"


class FieldOrigin(StrEnum):
    """How a value entered the import result."""

    INPUT = "input"
    EXTRACTED = "extracted"
    NORMALIZED = "normalized"
    DERIVED = "derived"


class FieldProvenance(DomainModel):
    """Origin record for an imported or derived output field."""

    field: NonEmptyText
    origin: FieldOrigin
    source: NonEmptyText
    detail: str | None = Field(default=None, max_length=1_000)


class HtmlFileInput(DomainModel):
    """Provenance required to import a standalone local HTML file."""

    html_path: FilePath
    source_url: HttpUrl
    fetched_at: AwareDatetime
    headers: dict[str, str] = Field(default_factory=dict)


class JsonFixtureInput(DomainModel):
    """A complete offline HTTP observation stored as structured JSON."""

    source_url: HttpUrl
    fetched_at: AwareDatetime
    status_code: int = Field(ge=100, le=599)
    headers: dict[str, str] = Field(default_factory=dict)
    html_body: str


class ParsedHeading(DomainModel):
    """Heading retained in source-document order."""

    level: int = Field(ge=1, le=3)
    text: NonEmptyText
    anchor: str | None = Field(default=None, max_length=200)


class ParsedParagraph(DomainModel):
    """Visible paragraph extracted from editorial content."""

    text: NonEmptyText


class ParsedImage(DomainModel):
    """Image and directly observed presentation metadata."""

    source_url: HttpUrl
    alt_text: str | None = Field(default=None, max_length=500)
    caption: str | None = Field(default=None, max_length=1_000)
    width: int | None = Field(default=None, gt=0)
    height: int | None = Field(default=None, gt=0)


class ParsedLink(DomainModel):
    """Resolved HTTP(S) link found in editorial content."""

    target_url: HttpUrl
    link_type: LinkType
    anchor_text: str | None = Field(default=None, max_length=500)
    rel: list[str] = Field(default_factory=list)


class ParsedFAQItem(DomainModel):
    """Visible question-and-answer pair."""

    question: NonEmptyText
    answer: NonEmptyText


class ParsedSection(DomainModel):
    """Intermediate section before domain IDs and ordering are assigned."""

    heading: ParsedHeading | None = None
    paragraphs: list[ParsedParagraph] = Field(default_factory=list)
    images: list[ParsedImage] = Field(default_factory=list)
    links: list[ParsedLink] = Field(default_factory=list)
    faq_items: list[ParsedFAQItem] = Field(default_factory=list)


class ParsedSchemaMarkup(DomainModel):
    """Defensively decoded JSON-LD payload."""

    schema_type: SchemaType
    payload: dict[str, JsonValue]


class ParsedDocument(DomainModel):
    """Parser output that contains only explicit or normalized observations."""

    source_url: HttpUrl
    fetched_at: AwareDatetime
    status_code: int | None = Field(default=None, ge=100, le=599)
    headers: dict[str, str] = Field(default_factory=dict)
    html_body: str
    source_hash: Sha256Digest
    canonical_url: HttpUrl | None = None
    title: str | None = None
    h1: str | None = None
    language: str | None = None
    meta_description: str | None = Field(default=None, max_length=500)
    published_at: AwareDatetime | None = None
    modified_at: AwareDatetime | None = None
    sections: list[ParsedSection] = Field(default_factory=list)
    schema_markup: list[ParsedSchemaMarkup] = Field(default_factory=list)
    warnings: list[ImportWarning] = Field(default_factory=list)


class ImportResult(DomainModel):
    """Versioned result of one fully offline import attempt."""

    contract_version: Literal["1.0"] = "1.0"
    status: ImportStatus
    source_type: ImportSourceType
    snapshot: CrawlSnapshot
    article: Article | None
    warnings: list[ImportWarning] = Field(default_factory=list)
    source_hash: Sha256Digest
    provenance: list[FieldProvenance] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_outcome(self) -> Self:
        """Keep success/failure state aligned with the normalized article."""
        if self.status is ImportStatus.SUCCEEDED and self.article is None:
            raise ValueError("successful imports require an article")
        if self.status is ImportStatus.FAILED and self.article is not None:
            raise ValueError("failed imports must not contain an article")
        return self


def load_json_fixture(path: Path) -> JsonFixtureInput:
    """Load and validate a UTF-8 JSON fixture from a local path."""
    return JsonFixtureInput.model_validate_json(path.read_text(encoding="utf-8"))
