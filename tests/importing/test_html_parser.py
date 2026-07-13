"""Tests for deterministic BeautifulSoup extraction rules."""

from datetime import UTC, datetime
from pathlib import Path

from pydantic import HttpUrl, TypeAdapter

from reinaluxe_recovery.domain import LinkType
from reinaluxe_recovery.importing import ImportWarningCode, parse_html

FIXTURES = Path(__file__).parent / "fixtures"
SOURCE_URL = TypeAdapter(HttpUrl).validate_python(
    "https://owner.example/articles/current/"
)
FETCHED_AT = datetime(2026, 7, 14, 12, 0, tzinfo=UTC)


def _parse(name: str):  # type: ignore[no-untyped-def]
    return parse_html(
        source_url=SOURCE_URL,
        fetched_at=FETCHED_AT,
        status_code=200,
        headers={},
        html_body=(FIXTURES / name).read_text(encoding="utf-8"),
    )


def test_complete_html_extracts_required_content() -> None:
    """Complete semantic HTML yields metadata and typed visible content."""
    parsed = _parse("complete-article.html")

    assert parsed.title == "Offline Craftsmanship Guide"
    assert parsed.h1 == "Offline Craftsmanship Guide"
    assert str(parsed.canonical_url) == "https://owner.example/guides/craftsmanship/"
    assert parsed.meta_description is not None
    assert parsed.published_at is not None
    assert parsed.modified_at is not None
    assert len(parsed.schema_markup) == 1
    assert sum(len(section.images) for section in parsed.sections) == 1


def test_relative_urls_are_resolved_and_classified() -> None:
    """Relative links and image paths resolve against the supplied source URL."""
    parsed = _parse("relative-urls.html")
    link = next(item for section in parsed.sections for item in section.links)
    image = next(item for section in parsed.sections for item in section.images)

    assert str(link.target_url) == "https://owner.example/articles/guide/"
    assert link.link_type is LinkType.INTERNAL
    assert str(image.source_url) == "https://owner.example/media/example.jpg"


def test_navigation_footer_and_cookie_banner_are_excluded() -> None:
    """Known site chrome does not enter normalized editorial paragraphs."""
    parsed = _parse("site-chrome.html")
    paragraphs = [
        item.text for section in parsed.sections for item in section.paragraphs
    ]

    assert paragraphs == ["Unique editorial paragraph."]


def test_heading_order_is_preserved() -> None:
    """H1, H2, and H3 remain in their document order."""
    parsed = _parse("complete-article.html")

    assert [
        section.heading.level for section in parsed.sections if section.heading
    ] == [
        1,
        2,
        3,
    ]


def test_malformed_json_ld_produces_warning() -> None:
    """Malformed optional JSON-LD is ignored without losing visible content."""
    parsed = _parse("malformed-json-ld.html")

    assert not parsed.schema_markup
    assert ImportWarningCode.MALFORMED_JSON_LD in {
        warning.code for warning in parsed.warnings
    }


def test_visible_faq_is_extracted_without_duplicate_answer_paragraph() -> None:
    """A visible details element becomes one FAQ rather than duplicate content."""
    parsed = _parse("complete-article.html")
    faqs = [item for section in parsed.sections for item in section.faq_items]
    paragraphs = [
        item.text for section in parsed.sections for item in section.paragraphs
    ]

    assert faqs[0].question == "Does stitch count prove quality?"
    assert faqs[0].answer.startswith("No.")
    assert faqs[0].answer not in paragraphs


def test_overlapping_main_and_article_are_not_extracted_twice() -> None:
    """Selecting the nested article avoids duplicate extraction from main."""
    parsed = _parse("complete-article.html")
    paragraphs = [
        item.text for section in parsed.sections for item in section.paragraphs
    ]

    assert (
        paragraphs.count(
            "This introduction describes directly observable construction details."
        )
        == 1
    )
