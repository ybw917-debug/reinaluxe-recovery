from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from reinaluxe_recovery.acquisition import AcquisitionRequest, AcquisitionSourceType


def test_request_round_trip_and_strict_validation() -> None:
    request = AcquisitionRequest(
        created_at=datetime.now(UTC),
        source_type=AcquisitionSourceType.URL_LIST,
        explicit_urls=("https://example.com/a",),
        allowed_hosts=frozenset({"example.com"}),
        output_directory=Path("out"),
        user_agent="OwnerAgent",
        request_timeout_seconds=1,
        delay_between_requests_seconds=0,
    )
    assert AcquisitionRequest.model_validate_json(request.model_dump_json()) == request
    with pytest.raises(ValidationError):
        AcquisitionRequest(
            created_at=datetime.now(),
            source_type="url_list",
            explicit_urls=("https://example.com",),
            allowed_hosts=frozenset({"example.com"}),
            output_directory=Path("out"),
            user_agent="x",
            surprise=True,
        )


@pytest.mark.parametrize(
    "field,value",
    [
        ("request_timeout_seconds", 0),
        ("delay_between_requests_seconds", -1),
        ("maximum_urls", 0),
    ],
)
def test_invalid_numeric_options(field, value) -> None:
    data = dict(
        created_at=datetime.now(UTC),
        source_type="url_list",
        explicit_urls=("https://example.com",),
        allowed_hosts=frozenset({"example.com"}),
        output_directory=Path("out"),
        user_agent="x",
        **{field: value},
    )
    with pytest.raises(ValidationError):
        AcquisitionRequest(**data)


def test_credentials_are_rejected_from_metadata() -> None:
    with pytest.raises(ValidationError):
        AcquisitionRequest(
            created_at=datetime.now(UTC),
            source_type="url_list",
            explicit_urls=("https://example.com",),
            allowed_hosts=frozenset({"example.com"}),
            output_directory=Path("out"),
            user_agent="x",
            metadata={"Authorization": "secret"},
        )
