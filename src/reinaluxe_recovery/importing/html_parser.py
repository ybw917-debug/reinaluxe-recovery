"""Deterministic BeautifulSoup parser for owner-provided offline HTML."""

from __future__ import annotations

import json
import re
from datetime import datetime
from hashlib import sha256
from typing import Any
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup, Tag
from pydantic import HttpUrl, TypeAdapter, ValidationError

from reinaluxe_recovery.domain.enums import LinkType, SchemaType
from reinaluxe_recovery.importing.contracts import (
    ParsedDocument,
    ParsedFAQItem,
    ParsedHeading,
    ParsedImage,
    ParsedLink,
    ParsedParagraph,
    ParsedSchemaMarkup,
    ParsedSection,
)
from reinaluxe_recovery.importing.warnings import (
    ImportWarning,
    ImportWarningCode,
    ImportWarningSeverity,
)

_HTTP_URL = TypeAdapter(HttpUrl)
_LANGUAGE_RE = re.compile(r"^[a-z]{2}(?:-[A-Z]{2})?$")
_SCHEMA_TYPES = {
    "article": SchemaType.ARTICLE,
    "faqpage": SchemaType.FAQ_PAGE,
    "breadcrumblist": SchemaType.BREADCRUMB_LIST,
    "product": SchemaType.PRODUCT,
    "organization": SchemaType.ORGANIZATION,
    "website": SchemaType.WEBSITE,
}


def _text(value: str) -> str:
    """Collapse all HTML whitespace to a single ASCII space."""
    return re.sub(r"\s+", " ", value).strip()


def _attribute(tag: Tag, name: str) -> str | None:
    """Return a scalar HTML attribute without guessing from list values."""
    value = tag.get(name)
    if isinstance(value, str):
        normalized = _text(value)
        return normalized or None
    return None


def _warning(
    code: ImportWarningCode,
    message: str,
    location: str | None = None,
) -> ImportWarning:
    return ImportWarning(
        severity=ImportWarningSeverity.WARNING,
        code=code,
        message=message,
        location=location,
    )


def _resolve_url(
    value: str | None,
    source_url: str,
    warnings: list[ImportWarning],
    location: str,
    code: ImportWarningCode = ImportWarningCode.INVALID_RESOURCE_URL,
) -> HttpUrl | None:
    if not value:
        return None
    resolved = urljoin(source_url, value)
    try:
        return _HTTP_URL.validate_python(resolved)
    except ValidationError:
        warnings.append(
            _warning(code, f"Ignored non-HTTP or invalid URL: {value}", location)
        )
        return None


def _parse_datetime(
    value: str | None,
    warnings: list[ImportWarning],
    location: str,
) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        warnings.append(_warning(ImportWarningCode.INVALID_DATE, value, location))
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        warnings.append(
            _warning(
                ImportWarningCode.INVALID_DATE,
                f"Ignored timezone-naive datetime: {value}",
                location,
            )
        )
        return None
    return parsed


def _meta_content(soup: BeautifulSoup, keys: set[str]) -> str | None:
    for tag in soup.find_all("meta"):
        if not isinstance(tag, Tag):
            continue
        key = (_attribute(tag, "property") or _attribute(tag, "name") or "").lower()
        if key in keys:
            return _attribute(tag, "content")
    return None


def _date_value(soup: BeautifulSoup, kind: str) -> str | None:
    meta_keys = {
        "published": {"article:published_time", "datepublished"},
        "modified": {"article:modified_time", "datemodified"},
    }[kind]
    value = _meta_content(soup, meta_keys)
    if value:
        return value
    itemprop = "datePublished" if kind == "published" else "dateModified"
    tag = soup.select_one(f'[itemprop="{itemprop}"]')
    if isinstance(tag, Tag):
        return _attribute(tag, "datetime") or _attribute(tag, "content")
    return None


def _schema_type(payload: dict[str, Any]) -> SchemaType:
    raw_type = payload.get("@type")
    if isinstance(raw_type, list):
        raw_type = next((item for item in raw_type if isinstance(item, str)), None)
    if isinstance(raw_type, str):
        return _SCHEMA_TYPES.get(raw_type.lower(), SchemaType.OTHER)
    return SchemaType.OTHER


