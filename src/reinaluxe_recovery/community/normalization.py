"""Transparent deterministic normalization, hashing, and duplicate reporting."""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from datetime import UTC, date, datetime
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from pydantic import TypeAdapter

_SPACE_RE = re.compile(r"\s+")
_TOKEN_RE = re.compile(r"[\w]+", re.UNICODE)
_LANGUAGE = TypeAdapter(str)


def normalize_text(value: str) -> str:
    """Normalize Unicode compatibility forms and collapse whitespace."""
    return _SPACE_RE.sub(" ", unicodedata.normalize("NFKC", value)).strip()


def normalize_claim_text(value: str) -> str:
    """Normalize a proposition for exact identity without changing meaning."""
    return normalize_text(value).casefold()


def normalize_platform_name(value: str) -> str:
    """Return a stable lowercase platform label with conservative aliases."""
    normalized = normalize_text(value).casefold().replace("_", " ").replace("-", " ")
    aliases = {
        "reddit com": "reddit",
        "reddit": "reddit",
        "youtube com": "youtube",
        "youtube": "youtube",
        "first party": "first_party",
        "owner": "owner",
    }
    return aliases.get(normalized, normalized.replace(" ", "_"))


def normalize_language(value: str) -> str:
    """Normalize common BCP-47 casing while retaining offline owner input."""
    raw = normalize_text(_LANGUAGE.validate_python(value)).replace("_", "-")
    parts = raw.split("-")
    if not parts or not 2 <= len(parts[0]) <= 3 or not parts[0].isalpha():
        raise ValueError("language must begin with a two- or three-letter code")
    normalized = [parts[0].lower()]
    for part in parts[1:]:
        normalized.append(part.upper() if len(part) == 2 and part.isalpha() else part)
    return "-".join(normalized)


def normalize_datetime(value: datetime | date | str) -> str:
    """Return a timezone-aware ISO 8601 timestamp normalized to UTC."""
    if isinstance(value, str):
        prepared = value.strip().replace("Z", "+00:00")
        parsed = datetime.fromisoformat(prepared)
    elif isinstance(value, date) and not isinstance(value, datetime):
        parsed = datetime(value.year, value.month, value.day, tzinfo=UTC)
    else:
        parsed = value
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("date/time values must include a timezone")
    return parsed.astimezone(UTC).isoformat().replace("+00:00", "Z")


def normalize_url(value: str) -> str:
    """Normalize an HTTP(S) audit URL without resolving or fetching it."""
    parts = urlsplit(normalize_text(value))
    if parts.scheme.lower() not in {"http", "https"} or not parts.hostname:
        raise ValueError("source_url must be an absolute HTTP(S) URL")
    scheme = parts.scheme.lower()
    host = parts.hostname.encode("idna").decode("ascii").lower()
    port = parts.port
    if port and not (
        (scheme == "http" and port == 80) or (scheme == "https" and port == 443)
    ):
        host = f"{host}:{port}"
    path = parts.path or "/"
    query = urlencode(sorted(parse_qsl(parts.query, keep_blank_values=True)))
    return urlunsplit((scheme, host, path, query, ""))


def canonical_json(value: Any) -> str:
    """Serialize JSON-compatible content deterministically."""
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def content_hash(value: Any) -> str:
    """Hash canonical UTF-8 JSON with SHA-256."""
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def stable_id(prefix: str, value: Any) -> str:
    """Return a readable stable ID derived from normalized scope/content."""
    return f"{prefix}_{content_hash(value)[:24]}"


def exact_duplicate_groups(
    records: list[dict[str, Any]], id_field: str
) -> list[list[str]]:
    """Group records sharing an exact content hash without merging them."""
    by_hash: dict[str, list[str]] = {}
    for record in records:
        by_hash.setdefault(str(record["content_hash"]), []).append(
            str(record[id_field])
        )
    return [sorted(ids) for ids in by_hash.values() if len(ids) > 1]


def likely_duplicate_claims(
    claims: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    """Report transparent token-overlap candidates; never merge them."""
    result: dict[str, list[dict[str, Any]]] = {str(c["claim_id"]): [] for c in claims}
    for index, left in enumerate(claims):
        left_tokens = set(_TOKEN_RE.findall(str(left["normalized_claim_text"])))
        if not left_tokens:
            continue
        for right in claims[index + 1 :]:
            right_tokens = set(_TOKEN_RE.findall(str(right["normalized_claim_text"])))
            union = left_tokens | right_tokens
            score = len(left_tokens & right_tokens) / len(union) if union else 0.0
            same_scope = all(
                left.get(field) == right.get(field)
                for field in ("brand", "model", "variant", "material")
                if left.get(field) or right.get(field)
            )
            if (
                score >= 0.72
                and same_scope
                and left["content_hash"] != right["content_hash"]
            ):
                evidence = {
                    "claim_id": right["claim_id"],
                    "reason": "normalized token Jaccard overlap within matching entity scope",
                    "score": round(score, 4),
                    "shared_tokens": sorted(left_tokens & right_tokens),
                }
                result[str(left["claim_id"])].append(evidence)
                reciprocal = dict(evidence)
                reciprocal["claim_id"] = left["claim_id"]
                result[str(right["claim_id"])].append(reciprocal)
    return result


def possible_conflicts(claims: list[dict[str, Any]]) -> dict[str, list[str]]:
    """Flag explicit contradiction records or opposite negation in close scope."""
    output: dict[str, list[str]] = {str(c["claim_id"]): [] for c in claims}
    negative = {"not", "no", "never", "without", "isn't", "doesn't"}
    for index, left in enumerate(claims):
        left_tokens = set(_TOKEN_RE.findall(str(left["normalized_claim_text"])))
        for right in claims[index + 1 :]:
            right_tokens = set(_TOKEN_RE.findall(str(right["normalized_claim_text"])))
            common = left_tokens & right_tokens
            smaller = min(len(left_tokens), len(right_tokens)) or 1
            overlap = len(common) / smaller
            explicit = "correction_or_contradiction" in {
                left.get("claim_type"),
                right.get("claim_type"),
            }
            negation_differs = bool(left_tokens & negative) != bool(
                right_tokens & negative
            )
            if overlap >= 0.65 and (explicit or negation_differs):
                left_id, right_id = str(left["claim_id"]), str(right["claim_id"])
                output[left_id].append(right_id)
                output[right_id].append(left_id)
    return {key: sorted(set(value)) for key, value in output.items()}
