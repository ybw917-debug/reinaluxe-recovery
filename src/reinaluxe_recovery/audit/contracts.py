"""Immutable contracts for deterministic article structure audits."""

from collections import Counter
from enum import StrEnum
from typing import Literal, Self
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator


class AuditModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, validate_default=True)


class AuditRuleCode(StrEnum):
    MISSING_TITLE = "missing_title"
    MISSING_H1 = "missing_h1"
    MULTIPLE_H1 = "multiple_h1"
    HEADING_LEVEL_JUMP = "heading_level_jump"
    EMPTY_HEADING = "empty_heading"
    TITLE_H1_MISMATCH_CANDIDATE = "title_h1_mismatch_candidate"
    MISSING_META_DESCRIPTION = "missing_meta_description"
    META_DESCRIPTION_TOO_SHORT = "meta_description_too_short"
    META_DESCRIPTION_TOO_LONG = "meta_description_too_long"
    EMPTY_PARAGRAPH = "empty_paragraph"
    VERY_SHORT_PARAGRAPH = "very_short_paragraph"
    VERY_LONG_PARAGRAPH = "very_long_paragraph"
    REPEATED_HEADING_TEXT = "repeated_heading_text"
    DUPLICATE_FAQ_QUESTION = "duplicate_faq_question"
    INCOMPLETE_FAQ_ITEM = "incomplete_faq_item"
    IMAGE_MISSING_ALT = "image_missing_alt"
    IMAGE_MISSING_SOURCE = "image_missing_source"
    BROKEN_INTERNAL_LINK_CANDIDATE = "broken_internal_link_candidate"
    MALFORMED_LINK = "malformed_link"
    EXCESSIVE_EXTERNAL_LINKS_CANDIDATE = "excessive_external_links_candidate"
    NO_INTERNAL_LINKS = "no_internal_links"
    MISSING_CANONICAL_URL = "missing_canonical_url"
    CANONICAL_SOURCE_URL_MISMATCH_CANDIDATE = "canonical_source_url_mismatch_candidate"
    MALFORMED_SCHEMA_MARKUP = "malformed_schema_markup"
    SCHEMA_TYPE_CONTENT_MISMATCH_CANDIDATE = "schema_type_content_mismatch_candidate"
    MISSING_ARTICLE_BODY = "missing_article_body"
    UNUSUALLY_LOW_WORD_COUNT = "unusually_low_word_count"
    UNUSUALLY_HIGH_WORD_COUNT = "unusually_high_word_count"
    REPEATED_CTA_CANDIDATE = "repeated_cta_candidate"
    REPEATED_CONCLUSION_CANDIDATE = "repeated_conclusion_candidate"
    TEMPLATE_BLOCK_CANDIDATE = "template_block_candidate"


class AuditSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class AuditStatus(StrEnum):
    COMPLETED = "completed"
    COMPLETED_WITH_ERRORS = "completed_with_errors"


class AuditFinding(AuditModel):
    finding_id: UUID
    rule_code: AuditRuleCode
    severity: AuditSeverity
    article_id: UUID
    article_version_id: UUID
    page_url: str
    message: str
    field_path: str | None = None
    section_id: UUID | None = None
    paragraph_id: UUID | None = None
    heading_id: UUID | None = None
    image_id: UUID | None = None
    link_id: UUID | None = None
    faq_item_id: UUID | None = None
    observed_value: str | int | None = None
    expected_condition: str | None = None
    evidence_refs: tuple[str, ...] = Field(min_length=1)
    created_at: AwareDatetime


class ArticleStructureAuditResult(AuditModel):
    contract_version: Literal["1.0"] = "1.0"
    article_id: UUID
    article_version_id: UUID
    page_url: str
    audited_at: AwareDatetime
    rule_set_version: str
    findings: tuple[AuditFinding, ...] = ()
    finding_count: int = 0
    severity_counts: dict[AuditSeverity, int] = Field(default_factory=dict)
    rule_counts: dict[AuditRuleCode, int] = Field(default_factory=dict)
    audited_fields: tuple[str, ...]
    audit_status: AuditStatus = AuditStatus.COMPLETED

    @model_validator(mode="after")
    def derive_counts(self) -> Self:
        severity = dict(Counter(item.severity for item in self.findings))
        rules = dict(Counter(item.rule_code for item in self.findings))
        status = (
            AuditStatus.COMPLETED_WITH_ERRORS
            if AuditSeverity.ERROR in severity
            else AuditStatus.COMPLETED
        )
        object.__setattr__(self, "finding_count", len(self.findings))
        object.__setattr__(self, "severity_counts", severity)
        object.__setattr__(self, "rule_counts", rules)
        object.__setattr__(self, "audit_status", status)
        return self


class SiteStructureAuditResult(AuditModel):
    contract_version: Literal["1.0"] = "1.0"
    audited_at: AwareDatetime
    rule_set_version: str
    page_count: int = 0
    article_version_count: int = 0
    total_findings: int = 0
    severity_counts: dict[AuditSeverity, int] = Field(default_factory=dict)
    rule_counts: dict[AuditRuleCode, int] = Field(default_factory=dict)
    article_results: tuple[ArticleStructureAuditResult, ...] = ()
    overall_status: AuditStatus = AuditStatus.COMPLETED

    @model_validator(mode="after")
    def derive_counts(self) -> Self:
        findings = [f for result in self.article_results for f in result.findings]
        object.__setattr__(
            self, "page_count", len({r.page_url for r in self.article_results})
        )
        object.__setattr__(self, "article_version_count", len(self.article_results))
        object.__setattr__(self, "total_findings", len(findings))
        severity = dict(Counter(item.severity for item in findings))
        object.__setattr__(self, "severity_counts", severity)
        object.__setattr__(
            self, "rule_counts", dict(Counter(f.rule_code for f in findings))
        )
        object.__setattr__(
            self,
            "overall_status",
            AuditStatus.COMPLETED_WITH_ERRORS
            if AuditSeverity.ERROR in severity
            else AuditStatus.COMPLETED,
        )
        return self


class AuditOptions(AuditModel):
    include_info: bool = True
    rule_codes: frozenset[AuditRuleCode] | None = None
    latest_only: bool = True
    page_urls: tuple[str, ...] | None = None
    limit: int | None = Field(default=None, ge=1)
    fail_on_error_severity: bool = False


class AuditRuleConfiguration(AuditModel):
    meta_description_min_chars: int = Field(default=70, ge=1)
    meta_description_max_chars: int = Field(default=160, ge=1)
    short_paragraph_max_words: int = Field(default=5, ge=1)
    long_paragraph_min_words: int = Field(default=200, ge=2)
    low_article_word_count: int = Field(default=300, ge=1)
    high_article_word_count: int = Field(default=5000, ge=2)
    excessive_external_links: int = Field(default=25, ge=1)


DEFAULT_RULE_CONFIGURATION = AuditRuleConfiguration()
RULE_SET_VERSION = "1.0"
