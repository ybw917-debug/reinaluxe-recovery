"""Normalize parsed offline HTML into validated domain records."""

from __future__ import annotations

import re
from uuid import UUID, uuid5

from pydantic import ValidationError

from reinaluxe_recovery.domain import (
    Article,
    ArticleStatus,
    ContentSection,
    ContentType,
    CrawlSnapshot,
    FAQItem,
    Heading,
    Image,
    Link,
    Paragraph,
    SchemaMarkup,
    SearchIntent,
)
from reinaluxe_recovery.importing.contracts import (
    FieldOrigin,
    FieldProvenance,
    HtmlFileInput,
    ImportResult,
    ImportSourceType,
    ImportStatus,
    JsonFixtureInput,
    ParsedDocument,
)
from reinaluxe_recovery.importing.html_parser import parse_html
from reinaluxe_recovery.importing.warnings import (
    ImportWarning,
    ImportWarningCode,
    ImportWarningSeverity,
)

_IMPORT_NAMESPACE = UUID("bc67bb6c-7883-50ba-9e4f-45816b46dc92")
_WORD_RE = re.compile(r"\b[\w'-]+\b", flags=re.UNICODE)


def _stable_id(document: ParsedDocument, label: str) -> UUID:
    """Create a repeatable ID scoped to content and supplied provenance."""
    identity = (
        f"{document.source_hash}:{document.source_url}:"
        f"{document.fetched_at.isoformat()}:{label}"
    )
    return uuid5(_IMPORT_NAMESPACE, identity)


def _fatal(code: ImportWarningCode, message: str) -> ImportWarning:
    return ImportWarning(
        severity=ImportWarningSeverity.FATAL,
        code=code,
        message=message,
    )


def _response_content_type(headers: dict[str, str]) -> str | None:
    for name, value in headers.items():
        if name.lower() == "content-type":
            return value
    return None


def _word_count(document: ParsedDocument) -> int:
    values: list[str] = []
    for section in document.sections:
        if section.heading is not None:
            values.append(section.heading.text)
        values.extend(paragraph.text for paragraph in section.paragraphs)
        for faq in section.faq_items:
            values.extend((faq.question, faq.answer))
    return sum(len(_WORD_RE.findall(value)) for value in values)


def _sections(document: ParsedDocument) -> list[ContentSection]:
    normalized: list[ContentSection] = []
    heading_order = 0
    for section_order, parsed in enumerate(document.sections):
        heading = None
        if parsed.heading is not None:
            heading = Heading(
                id=_stable_id(document, f"heading:{section_order}"),
                level=parsed.heading.level,
                text=parsed.heading.text,
                order=heading_order,
                anchor=parsed.heading.anchor,
            )
            heading_order += 1
        normalized.append(
            ContentSection(
                id=_stable_id(document, f"section:{section_order}"),
                order=section_order,
                heading=heading,
                paragraphs=[
                    Paragraph(
                        id=_stable_id(
                            document,
                            f"section:{section_order}:paragraph:{order}",
                        ),
                        text=item.text,
                        order=order,
                    )
                    for order, item in enumerate(parsed.paragraphs)
                ],
                images=[
                    Image(
                        id=_stable_id(
                            document,
                            f"section:{section_order}:image:{order}",
                        ),
                        source_url=item.source_url,
                        order=order,
                        alt_text=item.alt_text,
                        caption=item.caption,
                        width=item.width,
                        height=item.height,
                    )
                    for order, item in enumerate(parsed.images)
                ],
                links=[
                    Link(
                        id=_stable_id(
                            document,
                            f"section:{section_order}:link:{order}",
                        ),
                        target_url=item.target_url,
                        link_type=item.link_type,
                        order=order,
                        anchor_text=item.anchor_text,
                        rel=item.rel,
                    )
                    for order, item in enumerate(parsed.links)
                ],
                faq_items=[
                    FAQItem(
                        id=_stable_id(
                            document,
                            f"section:{section_order}:faq:{order}",
                        ),
                        question=item.question,
                        answer=item.answer,
                        order=order,
                    )
                    for order, item in enumerate(parsed.faq_items)
                ],
            )
        )
    return normalized


def _provenance(document: ParsedDocument) -> list[FieldProvenance]:
    records = [
        FieldProvenance(
            field="snapshot.requested_url",
            origin=FieldOrigin.INPUT,
            source="import input",
        ),
        FieldProvenance(
            field="snapshot.captured_at",
            origin=FieldOrigin.INPUT,
            source="import input",
        ),
        FieldProvenance(
            field="source_hash",
            origin=FieldOrigin.DERIVED,
            source="UTF-8 HTML body",
            detail="SHA-256 of the exact in-memory HTML string",
        ),
        FieldProvenance(
            field="article.word_count",
            origin=FieldOrigin.DERIVED,
            source="normalized visible editorial content",
        ),
        FieldProvenance(
            field="article.sections",
            origin=FieldOrigin.NORMALIZED,
            source="visible semantic HTML content",
        ),
    ]
    extracted = {
        "article.title": document.title,
        "article.canonical_url": document.canonical_url,
        "article.language": document.language,
        "article.meta_description": document.meta_description,
        "article.published_at": document.published_at,
        "article.modified_at": document.modified_at,
        "article.schema_markup": document.schema_markup or None,
    }
    records.extend(
        FieldProvenance(
            field=field,
            origin=FieldOrigin.EXTRACTED,
            source="HTML markup",
        )
        for field, value in extracted.items()
        if value is not None
    )
    return records


