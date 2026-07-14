"""Tests for deterministic page identity and normalized Article hashing."""

from datetime import timedelta
from uuid import uuid4

import pytest

from reinaluxe_recovery.importing import ImportResult
from reinaluxe_recovery.persistence import (
    URLNormalizationError,
    hash_normalized_article,
    normalize_page_url,
)


def test_url_normalization_has_conservative_deterministic_rules() -> None:
    """Only syntax known to preserve resource identity is normalized."""
    assert (
        normalize_page_url("HTTPS://Example.COM:443/Path/Case?b=2&a=1#section")
        == "https://example.com/Path/Case?b=2&a=1"
    )
    assert normalize_page_url("http://EXAMPLE.com:80") == "http://example.com/"


def test_fragments_do_not_create_distinct_identity() -> None:
    """Fragments identify positions within a response, not separate pages."""
    assert normalize_page_url("https://example.com/page#one") == normalize_page_url(
        "https://example.com/page#two"
    )


def test_query_strings_remain_distinct() -> None:
    """Query values and order are preserved without speculative merging."""
    assert normalize_page_url("https://example.com/page?a=1&b=2") != normalize_page_url(
        "https://example.com/page?b=2&a=1"
    )


@pytest.mark.parametrize(
    "url",
    ["/relative", "example.com/path", "ftp://example.com/path"],
)
def test_relative_and_unsupported_urls_are_rejected(url: str) -> None:
    """Page identity requires an absolute HTTP(S) URL."""
    with pytest.raises(URLNormalizationError):
        normalize_page_url(url)


def test_hash_excludes_transport_identity_and_time(
    successful_import: ImportResult,
) -> None:
    """A fresh snapshot identity does not create a content version by itself."""
    assert successful_import.article is not None
    article = successful_import.article
    changed_transport = article.model_copy(
        update={
            "id": uuid4(),
            "source_snapshot_id": uuid4(),
            "normalized_at": article.normalized_at + timedelta(days=1),
            "source_content_hash": "f" * 64,
        }
    )
    assert hash_normalized_article(article) == hash_normalized_article(
        changed_transport
    )


def test_hash_changes_for_meaningful_editorial_change(
    successful_import: ImportResult,
) -> None:
    """Editorial content changes produce a new normalized-content hash."""
    assert successful_import.article is not None
    changed = successful_import.article.model_copy(
        update={"title": f"{successful_import.article.title} Revised"}
    )
    assert hash_normalized_article(
        successful_import.article
    ) != hash_normalized_article(changed)


def test_hash_preserves_arbitrary_schema_payload_ids(
    successful_import: ImportResult,
) -> None:
    """JSON-LD identity content is not mistaken for a generated model ID."""
    assert successful_import.article is not None
    assert successful_import.article.schema_markup
    markup = successful_import.article.schema_markup[0]
    changed_markup = markup.model_copy(
        update={"payload": markup.payload | {"id": "editorial-schema-identity"}}
    )
    changed = successful_import.article.model_copy(
        update={"schema_markup": [changed_markup]}
    )

    assert hash_normalized_article(
        successful_import.article
    ) != hash_normalized_article(changed)