def _parse_schema(
    soup: BeautifulSoup,
    warnings: list[ImportWarning],
) -> list[ParsedSchemaMarkup]:
    schemas: list[ParsedSchemaMarkup] = []
    for index, script in enumerate(soup.find_all("script")):
        if not isinstance(script, Tag):
            continue
        script_type = (_attribute(script, "type") or "").lower().split(";", 1)[0]
        if script_type != "application/ld+json":
            continue
        raw = script.string or script.get_text()
        try:
            decoded: Any = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            warnings.append(
                _warning(
                    ImportWarningCode.MALFORMED_JSON_LD,
                    "Ignored malformed JSON-LD block.",
                    f"script[{index}]",
                )
            )
            continue
        payloads = decoded if isinstance(decoded, list) else [decoded]
        for payload in payloads:
            if not isinstance(payload, dict):
                warnings.append(
                    _warning(
                        ImportWarningCode.UNSUPPORTED_JSON_LD,
                        "Ignored JSON-LD value that is not an object.",
                        f"script[{index}]",
                    )
                )
                continue
            schemas.append(
                ParsedSchemaMarkup(
                    schema_type=_schema_type(payload),
                    payload=payload,
                )
            )
    return schemas


def _canonical_url(
    soup: BeautifulSoup,
    source_url: str,
    warnings: list[ImportWarning],
) -> HttpUrl | None:
    for tag in soup.find_all("link"):
        if not isinstance(tag, Tag):
            continue
        rel = tag.get("rel")
        values = rel if isinstance(rel, list) else [rel]
        if any(
            isinstance(value, str) and value.lower() == "canonical" for value in values
        ):
            return _resolve_url(
                _attribute(tag, "href"),
                source_url,
                warnings,
                "link[rel=canonical]",
                ImportWarningCode.INVALID_CANONICAL_URL,
            )
    return None


def _link_type(target: HttpUrl, source: HttpUrl) -> LinkType:
    target_parts = urlsplit(str(target))
    source_parts = urlsplit(str(source))
    if target_parts.hostname and target_parts.hostname == source_parts.hostname:
        return LinkType.INTERNAL
    return LinkType.EXTERNAL


