from collections.abc import Callable

import httpx
import pytest


@pytest.fixture
def public_resolver():
    return lambda host: ["93.184.216.34"]


@pytest.fixture
def transport_factory() -> Callable:
    return lambda handler: httpx.MockTransport(handler)
