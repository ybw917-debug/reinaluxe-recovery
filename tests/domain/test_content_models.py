"""Tests for normalized article contracts."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from reinaluxe_recovery.domain import (
    Article,
    ArticleStatus,
    ContentSection,
    ContentType,
    Heading,
    Paragraph,
    SearchIntent,
)


def _valid_article_data() -> dict[str, object]:
    section = ContentSection(
        order=0,
        heading=Heading(level=2, text="Craftsmanship details", order=0),
        paragraphs=[Paragraph(text="Observable construction details.", order=0)],
    )
    return {
        "source_snapshot_id": uuid4(),
        "url": "https://reinaluxe.co/craftsmanship-guide/",
        "title": "Craftsmanship Guide",
        "status": ArticleStatus.PUBLISHED,
        "content_type": ContentType.CRAFTSMANSHIP_GUIDE,
        "language": "en",
        "normalized_at": datetime(2026, 7, 14, 10, 0, tzinfo=UTC),
        "search_intents": [SearchIntent.INFORMATIONAL],
        "sections": [section],
    }


def test_valid_article_creation() -> None:
    """A complete normalized article is accepted."""
    article = Article.model_validate(_valid_article_data())

    assert str(article.url) == "https://reinaluxe.co/craftsmanship-guide/"
    assert article.sections[0].heading is not None


def test_invalid_article_url_is_rejected() -> None:
    """Article URLs must use a valid HTTP or HTTPS URL."""
    data = _valid_article_data()
    data["url"] = "not-a-url"

    with pytest.raises(ValidationError):
        Article.model_validate(data)


def test_naive_article_datetime_is_rejected() -> None:
    """Domain timestamps must contain an explicit timezone offset."""
    data = _valid_article_data()
    data["normalized_at"] = datetime(2026, 7, 14, 10, 0)

    with pytest.raises(ValidationError):
        Article.model_validate(data)
