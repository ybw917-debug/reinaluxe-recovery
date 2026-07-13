"""Import smoke test for the project package."""

import reinaluxe_recovery


def test_package_import() -> None:
    """The package can be imported from the configured source layout."""
    assert reinaluxe_recovery.__version__ == "0.1.0"
