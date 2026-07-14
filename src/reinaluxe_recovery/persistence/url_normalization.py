"""Deterministic offline URL normalization for canonical page identity."""

from urllib.parse import SplitResult, urlsplit, urlunsplit

from reinaluxe_recovery.persistence.exceptions import URLNormalizationError

SUPPORTED_SCHEMES = frozenset({"http", "https"})


def normalize_page_url(url: str) -> str:
    """Normalize a complete HTTP(S) URL without making network assumptions.

    Scheme and host are lowercased, default ports and fragments are removed,
    and an empty path becomes ``/``. Path case and the exact query string are
    preserved because changing either could merge distinct resources.
    """
    try:
        parsed = urlsplit(url)
        port = parsed.port
    except ValueError as error:
        raise URLNormalizationError(f"invalid page URL: {error}") from error

    scheme = parsed.scheme.lower()
    if scheme not in SUPPORTED_SCHEMES:
        raise URLNormalizationError("page URL must use http or https")
    if not parsed.hostname:
        raise URLNormalizationError("page URL must be absolute and include a host")
    if parsed.username is not None or parsed.password is not None:
        raise URLNormalizationError("page URL must not contain user information")

    host = parsed.hostname.lower()
    if ":" in host:
        host = f"[{host}]"
    include_port = port is not None and not (
        (scheme == "http" and port == 80) or (scheme == "https" and port == 443)
    )
    netloc = f"{host}:{port}" if include_port else host
    normalized = SplitResult(
        scheme=scheme,
        netloc=netloc,
        path=parsed.path or "/",
        query=parsed.query,
        fragment="",
    )
    return urlunsplit(normalized)
