import pytest

from reinaluxe_recovery.acquisition.robots import RobotsPolicy, product_token

LIVE_POLICY = """User-agent: *
Allow: /
Disallow: /wp-admin/
Allow: /wp-admin/admin-ajax.php
Disallow: /wp-content/uploads/wpo/wpo-plugins-tables-list.json
Content-signal: search=yes,ai-train=no
Sitemap: https://example.com/sitemap.xml"""


@pytest.mark.parametrize(
    "path,expected",
    [
        ("/", True),
        ("/best-hermes-replica-bags-guide/", True),
        ("/aaa-replica-reviews/best-celine-replica-bags-2025/", True),
        ("/wp-admin/", False),
        ("/wp-admin/edit.php", False),
        ("/wp-admin/admin-ajax.php", True),
        ("/wp-content/uploads/wpo/wpo-plugins-tables-list.json", False),
    ],
)
@pytest.mark.parametrize("line_ending", ["\n", "\r\n"])
@pytest.mark.parametrize("bom", [b"", b"\xef\xbb\xbf"])
@pytest.mark.parametrize("trailing_newline", [False, True])
def test_live_policy_semantics_are_stable(
    path, expected, line_ending, bom, trailing_newline
) -> None:
    text = LIVE_POLICY.replace("\n", line_ending)
    if trailing_newline:
        text += line_ending
    policy = RobotsPolicy.from_bytes(bom + text.encode())

    assert (
        policy.allows("ReinaLuxeRecoveryAudit", f"https://example.com{path}")
        is expected
    )


def test_duplicate_exact_and_wildcard_groups_merge() -> None:
    policy = RobotsPolicy.from_bytes(
        b"""# first wildcard group
User-agent: *
Disallow: /one

User-agent: ReinaLuxeRecoveryAudit
Disallow: /specific

User-agent: *
Disallow: /two

User-agent: ReinaLuxeRecoveryAudit
Disallow: /specific-two
"""
    )

    assert policy.allows("OtherBot", "https://example.com/one") is False
    assert policy.allows("OtherBot", "https://example.com/two") is False
    assert policy.allows("ReinaLuxeRecoveryAudit", "https://example.com/one") is True
    assert (
        policy.allows("ReinaLuxeRecoveryAudit", "https://example.com/specific") is False
    )
    assert (
        policy.allows("ReinaLuxeRecoveryAudit", "https://example.com/specific-two")
        is False
    )


@pytest.mark.parametrize(
    "spacing",
    [
        "# explanatory comment\n",
        "\n",
        "# first comment\n\n# second comment\n\n",
    ],
)
def test_comments_and_blank_lines_do_not_end_an_active_group(spacing) -> None:
    policy = RobotsPolicy.from_bytes(
        f"User-agent: *\n{spacing}Disallow: /private\n".encode()
    )

    assert policy.allows("Bot", "https://example.com/private") is False


def test_product_group_matching_is_exact_and_case_insensitive() -> None:
    policy = RobotsPolicy.from_bytes(
        b"""User-agent: Reina
Disallow: /partial

User-agent: RecoveryAudit
Disallow: /partial

User-agent: LuxeRecovery
Disallow: /partial

User-agent: ReinaLuxeRecoveryAudit
Disallow: /exact

User-agent: *
Disallow: /wildcard
"""
    )

    assert policy.allows("reinaluxerecoveryaudit", "https://example.com/exact") is False
    assert (
        policy.allows("ReinaLuxeRecoveryAudit", "https://example.com/partial") is True
    )
    assert (
        policy.allows("ReinaLuxeRecoveryAudit", "https://example.com/wildcard") is True
    )
    assert policy.allows("ReinaLuxeRecoveryAuditExtended", "https://example.com/exact")
    assert (
        policy.allows("ReinaLuxeRecoveryAuditExtended", "https://example.com/wildcard")
        is False
    )
    assert policy.allows("OtherBot", "https://example.com/wildcard") is False


def test_longest_rule_and_equal_length_allow_win() -> None:
    policy = RobotsPolicy.from_bytes(
        b"""User-agent: *
Allow: /
Disallow: /private
Disallow: /same
Allow: /same
Allow: /private/public
Disallow:
"""
    )

    assert policy.allows("Bot", "https://example.com/private/file") is False
    assert policy.allows("Bot", "https://example.com/private/public/file") is True
    assert policy.allows("Bot", "https://example.com/same") is True


def test_query_and_percent_encoding_are_deterministic() -> None:
    policy = RobotsPolicy.from_bytes(
        b"""User-agent: *
Disallow: /search?private=1
Disallow: /caf%C3%A9
Disallow: /docs/~owner
"""
    )

    assert policy.allows("Bot", "https://example.com/search?private=1") is False
    assert policy.allows("Bot", "https://example.com/search?public=1") is True
    assert policy.allows("Bot", "https://example.com/caf%C3%A9") is False
    assert policy.allows("Bot", "https://example.com/café") is False
    assert policy.allows("Bot", "https://example.com/docs/%7Eowner") is False
    assert policy.allows("Bot", "/search?private=1") == policy.allows(
        "Bot", "https://example.com/search?private=1"
    )


def test_product_token_extraction() -> None:
    assert (
        product_token("ReinaLuxeRecoveryAudit/1.0 (+https://reinaluxe.co/)")
        == "ReinaLuxeRecoveryAudit"
    )
