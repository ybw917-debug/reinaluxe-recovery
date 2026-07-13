"""Shared configuration and constrained types for domain contracts."""

from typing import Annotated

from pydantic import BaseModel, ConfigDict, StringConstraints

NonEmptyText = Annotated[str, StringConstraints(min_length=1, strip_whitespace=True)]
Sha256Digest = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]


class DomainModel(BaseModel):
    """Base model for strict, immutable domain data."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
        validate_default=True,
    )
