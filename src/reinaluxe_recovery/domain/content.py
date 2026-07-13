"""Normalized content models for the Content Audit domain."""

from typing import Annotated, Literal, Self
from uuid import UUID, uuid4

from pydantic import (
    AwareDatetime,
    Field,
    HttpUrl,
    JsonValue,
    StringConstraints,
    model_validator,
)

from reinaluxe_recovery.domain.base import DomainModel, NonEmptyText, Sha256Digest
from reinaluxe_recovery.domain.enums import (
    ArticleStatus,
    ContentType,
    LinkType,
    SchemaType,
    SearchIntent,
)

LanguageCode = Annotated[
    str,
    StringConstraints(pattern=r"^[a-z]{2}(?:-[A-Z]{2})?$"),
]


class Heading(DomainModel):
    """Ordered heading extracted from an article."""

    id: UUID = Field(default_factory=uuid4)
    level: int = Field(ge=1, le=6)
    text: NonEmptyText
    order: int = Field(ge=0)
    anchor: str | None = Field(default=None, max_length=200)


class Paragraph(DomainModel):
    """Normalized paragraph with optional source offsets."""

    id: UUID = Field(default_factory=uuid4)
    text: NonEmptyText
    order: int = Field(ge=0)
    source_start_offset: int | None = Field(default=None, ge=0)
    source_end_offset: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_offsets(self) -> Self:
        """Require source offsets to be complete and ordered."""
        start = self.source_start_offset
        end = self.source_end_offset
        if (start is None) != (end is None):
            raise ValueError("source offsets must be provided together")
        if start is not None and end is not None and end < start:
            raise ValueError("source_end_offset must not precede source_start_offset")
        return self


class Image(DomainModel):
    """Image reference observed in normalized article content."""

    id: UUID = Field(default_factory=uuid4)
    source_url: HttpUrl
    order: int = Field(ge=0)
    alt_text: str | None = Field(default=None, max_length=500)
    caption: str | None = Field(default=None, max_length=1_000)
    width: int | None = Field(default=None, gt=0)
    height: int | None = Field(default=None, gt=0)


class Link(DomainModel):
    """Link observed in normalized article content."""

    id: UUID = Field(default_factory=uuid4)
    target_url: HttpUrl
    link_type: LinkType
    order: int = Field(ge=0)
    anchor_text: str | None = Field(default=None, max_length=500)
    rel: list[str] = Field(default_factory=list)


class SchemaMarkup(DomainModel):
    """Structured-data payload preserved independently of its validation state."""

    id: UUID = Field(default_factory=uuid4)
    schema_type: SchemaType
    payload: dict[str, JsonValue]
    source_section_id: UUID | None = None
    validation_errors: list[str] = Field(default_factory=list)


class FAQItem(DomainModel):
    """Question-and-answer pair found in source content."""

    id: UUID = Field(default_factory=uuid4)
    question: NonEmptyText
    answer: NonEmptyText
    order: int = Field(ge=0)


class EntityMention(DomainModel):
    """Named entity mention preserved with its source context."""

    id: UUID = Field(default_factory=uuid4)
    name: NonEmptyText
    entity_type: str | None = Field(default=None, max_length=100)
    source_text: str | None = Field(default=None, max_length=1_000)
    source_section_id: UUID | None = None
    evidence_reference_ids: list[UUID] = Field(default_factory=list)


class Topic(DomainModel):
    """Stable editorial topic used to classify articles."""

    id: UUID = Field(default_factory=uuid4)
    name: NonEmptyText
    description: str | None = Field(default=None, max_length=2_000)
    parent_topic_id: UUID | None = None
    aliases: list[str] = Field(default_factory=list)


class TopicCluster(DomainModel):
    """Related topics and articles organized around a primary topic."""

    id: UUID = Field(default_factory=uuid4)
    name: NonEmptyText
    primary_topic_id: UUID
    topic_ids: list[UUID] = Field(min_length=1)
    article_ids: list[UUID] = Field(default_factory=list)
    description: str | None = Field(default=None, max_length=2_000)

    @model_validator(mode="after")
    def validate_topic_ids(self) -> Self:
        """Require unique topics and inclusion of the primary topic."""
        if len(self.topic_ids) != len(set(self.topic_ids)):
            raise ValueError("topic_ids must be unique")
        if self.primary_topic_id not in self.topic_ids:
            raise ValueError("primary_topic_id must be included in topic_ids")
        return self


class ContentSection(DomainModel):
    """Ordered normalized section containing typed content components."""

    id: UUID = Field(default_factory=uuid4)
    order: int = Field(ge=0)
    heading: Heading | None = None
    paragraphs: list[Paragraph] = Field(default_factory=list)
    images: list[Image] = Field(default_factory=list)
    links: list[Link] = Field(default_factory=list)
    faq_items: list[FAQItem] = Field(default_factory=list)
    entity_mentions: list[EntityMention] = Field(default_factory=list)


class Article(DomainModel):
    """Normalized article record derived from a raw crawl snapshot."""

    contract_version: Literal["1.0"] = "1.0"
    id: UUID = Field(default_factory=uuid4)
    source_snapshot_id: UUID
    url: HttpUrl
    title: NonEmptyText
    status: ArticleStatus
    content_type: ContentType
    language: LanguageCode
    normalized_at: AwareDatetime
    search_intents: list[SearchIntent] = Field(min_length=1)
    canonical_url: HttpUrl | None = None
    published_at: AwareDatetime | None = None
    modified_at: AwareDatetime | None = None
    source_content_hash: Sha256Digest | None = None
    meta_description: str | None = Field(default=None, max_length=500)
    word_count: int | None = Field(default=None, ge=0)
    sections: list[ContentSection] = Field(default_factory=list)
    schema_markup: list[SchemaMarkup] = Field(default_factory=list)
    topic_ids: list[UUID] = Field(default_factory=list)
    topic_cluster_ids: list[UUID] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_article(self) -> Self:
        """Validate lifecycle-sensitive content and ordered relationships."""
        if (
            self.status in {ArticleStatus.DRAFT, ArticleStatus.PUBLISHED}
            and not self.sections
        ):
            raise ValueError(
                "draft and published articles require at least one section"
            )
        if (
            self.published_at is not None
            and self.modified_at is not None
            and self.modified_at < self.published_at
        ):
            raise ValueError("modified_at must not precede published_at")

        section_ids = [section.id for section in self.sections]
        section_orders = [section.order for section in self.sections]
        if len(section_ids) != len(set(section_ids)):
            raise ValueError("section IDs must be unique")
        if len(section_orders) != len(set(section_orders)):
            raise ValueError("section order values must be unique")
        if len(self.search_intents) != len(set(self.search_intents)):
            raise ValueError("search_intents must be unique")
        return self
