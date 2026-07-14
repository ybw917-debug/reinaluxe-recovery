"""Deterministic RFC-style robots exclusion policy evaluation."""

import re
from dataclasses import dataclass
from urllib.parse import unquote_to_bytes, urlsplit

_PRODUCT_TOKEN = re.compile(r"^[!#$%&'*+.^_`|~0-9A-Za-z-]+")
_UNRESERVED = frozenset(
    b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~"
)


def product_token(user_agent: str) -> str:
    """Extract the leading HTTP product token used for robots group matching."""
    match = _PRODUCT_TOKEN.match(user_agent.strip())
    if match is None:
        raise ValueError("User-Agent must begin with a valid product token")
    return match.group(0)


def _normalize_octets(value: str) -> str:
    normalized: list[str] = []
    index = 0
    while index < len(value):
        if (
            value[index] == "%"
            and index + 2 < len(value)
            and all(
                character in "0123456789abcdefABCDEF"
                for character in value[index + 1 : index + 3]
            )
        ):
            octet = int(value[index + 1 : index + 3], 16)
            normalized.append(chr(octet) if octet in _UNRESERVED else f"%{octet:02X}")
            index += 3
            continue
        character = value[index]
        if ord(character) < 128:
            normalized.append(character)
        else:
            normalized.extend(f"%{octet:02X}" for octet in character.encode("utf-8"))
        index += 1
    return "".join(normalized)


def _path_and_query(url: str) -> str:
    parts = urlsplit(url)
    path = parts.path or "/"
    if parts.query:
        path = f"{path}?{parts.query}"
    return _normalize_octets(path)


@dataclass(frozen=True)
class RobotsRule:
    pattern: str
    allow: bool

    def match_length(self, path_and_query: str) -> int | None:
        end_anchored = self.pattern.endswith("$")
        source = self.pattern[:-1] if end_anchored else self.pattern
        pieces = source.split("*")
        normalized = [_normalize_octets(piece) for piece in pieces]
        expression = ".*".join(re.escape(piece) for piece in normalized)
        if end_anchored:
            expression = f"{expression}$"
        if re.match(expression, path_and_query) is None:
            return None
        literal = "".join(normalized)
        return len(unquote_to_bytes(literal))


@dataclass(frozen=True)
class RobotsGroup:
    agents: tuple[str, ...]
    rules: tuple[RobotsRule, ...]


@dataclass(frozen=True)
class RobotsPolicy:
    groups: tuple[RobotsGroup, ...] = ()

    @classmethod
    def from_bytes(cls, content: bytes) -> "RobotsPolicy":
        text = content.decode("utf-8-sig")
        groups: list[RobotsGroup] = []
        agents: list[str] = []
        rules: list[RobotsRule] = []

        def finish_group() -> None:
            nonlocal agents, rules
            if agents:
                groups.append(RobotsGroup(tuple(agents), tuple(rules)))
            agents = []
            rules = []

        for raw_line in text.splitlines():
            line = raw_line.split("#", 1)[0].strip()
            if not line:
                continue
            directive, separator, raw_value = line.partition(":")
            if not separator:
                continue
            name = directive.strip().casefold()
            value = raw_value.strip()
            if name == "user-agent":
                if rules:
                    finish_group()
                if value:
                    agents.append(value.casefold())
            elif name in {"allow", "disallow"} and agents:
                if value:
                    rules.append(RobotsRule(value, allow=name == "allow"))
            # Sitemap and unknown directives are intentionally not access rules.
        finish_group()
        return cls(tuple(groups))

    def allows(self, user_agent_product: str, url: str) -> bool:
        product = user_agent_product.casefold()
        selected = [group for group in self.groups if product in group.agents]
        if not selected:
            selected = [group for group in self.groups if "*" in group.agents]

        path_and_query = _path_and_query(url)
        matches = [
            (length, rule.allow)
            for group in selected
            for rule in group.rules
            if (length := rule.match_length(path_and_query)) is not None
        ]
        if not matches:
            return True
        longest = max(length for length, _ in matches)
        return any(allow for length, allow in matches if length == longest)