def _positive_int(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        parsed = int(value)
    except ValueError:
        return None
    return parsed if parsed > 0 else None


def _visible_faq(tag: Tag) -> ParsedFAQItem | None:
    summary = tag.find("summary")
    if not isinstance(summary, Tag):
        return None
    question = _text(summary.get_text(" ", strip=True))
    clone = BeautifulSoup(str(tag), "html.parser")
    clone_summary = clone.find("summary")
    if clone_summary is not None:
        clone_summary.decompose()
    answer = _text(clone.get_text(" ", strip=True))
    if not question or not answer:
        return None
    return ParsedFAQItem(question=question, answer=answer)


def _new_section(heading: ParsedHeading | None = None) -> ParsedSection:
    return ParsedSection(heading=heading)


def _parse_sections(
    selected: Tag,
    source_url: HttpUrl,
    warnings: list[ImportWarning],
) -> list[ParsedSection]:
    content = BeautifulSoup(str(selected), "html.parser")
    for unwanted in content.select(
        "script, style, noscript, template, nav, footer, aside, "
        "[role='navigation'], [role='contentinfo'], [aria-hidden='true'], "
        ".cookie-banner, [role='dialog'][aria-label*='cookie' i]"
    ):
        unwanted.decompose()

    sections: list[ParsedSection] = []
    current = _new_section()
    source_text = str(source_url)
    for element in content.find_all(["h1", "h2", "h3", "p", "img", "a", "details"]):
        if not isinstance(element, Tag):
            continue
        if element.name != "details" and element.find_parent("details") is not None:
            continue
        if element.name in {"h1", "h2", "h3"}:
            if current.heading is not None or any(
                (current.paragraphs, current.images, current.links, current.faq_items)
            ):
                sections.append(current)
            heading_text = _text(element.get_text(" ", strip=True))
            current = _new_section(
                ParsedHeading(
                    level=int(element.name[1]),
                    text=heading_text,
                    anchor=_attribute(element, "id"),
                )
                if heading_text
                else None
            )
        elif element.name == "p":
            paragraph_text = _text(element.get_text(" ", strip=True))
            if paragraph_text:
                current.paragraphs.append(ParsedParagraph(text=paragraph_text))
        elif element.name == "img":
            image_url = _resolve_url(
                _attribute(element, "src"),
                source_text,
                warnings,
                "img[src]",
            )
            if image_url is None:
                continue
            figure = element.find_parent("figure")
            figcaption = figure.find("figcaption") if isinstance(figure, Tag) else None
            caption = (
                _text(figcaption.get_text(" ", strip=True))
                if isinstance(figcaption, Tag)
                else None
            )
            current.images.append(
                ParsedImage(
                    source_url=image_url,
                    alt_text=_attribute(element, "alt"),
                    caption=caption or None,
                    width=_positive_int(_attribute(element, "width")),
                    height=_positive_int(_attribute(element, "height")),
                )
            )
        elif element.name == "a":
            target = _resolve_url(
                _attribute(element, "href"),
                source_text,
                warnings,
                "a[href]",
            )
            if target is None:
                continue
            anchor_text = _text(element.get_text(" ", strip=True)) or None
            rel_value = element.get("rel")
            rel = (
                [str(item) for item in rel_value] if isinstance(rel_value, list) else []
            )
            current.links.append(
                ParsedLink(
                    target_url=target,
                    link_type=_link_type(target, source_url),
                    anchor_text=anchor_text,
                    rel=rel,
                )
            )
        else:
            faq = _visible_faq(element)
            if faq is None:
                warnings.append(
                    _warning(
                        ImportWarningCode.INCOMPLETE_FAQ,
                        "Ignored visible FAQ block without both question and answer.",
                        "details",
                    )
                )
            else:
                current.faq_items.append(faq)

    if current.heading is not None or any(
        (current.paragraphs, current.images, current.links, current.faq_items)
    ):
        sections.append(current)
    return sections


def parse_html(
    *,
    source_url: HttpUrl,
    fetched_at: datetime,
    status_code: int | None,
    headers: dict[str, str],
    html_body: str,
) -> ParsedDocument:
    """Parse one in-memory HTML observation without any network access."""
    warnings: list[ImportWarning] = []
    soup = BeautifulSoup(html_body, "html.parser")
    selected = soup.find("article") or soup.find("main") or soup.body
    sections = (
        _parse_sections(selected, source_url, warnings)
        if isinstance(selected, Tag)
        else []
    )
    h1_tag = selected.find("h1") if isinstance(selected, Tag) else None
    h1 = _text(h1_tag.get_text(" ", strip=True)) if isinstance(h1_tag, Tag) else None
    title_tag = soup.find("title")
    title = (
        _text(title_tag.get_text(" ", strip=True))
        if isinstance(title_tag, Tag)
        else None
    ) or h1
    html_tag = soup.find("html")
    language = _attribute(html_tag, "lang") if isinstance(html_tag, Tag) else None
    if language and not _LANGUAGE_RE.fullmatch(language):
        warnings.append(
            _warning(
                ImportWarningCode.INVALID_LANGUAGE,
                f"Ignored unsupported language code: {language}",
                "html[lang]",
            )
        )
        language = None

    return ParsedDocument(
        source_url=source_url,
        fetched_at=fetched_at,
        status_code=status_code,
        headers=headers,
        html_body=html_body,
        source_hash=sha256(html_body.encode("utf-8")).hexdigest(),
        canonical_url=_canonical_url(soup, str(source_url), warnings),
        title=title,
        h1=h1,
        language=language,
        meta_description=_meta_content(soup, {"description", "og:description"}),
        published_at=_parse_datetime(
            _date_value(soup, "published"), warnings, "datePublished"
        ),
        modified_at=_parse_datetime(
            _date_value(soup, "modified"), warnings, "dateModified"
        ),
        sections=sections,
        schema_markup=_parse_schema(soup, warnings),
        warnings=warnings,
    )
