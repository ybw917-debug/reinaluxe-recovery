from datetime import UTC, datetime
from uuid import uuid4

import pytest

from reinaluxe_recovery.domain import Article, ContentSection, Heading, Paragraph
from reinaluxe_recovery.domain.enums import ArticleStatus, ContentType, SearchIntent
from reinaluxe_recovery.persistence.dto import StoredArticleVersionSummary


@pytest.fixture
def article_version() -> StoredArticleVersionSummary:
    article = Article(
        id=uuid4(),
        source_snapshot_id=uuid4(),
        url="https://example.com/a/",
        canonical_url="https://example.com/a/",
        title="A useful title",
        status=ArticleStatus.PUBLISHED,
        content_type=ContentType.INFORMATIONAL_ARTICLE,
        language="en",
        normalized_at=datetime(2026, 7, 14, tzinfo=UTC),
        search_intents=[SearchIntent.INFORMATIONAL],
        meta_description="short",
        sections=[
            ContentSection(
                order=0,
                heading=Heading(level=1, text="Different heading", order=0),
                paragraphs=[Paragraph(text="Tiny body.", order=0)],
            )
        ],
    )
    return StoredArticleVersionSummary(
        id=uuid4(),
        page_id=uuid4(),
        crawl_id=uuid4(),
        article=article,
        normalized_content_hash="a" * 64,
        version_number=1,
        created_at=datetime(2026, 7, 14, tzinfo=UTC),
    )