def normalize_document(
    document: ParsedDocument,
    source_type: ImportSourceType,
) -> ImportResult:
    """Create immutable domain records or a controlled fatal result."""
    warnings = list(document.warnings)
    snapshot = CrawlSnapshot(
        id=_stable_id(document, "crawl-snapshot"),
        requested_url=document.source_url,
        captured_at=document.fetched_at,
        source_system=f"offline_{source_type.value}",
        final_url=document.source_url,
        http_status=document.status_code,
        response_headers=document.headers,
        raw_html=document.html_body,
        response_content_type=_response_content_type(document.headers),
        content_hash=document.source_hash,
        observed_canonical_url=document.canonical_url,
        error_message=(
            "HTTP status was not supplied with the standalone HTML file."
            if document.status_code is None
            else None
        ),
    )

    if not document.title:
        warnings.append(
            _fatal(
                ImportWarningCode.MISSING_TITLE,
                "A title or H1 is required to create an Article.",
            )
        )
    if not document.language:
        warnings.append(
            _fatal(
                ImportWarningCode.MISSING_LANGUAGE,
                "An explicit supported html[lang] value is required.",
            )
        )
    has_body = any(
        section.paragraphs or section.faq_items for section in document.sections
    )
    if not has_body:
        warnings.append(
            _fatal(
                ImportWarningCode.MISSING_ARTICLE_BODY,
                "No usable editorial paragraphs or visible FAQ items were found.",
            )
        )
    if any(item.severity is ImportWarningSeverity.FATAL for item in warnings):
        return ImportResult(
            status=ImportStatus.FAILED,
            source_type=source_type,
            snapshot=snapshot,
            article=None,
            warnings=warnings,
            source_hash=document.source_hash,
            provenance=_provenance(document),
        )

    assert document.title is not None
    assert document.language is not None
    try:
        article = Article(
            id=_stable_id(document, "article"),
            source_snapshot_id=snapshot.id,
            url=document.source_url,
            title=document.title,
            status=ArticleStatus.UNKNOWN,
            content_type=ContentType.OTHER,
            language=document.language,
            normalized_at=document.fetched_at,
            search_intents=[SearchIntent.UNKNOWN],
            canonical_url=document.canonical_url,
            published_at=document.published_at,
            modified_at=document.modified_at,
            source_content_hash=document.source_hash,
            meta_description=document.meta_description,
            word_count=_word_count(document),
            sections=_sections(document),
            schema_markup=[
                SchemaMarkup(
                    id=_stable_id(document, f"schema:{order}"),
                    schema_type=item.schema_type,
                    payload=item.payload,
                )
                for order, item in enumerate(document.schema_markup)
            ],
        )
    except ValidationError as error:
        warnings.append(
            _fatal(
                ImportWarningCode.NORMALIZATION_FAILED,
                f"Normalized content did not satisfy the Article contract: {error}",
            )
        )
        return ImportResult(
            status=ImportStatus.FAILED,
            source_type=source_type,
            snapshot=snapshot,
            article=None,
            warnings=warnings,
            source_hash=document.source_hash,
            provenance=_provenance(document),
        )

    return ImportResult(
        status=ImportStatus.SUCCEEDED,
        source_type=source_type,
        snapshot=snapshot,
        article=article,
        warnings=warnings,
        source_hash=document.source_hash,
        provenance=_provenance(document),
    )


def import_html_file(import_input: HtmlFileInput) -> ImportResult:
    """Import one local UTF-8 HTML file without accessing the network."""
    html_body = import_input.html_path.read_text(encoding="utf-8-sig")
    document = parse_html(
        source_url=import_input.source_url,
        fetched_at=import_input.fetched_at,
        status_code=None,
        headers=import_input.headers,
        html_body=html_body,
    )
    return normalize_document(document, ImportSourceType.HTML_FILE)


def import_json_fixture(import_input: JsonFixtureInput) -> ImportResult:
    """Import an already validated in-memory JSON fixture contract."""
    document = parse_html(
        source_url=import_input.source_url,
        fetched_at=import_input.fetched_at,
        status_code=import_input.status_code,
        headers=import_input.headers,
        html_body=import_input.html_body,
    )
    return normalize_document(document, ImportSourceType.JSON_FIXTURE)
