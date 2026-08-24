"""Shared schema primitives."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

ConfidenceLevel = Literal["high", "medium", "low", "none"]
RiskLevel = Literal["low", "medium", "high", "unknown"]
AssessmentLevel = Literal["low", "moderate", "higher", "unknown"]
TerrainKind = Literal["coastal", "lowland", "hilly", "highland", "mountainous", "unknown"]
DataQuality = Literal["live", "database", "estimate", "unavailable"]


class CamelModel(BaseModel):
    """Every response model serialises as camelCase for the TypeScript client."""

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        from_attributes=True,
    )


class DataSource(CamelModel):
    """Provenance for one field of a report, so the UI can be honest about it."""

    field: str
    provider: str
    quality: DataQuality
    note: str | None = None


class ErrorDetail(CamelModel):
    code: str
    message: str
    detail: str | None = None


class ErrorResponse(CamelModel):
    """The shape of every non-2xx body this API returns."""

    error: ErrorDetail
