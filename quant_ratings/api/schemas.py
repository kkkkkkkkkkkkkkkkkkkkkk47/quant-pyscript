"""Pydantic v2 response schemas for the Quant Ratings API.

These models define the JSON shapes returned by the API endpoints.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class WeightProfileResponse(BaseModel):
    """Serialised representation of a WeightProfile."""

    asset_class: str
    sub_category: Optional[str]
    sentiment_pct: float
    orderflow_pct: float
    economic_pct: float


class RatingRecordResponse(BaseModel):
    """Serialised representation of a RatingRecord (Requirement 10.6)."""

    record_id: str
    security_id: str
    asset_class: str
    composite_score: float
    rating: str
    sentiment_score: float
    orderflow_score: float
    economic_score: float
    weight_profile: WeightProfileResponse
    data_deficient: bool
    computed_at: datetime


class ErrorResponse(BaseModel):
    """Standard error envelope returned on 4xx / 5xx responses."""

    error: str
    code: str


class HealthResponse(BaseModel):
    """Health-check response (Requirement 11.4)."""

    last_successful_cycle_at: Optional[datetime]
    securities_rated: int
    status: str  # "ok" or "degraded"
