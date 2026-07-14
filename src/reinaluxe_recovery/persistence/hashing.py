"""Stable hashing for editorially meaningful normalized Article content."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from reinaluxe_recovery.domain import Article

_NESTED_ID_EXCLUDE: dict[str, Any] = {"id": True}
_ARTICLE_HASH_EXCLUDE: dict[str, Any] = {
    "id": True,
    "normalized_at": True,
    "source_content_hash": True,
    "source_snapshot_id": True,
    "sections": {
        "__all__": {
            "id": True,
            "heading": _NESTED_ID_EXCLUDE,
            "paragraphs": {"__all__": _NESTED_ID_EXCLUDE},
            "images": {"__all__": _NESTED_ID_EXCLUDE},
            "links": {"__all__": _NESTED_ID_EXCLUDE},
            "faq_items": {"__all__": _NESTED_ID_EXCLUDE},
            "entity_mentions": {"__all__": {"id": True, "source_section_id": True}},
        }
    },
    "schema_markup": {
        "__all__": {"id": True, "source_section_id": True},
    },
}


def normalized_article_payload(article: Article) -> dict[str, Any]:
    """Return the canonical hash payload without transport identities.

    Top-level record identity, source-snapshot identity, normalization time,
    source transport hash, generated nested IDs, and ID-based section pointers
    are excluded. All remaining editorial content and classification fields are
    included.
    """
    return article.model_dump(mode="json", exclude=_ARTICLE_HASH_EXCLUDE)


def hash_normalized_article(article: Article) -> str:
    """Hash canonical JSON for the normalized editorial Article payload."""
    serialized = json.dumps(
        normalized_article_payload(article),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()
