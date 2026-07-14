"""Transparent, local-only structure rules over normalized Article data."""

from __future__ import annotations

import re
from collections import Counter
from datetime import datetime
from typing import Any
from urllib.parse import urlsplit
from uuid import NAMESPACE_URL, UUID, uuid5

from reinaluxe_recovery.audit.contracts import (
    DEFAULT_RULE_CONFIGURATION,
    AuditFinding,
    AuditRuleCode,
    AuditRuleConfiguration,
    AuditSeverity,
)
from reinaluxe_recovery.domain import Article
from reinaluxe_recovery.domain.enums import LinkType, SchemaType
from reinaluxe_recovery.persistence.url_normalization import normalize_page_url


def normalize_text(value: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (value or "").casefold()).strip()


def _words(value: str) -> int:
    return len(re.findall(r"\b[\w'-]+\b", value, flags=re.UNICODE))


def audit_rules(
    article: Article,
    article_version_id: UUID,
    page_inventory: frozenset[str],
    created_at: datetime,
    config: AuditRuleConfiguration = DEFAULT_RULE_CONFIGURATION,
) -> list[AuditFinding]:
    findings: list[AuditFinding] = []

    def add(
        code: AuditRuleCode,
        severity: AuditSeverity,
        message: str,
        path: str,
        **evidence: Any,
    ) -> None:
        position = str(
            evidence.get("paragraph_id")
            or evidence.get("heading_id")
            or evidence.get("image_id")
            or evidence.get("link_id")
            or evidence.get("faq_item_id")
            or path
        )
        findings.append(
            AuditFinding(
                finding_id=uuid5(
                    NAMESPACE_URL, f"{article_version_id}:{code}:{position}"
                ),
                rule_code=code,
                severity=severity,
                article_id=article.id,
                article_version_id=article_version_id,
                page_url=str(article.url),
                message=message,
                field_path=path,
                evidence_refs=(path,),
                created_at=created_at,
                **evidence,
            )
        )

    title = str(article.title).strip()
    if not title:
        add(
            AuditRuleCode.MISSING_TITLE,
            AuditSeverity.ERROR,
            "Article title is blank.",
            "title",
            expected_condition="A non-blank normalized title",
        )
    headings = [
        (s, s.heading)
        for s in sorted(article.sections, key=lambda x: x.order)
        if s.heading is not None
    ]
    h1s = [(s, h) for s, h in headings if h.level == 1]
    if not h1s:
        add(
            AuditRuleCode.MISSING_H1,
            AuditSeverity.WARNING,
            "No H1 heading is present.",
            "sections",
            observed_value=0,
            expected_condition="Exactly one H1",
        )
    elif len(h1s) > 1:
        add(
            AuditRuleCode.MULTIPLE_H1,
            AuditSeverity.WARNING,
            "More than one H1 heading is present.",
            "sections",
            observed_value=len(h1s),
            expected_condition="Exactly one H1",
        )
    if len(h1s) == 1 and normalize_text(title) != normalize_text(str(h1s[0][1].text)):
        add(
            AuditRuleCode.TITLE_H1_MISMATCH_CANDIDATE,
            AuditSeverity.INFO,
            "Title and H1 differ after lowercase alphanumeric normalization.",
            "title",
            heading_id=h1s[0][1].id,
            observed_value=str(h1s[0][1].text),
            expected_condition=title,
        )
    previous = None
    heading_texts: Counter[str] = Counter()
    for section, heading in headings:
        text = str(heading.text).strip()
        path = f"sections[{section.order}].heading"
        if not text:
            add(
                AuditRuleCode.EMPTY_HEADING,
                AuditSeverity.ERROR,
                "Heading text is blank.",
                path,
                section_id=section.id,
                heading_id=heading.id,
            )
        normalized = normalize_text(text)
        heading_texts[normalized] += 1
        if previous is not None and heading.level > previous + 1:
            add(
                AuditRuleCode.HEADING_LEVEL_JUMP,
                AuditSeverity.WARNING,
                f"Heading level jumps from H{previous} to H{heading.level}.",
                path,
                section_id=section.id,
                heading_id=heading.id,
                observed_value=heading.level,
                expected_condition=f"At most H{previous + 1}",
            )
        previous = heading.level
    for section, heading in headings:
        if (
            normalize_text(str(heading.text))
            and heading_texts[normalize_text(str(heading.text))] > 1
        ):
            add(
                AuditRuleCode.REPEATED_HEADING_TEXT,
                AuditSeverity.WARNING,
                "Identical normalized heading text repeats in this article.",
                f"sections[{section.order}].heading.text",
                section_id=section.id,
                heading_id=heading.id,
                observed_value=str(heading.text),
            )

    meta = (article.meta_description or "").strip()
    if not meta:
        add(
            AuditRuleCode.MISSING_META_DESCRIPTION,
            AuditSeverity.WARNING,
            "Meta description is missing or blank.",
            "meta_description",
            expected_condition="A non-blank description",
        )
    elif len(meta) < config.meta_description_min_chars:
        add(
            AuditRuleCode.META_DESCRIPTION_TOO_SHORT,
            AuditSeverity.INFO,
            "Meta description is below the configured audit threshold.",
            "meta_description",
            observed_value=len(meta),
            expected_condition=f">= {config.meta_description_min_chars} characters",
        )
    elif len(meta) > config.meta_description_max_chars:
        add(
            AuditRuleCode.META_DESCRIPTION_TOO_LONG,
            AuditSeverity.INFO,
            "Meta description exceeds the configured audit threshold.",
            "meta_description",
            observed_value=len(meta),
            expected_condition=f"<= {config.meta_description_max_chars} characters",
        )
    if article.canonical_url is None:
        add(
            AuditRuleCode.MISSING_CANONICAL_URL,
            AuditSeverity.WARNING,
            "Canonical URL is missing.",
            "canonical_url",
            expected_condition="An explicit HTTP(S) canonical URL",
        )
    elif normalize_page_url(str(article.canonical_url)) != normalize_page_url(
        str(article.url)
    ):
        add(
            AuditRuleCode.CANONICAL_SOURCE_URL_MISMATCH_CANDIDATE,
            AuditSeverity.INFO,
            "Canonical and source URLs differ after deterministic URL normalization.",
            "canonical_url",
            observed_value=str(article.canonical_url),
            expected_condition=normalize_page_url(str(article.url)),
        )

    paragraphs = [
        (s, p)
        for s in article.sections
        for p in sorted(s.paragraphs, key=lambda x: x.order)
    ]
    usable = [p for _, p in paragraphs if str(p.text).strip()]
    if not usable:
        add(
            AuditRuleCode.MISSING_ARTICLE_BODY,
            AuditSeverity.ERROR,
            "No usable normalized paragraph body is present.",
            "sections",
            expected_condition="At least one non-blank paragraph",
        )
    block_counts = Counter(normalize_text(str(p.text)) for p in usable)
    cta_counts = Counter(
        normalize_text(str(p.text))
        for p in usable
        if re.search(
            r"\b(click|buy|shop|subscribe|contact|learn more)\b", str(p.text), re.I
        )
    )
    conclusion_counts = Counter(
        normalize_text(str(p.text))
        for p in usable
        if re.match(
            r"\s*(in conclusion|to conclude|in summary|to summarize)\b",
            str(p.text),
            re.I,
        )
    )
    for section, paragraph in paragraphs:
        text = str(paragraph.text).strip()
        count = _words(text)
        path = f"sections[{section.order}].paragraphs[{paragraph.order}].text"
        common = {
            "section_id": section.id,
            "paragraph_id": paragraph.id,
            "observed_value": count,
        }
        if not text:
            add(
                AuditRuleCode.EMPTY_PARAGRAPH,
                AuditSeverity.WARNING,
                "Paragraph is blank.",
                path,
                **common,
            )
        elif count <= config.short_paragraph_max_words:
            add(
                AuditRuleCode.VERY_SHORT_PARAGRAPH,
                AuditSeverity.INFO,
                "Paragraph is at or below the configured short threshold.",
                path,
                expected_condition=f"> {config.short_paragraph_max_words} words",
                **common,
            )
        elif count >= config.long_paragraph_min_words:
            add(
                AuditRuleCode.VERY_LONG_PARAGRAPH,
                AuditSeverity.INFO,
                "Paragraph is at or above the configured long threshold.",
                path,
                expected_condition=f"< {config.long_paragraph_min_words} words",
                **common,
            )
        normalized = normalize_text(text)
        if normalized and block_counts[normalized] > 1:
            add(
                AuditRuleCode.TEMPLATE_BLOCK_CANDIDATE,
                AuditSeverity.INFO,
                "Identical normalized paragraph text repeats within this article.",
                path,
                section_id=section.id,
                paragraph_id=paragraph.id,
                observed_value=text,
            )
        if normalized and cta_counts[normalized] > 1:
            add(
                AuditRuleCode.REPEATED_CTA_CANDIDATE,
                AuditSeverity.INFO,
                "Identical action-language paragraph repeats within this article.",
                path,
                section_id=section.id,
                paragraph_id=paragraph.id,
                observed_value=text,
            )
        if normalized and conclusion_counts[normalized] > 1:
            add(
                AuditRuleCode.REPEATED_CONCLUSION_CANDIDATE,
                AuditSeverity.INFO,
                "Identical conclusion-prefixed paragraph repeats within this article.",
                path,
                section_id=section.id,
                paragraph_id=paragraph.id,
                observed_value=text,
            )
    word_count = sum(_words(str(p.text)) for p in usable)
    if word_count < config.low_article_word_count:
        add(
            AuditRuleCode.UNUSUALLY_LOW_WORD_COUNT,
            AuditSeverity.INFO,
            "Derived body word count is below the configured audit threshold.",
            "sections",
            observed_value=word_count,
            expected_condition=f">= {config.low_article_word_count} words",
        )
    elif word_count > config.high_article_word_count:
        add(
            AuditRuleCode.UNUSUALLY_HIGH_WORD_COUNT,
            AuditSeverity.INFO,
            "Derived body word count exceeds the configured audit threshold.",
            "sections",
            observed_value=word_count,
            expected_condition=f"<= {config.high_article_word_count} words",
        )

    links = [(s, link) for s in article.sections for link in s.links]
    internal = [(s, link) for s, link in links if link.link_type is LinkType.INTERNAL]
    external = [
        (s, link)
        for s, link in links
        if link.link_type in {LinkType.EXTERNAL, LinkType.AFFILIATE}
    ]
    if not internal:
        add(
            AuditRuleCode.NO_INTERNAL_LINKS,
            AuditSeverity.INFO,
            "No link classified as internal is present.",
            "sections",
            observed_value=0,
        )
    if len(external) > config.excessive_external_links:
        add(
            AuditRuleCode.EXCESSIVE_EXTERNAL_LINKS_CANDIDATE,
            AuditSeverity.INFO,
            "External-link count exceeds the configured audit threshold.",
            "sections",
            observed_value=len(external),
            expected_condition=f"<= {config.excessive_external_links} links",
        )
    for section, link in links:
        target = str(link.target_url)
        path = f"sections[{section.order}].links[{link.order}].target_url"
        parts = urlsplit(target)
        if parts.scheme not in {"http", "https"} or not parts.netloc:
            add(
                AuditRuleCode.MALFORMED_LINK,
                AuditSeverity.ERROR,
                "Link is not an absolute HTTP(S) URL.",
                path,
                section_id=section.id,
                link_id=link.id,
                observed_value=target,
            )
        elif (
            link.link_type is LinkType.INTERNAL
            and normalize_page_url(target) not in page_inventory
        ):
            add(
                AuditRuleCode.BROKEN_INTERNAL_LINK_CANDIDATE,
                AuditSeverity.WARNING,
                "Internal target is absent from the local persisted page inventory; no network check was made.",
                path,
                section_id=section.id,
                link_id=link.id,
                observed_value=target,
            )
    for section in article.sections:
        for image in section.images:
            path = f"sections[{section.order}].images[{image.order}]"
            if not str(image.source_url).strip():
                add(
                    AuditRuleCode.IMAGE_MISSING_SOURCE,
                    AuditSeverity.ERROR,
                    "Image source is missing.",
                    f"{path}.source_url",
                    section_id=section.id,
                    image_id=image.id,
                )
            if not (image.alt_text or "").strip():
                add(
                    AuditRuleCode.IMAGE_MISSING_ALT,
                    AuditSeverity.WARNING,
                    "Image alt text is missing or blank.",
                    f"{path}.alt_text",
                    section_id=section.id,
                    image_id=image.id,
                )
        questions = Counter(normalize_text(str(f.question)) for f in section.faq_items)
        for faq in section.faq_items:
            path = f"sections[{section.order}].faq_items[{faq.order}]"
            if not str(faq.question).strip() or not str(faq.answer).strip():
                add(
                    AuditRuleCode.INCOMPLETE_FAQ_ITEM,
                    AuditSeverity.ERROR,
                    "FAQ question or answer is blank.",
                    path,
                    section_id=section.id,
                    faq_item_id=faq.id,
                )
            if questions[normalize_text(str(faq.question))] > 1:
                add(
                    AuditRuleCode.DUPLICATE_FAQ_QUESTION,
                    AuditSeverity.WARNING,
                    "Identical normalized FAQ question repeats.",
                    f"{path}.question",
                    section_id=section.id,
                    faq_item_id=faq.id,
                    observed_value=str(faq.question),
                )
    has_faq = any(s.faq_items for s in article.sections)
    for index, schema in enumerate(article.schema_markup):
        path = f"schema_markup[{index}]"
        if (
            schema.validation_errors
            or not isinstance(schema.payload, dict)
            or not schema.payload
        ):
            add(
                AuditRuleCode.MALFORMED_SCHEMA_MARKUP,
                AuditSeverity.WARNING,
                "Schema payload is empty or carries normalized validation errors.",
                path,
                observed_value=len(schema.validation_errors),
            )
        if schema.schema_type is SchemaType.FAQ_PAGE and not has_faq:
            add(
                AuditRuleCode.SCHEMA_TYPE_CONTENT_MISMATCH_CANDIDATE,
                AuditSeverity.INFO,
                "FAQ schema exists but no visible normalized FAQ items are present.",
                path,
            )
    return findings
