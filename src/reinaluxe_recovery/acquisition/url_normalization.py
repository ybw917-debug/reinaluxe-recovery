"""URL normalization and public-target safeguards."""

import ipaddress
import socket
from collections.abc import Callable
from urllib.parse import urlsplit, urlunsplit

from reinaluxe_recovery.acquisition.exceptions import UnsafeTargetError

Resolver = Callable[[str], list[str]]


def normalize_acquisition_url(value: str) -> str:
    parts = urlsplit(value)
    if parts.scheme.casefold() not in {"http", "https"} or not parts.hostname:
        raise UnsafeTargetError("only absolute HTTP(S) URLs are allowed")
    if parts.username or parts.password:
        raise UnsafeTargetError("URL credentials are not allowed")
    host = parts.hostname.casefold()
    rendered_host = f"[{host}]" if ":" in host else host
    port = f":{parts.port}" if parts.port else ""
    return urlunsplit(
        (
            parts.scheme.casefold(),
            f"{rendered_host}{port}",
            parts.path or "/",
            parts.query,
            "",
        )
    )


def system_resolver(host: str) -> list[str]:
    return sorted({str(item[4][0]) for item in socket.getaddrinfo(host, None)})


def validate_public_url(
    value: str, allowed_hosts: frozenset[str], resolver: Resolver = system_resolver
) -> str:
    normalized = normalize_acquisition_url(value)
    host = urlsplit(normalized).hostname
    assert host is not None
    if host.casefold() not in {item.casefold() for item in allowed_hosts}:
        raise UnsafeTargetError(f"host is not allowed: {host}")
    try:
        addresses = [ipaddress.ip_address(item) for item in resolver(host)]
    except (OSError, ValueError) as error:
        raise UnsafeTargetError(f"could not resolve a public target: {host}") from error
    if not addresses or any(not address.is_global for address in addresses):
        raise UnsafeTargetError(f"target resolves to a non-public address: {host}")
    return normalized
