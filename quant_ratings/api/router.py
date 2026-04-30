"""FastAPI router for the Quant Ratings API.

Exposes four endpoints:
  GET /ratings/{security_id}/latest
  GET /ratings/{security_id}/history
  GET /ratings/asset-class/{asset_class}/latest
  GET /health

Requirements: 10.1, 10.2, 10.3, 10.4, 10.5, 10.6, 11.4
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from quant_ratings.api.schemas import (
    ErrorResponse,
    HealthResponse,
    RatingRecordResponse,
    WeightProfileResponse,
)
from quant_ratings.config.security_registry import SecurityRegistry
from quant_ratings.engine.rating_engine import RatingEngine
from quant_ratings.models.enums import AssetClass
from quant_ratings.models.rating_record import RatingRecord
from quant_ratings.persistence.base import RatingStore, StorageError

router = APIRouter()


# ---------------------------------------------------------------------------
# Dependency providers — replaced via app.dependency_overrides in tests
# ---------------------------------------------------------------------------


def get_store() -> RatingStore:  # pragma: no cover
    """Return the application-level RatingStore.

    Override this in tests via ``app.dependency_overrides[get_store] = ...``.
    """
    raise NotImplementedError("get_store dependency not configured")


def get_security_registry() -> SecurityRegistry:  # pragma: no cover
    """Return the application-level SecurityRegistry.

    Override this in tests via ``app.dependency_overrides[get_security_registry] = ...``.
    """
    raise NotImplementedError("get_security_registry dependency not configured")


def get_rating_engine() -> RatingEngine:  # pragma: no cover
    """Return the application-level RatingEngine (used for health checks).

    Override this in tests via ``app.dependency_overrides[get_rating_engine] = ...``.
    """
    raise NotImplementedError("get_rating_engine dependency not configured")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _record_to_response(record: RatingRecord) -> RatingRecordResponse:
    """Convert a domain RatingRecord to its API response schema."""
    wp = record.weight_profile
    return RatingRecordResponse(
        record_id=record.record_id,
        security_id=record.security_id,
        asset_class=record.asset_class,
        composite_score=record.composite_score,
        rating=record.rating,
        sentiment_score=record.sentiment_score,
        orderflow_score=record.orderflow_score,
        economic_score=record.economic_score,
        weight_profile=WeightProfileResponse(
            asset_class=wp.asset_class,
            sub_category=wp.sub_category,
            sentiment_pct=wp.sentiment_pct,
            orderflow_pct=wp.orderflow_pct,
            economic_pct=wp.economic_pct,
        ),
        data_deficient=record.data_deficient,
        computed_at=record.computed_at,
    )


# ---------------------------------------------------------------------------
# Endpoints
#
# IMPORTANT: /ratings/asset-class/{asset_class}/latest MUST be registered
# before /ratings/{security_id}/latest to avoid FastAPI treating
# "asset-class" as a security_id path parameter.
# ---------------------------------------------------------------------------


@router.get(
    "/ratings/asset-class/{asset_class}/latest",
    response_model=list[RatingRecordResponse],
    responses={
        404: {"model": ErrorResponse},
        503: {"model": ErrorResponse},
    },
)
def get_latest_by_asset_class(
    asset_class: str,
    store: Annotated[RatingStore, Depends(get_store)],
) -> list[RatingRecordResponse]:
    """Return the most recent RatingRecord for every security in *asset_class*.

    Requirement 10.3
    """
    # Validate asset_class value
    try:
        ac_enum = AssetClass(asset_class)
    except ValueError:
        raise HTTPException(
            status_code=404,
            detail=ErrorResponse(
                error=f"Asset class '{asset_class}' not found",
                code="ASSET_CLASS_NOT_FOUND",
            ).model_dump(),
        )

    try:
        records = store.get_latest_by_asset_class(ac_enum.value)
    except StorageError as exc:
        raise HTTPException(
            status_code=503,
            detail=ErrorResponse(
                error=str(exc),
                code="STORE_UNAVAILABLE",
            ).model_dump(),
        )

    if not records:
        raise HTTPException(
            status_code=404,
            detail=ErrorResponse(
                error=f"No records found for asset class '{asset_class}'",
                code="ASSET_CLASS_NOT_FOUND",
            ).model_dump(),
        )

    return [_record_to_response(r) for r in records]


@router.get(
    "/ratings/{security_id}/latest",
    response_model=RatingRecordResponse,
    responses={
        404: {"model": ErrorResponse},
        503: {"model": ErrorResponse},
    },
)
def get_latest(
    security_id: str,
    registry: Annotated[SecurityRegistry, Depends(get_security_registry)],
    store: Annotated[RatingStore, Depends(get_store)],
) -> RatingRecordResponse:
    """Return the most recent RatingRecord for *security_id*.

    Requirement 10.1
    """
    if registry.get(security_id) is None:
        raise HTTPException(
            status_code=404,
            detail=ErrorResponse(
                error=f"Security '{security_id}' not found in registry",
                code="SECURITY_NOT_FOUND",
            ).model_dump(),
        )

    try:
        record = store.get_latest(security_id)
    except StorageError as exc:
        raise HTTPException(
            status_code=503,
            detail=ErrorResponse(
                error=str(exc),
                code="STORE_UNAVAILABLE",
            ).model_dump(),
        )

    if record is None:
        raise HTTPException(
            status_code=404,
            detail=ErrorResponse(
                error=f"No rating record found for security '{security_id}'",
                code="SECURITY_NOT_FOUND",
            ).model_dump(),
        )

    return _record_to_response(record)


@router.get(
    "/ratings/{security_id}/history",
    response_model=list[RatingRecordResponse],
    responses={
        400: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        503: {"model": ErrorResponse},
    },
)
def get_history(
    security_id: str,
    registry: Annotated[SecurityRegistry, Depends(get_security_registry)],
    store: Annotated[RatingStore, Depends(get_store)],
    from_dt: Annotated[Optional[str], Query(alias="from_dt")] = None,
    to_dt: Annotated[Optional[str], Query(alias="to_dt")] = None,
) -> list[RatingRecordResponse]:
    """Return all RatingRecords for *security_id* within the given time range.

    Requirement 10.2
    """
    if registry.get(security_id) is None:
        raise HTTPException(
            status_code=404,
            detail=ErrorResponse(
                error=f"Security '{security_id}' not found in registry",
                code="SECURITY_NOT_FOUND",
            ).model_dump(),
        )

    # Parse ISO8601 date parameters
    try:
        from_utc: datetime = (
            datetime.fromisoformat(from_dt) if from_dt else datetime.min
        )
        to_utc: datetime = (
            datetime.fromisoformat(to_dt) if to_dt else datetime.max
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=ErrorResponse(
                error=f"Invalid date parameter: {exc}",
                code="INVALID_PARAMETERS",
            ).model_dump(),
        )

    try:
        records = store.get_history(security_id, from_utc, to_utc)
    except StorageError as exc:
        raise HTTPException(
            status_code=503,
            detail=ErrorResponse(
                error=str(exc),
                code="STORE_UNAVAILABLE",
            ).model_dump(),
        )

    return [_record_to_response(r) for r in records]


@router.get(
    "/health",
    response_model=HealthResponse,
)
def get_health(
    engine: Annotated[RatingEngine, Depends(get_rating_engine)],
) -> HealthResponse:
    """Return the health status of the Rating_Engine.

    Requirement 11.4
    """
    last_cycle = engine.last_successful_cycle_at
    securities_rated = engine.last_cycle_security_count
    status = "ok" if last_cycle is not None else "degraded"

    return HealthResponse(
        last_successful_cycle_at=last_cycle,
        securities_rated=securities_rated,
        status=status,
    )
