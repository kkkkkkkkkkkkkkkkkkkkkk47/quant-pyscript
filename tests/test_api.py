"""Tests for the Quant Ratings API layer.

Feature: quant-ratings, Property 17: JSON schema completeness

**Validates: Requirements 10.6**

Property 17: JSON API response always contains all required fields.
For any RatingRecord returned by the API, the serialised JSON object must
contain all fields defined in the RatingRecordResponse schema with field
names exactly matching the schema definition.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

import pytest
from fastapi.testclient import TestClient
from hypothesis import given, settings
import hypothesis.strategies as st

from quant_ratings.api.app import app
from quant_ratings.api.router import (
    get_rating_engine,
    get_security_registry,
    get_store,
)
from quant_ratings.api.schemas import RatingRecordResponse
from quant_ratings.config.security_registry import SecurityRegistry
from quant_ratings.engine.rating_engine import RatingEngine
from quant_ratings.models.enums import AssetClass
from quant_ratings.models.rating_record import RatingRecord
from quant_ratings.models.security import Security
from quant_ratings.models.weight_profile import WeightProfile
from quant_ratings.persistence.base import RatingStore, StorageError


# ---------------------------------------------------------------------------
# Helpers / shared fixtures
# ---------------------------------------------------------------------------


def _make_weight_profile(
    asset_class: str = "FX",
    sub_category: Optional[str] = "Major",
    sentiment_pct: float = 20.0,
    orderflow_pct: float = 30.0,
    economic_pct: float = 50.0,
) -> WeightProfile:
    return WeightProfile(
        asset_class=asset_class,
        sub_category=sub_category,
        sentiment_pct=sentiment_pct,
        orderflow_pct=orderflow_pct,
        economic_pct=economic_pct,
    )


def _make_record(
    *,
    security_id: str = "EUR/USD",
    asset_class: str = "FX",
    composite_score: float = 3.85,
    rating: str = "Buy",
    sentiment_score: float = 3.2,
    orderflow_score: float = 4.1,
    economic_score: float = 3.9,
    weight_profile: Optional[WeightProfile] = None,
    data_deficient: bool = False,
    computed_at: Optional[datetime] = None,
    record_id: Optional[str] = None,
) -> RatingRecord:
    if weight_profile is None:
        weight_profile = _make_weight_profile()
    if computed_at is None:
        computed_at = datetime(2025, 1, 15, 14, 0, 0, tzinfo=timezone.utc)
    if record_id is None:
        record_id = str(uuid.uuid4())
    return RatingRecord(
        record_id=record_id,
        security_id=security_id,
        asset_class=asset_class,
        composite_score=composite_score,
        rating=rating,
        sentiment_score=sentiment_score,
        orderflow_score=orderflow_score,
        economic_score=economic_score,
        weight_profile=weight_profile,
        data_deficient=data_deficient,
        computed_at=computed_at,
    )


# ---------------------------------------------------------------------------
# Mock store implementations
# ---------------------------------------------------------------------------


class MockStore(RatingStore):
    """Configurable in-memory store for API tests."""

    def __init__(
        self,
        latest: Optional[RatingRecord] = None,
        history: Optional[list[RatingRecord]] = None,
        by_asset_class: Optional[list[RatingRecord]] = None,
        raise_on_get: bool = False,
    ) -> None:
        self._latest = latest
        self._history = history or []
        self._by_asset_class = by_asset_class or []
        self._raise_on_get = raise_on_get

    def save(self, record: RatingRecord) -> None:  # pragma: no cover
        pass

    def get_latest(self, security_id: str) -> Optional[RatingRecord]:
        if self._raise_on_get:
            raise StorageError("store unavailable")
        return self._latest

    def get_history(
        self, security_id: str, from_utc: datetime, to_utc: datetime
    ) -> list[RatingRecord]:
        if self._raise_on_get:
            raise StorageError("store unavailable")
        return self._history

    def get_latest_by_asset_class(self, asset_class) -> list[RatingRecord]:
        if self._raise_on_get:
            raise StorageError("store unavailable")
        return self._by_asset_class


class MockRatingEngine:
    """Minimal RatingEngine stand-in for health-check tests."""

    def __init__(
        self,
        last_successful_cycle_at: Optional[datetime] = None,
        last_cycle_security_count: int = 0,
    ) -> None:
        self.last_successful_cycle_at = last_successful_cycle_at
        self.last_cycle_security_count = last_cycle_security_count


# ---------------------------------------------------------------------------
# Client factory
# ---------------------------------------------------------------------------


def _make_client(
    store: Optional[RatingStore] = None,
    registry: Optional[SecurityRegistry] = None,
    engine: Optional[MockRatingEngine] = None,
) -> TestClient:
    """Build a TestClient with dependency overrides applied."""
    if store is None:
        store = MockStore()
    if registry is None:
        registry = SecurityRegistry()
    if engine is None:
        engine = MockRatingEngine()

    app.dependency_overrides[get_store] = lambda: store
    app.dependency_overrides[get_security_registry] = lambda: registry
    app.dependency_overrides[get_rating_engine] = lambda: engine

    return TestClient(app)


# ---------------------------------------------------------------------------
# Task 15.3 — Property 17: JSON schema completeness
# ---------------------------------------------------------------------------

# Hypothesis strategies for generating RatingRecord instances

_valid_score = st.floats(min_value=0.0, max_value=5.0, allow_nan=False, allow_infinity=False)
_valid_pct = st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False)


@st.composite
def valid_weight_profiles(draw) -> WeightProfile:
    """Generate a WeightProfile whose weights sum to exactly 100.0."""
    s = draw(st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False))
    o = draw(st.floats(min_value=0.0, max_value=100.0 - s, allow_nan=False, allow_infinity=False))
    e = 100.0 - s - o
    return WeightProfile(
        asset_class=draw(st.sampled_from(["FX", "Equity", "Crypto", "Index", "Commodity"])),
        sub_category=draw(st.one_of(st.none(), st.sampled_from(["Major", "Volatile_Cross", "Emerging"]))),
        sentiment_pct=s,
        orderflow_pct=o,
        economic_pct=e,
    )


@st.composite
def rating_records(draw) -> RatingRecord:
    """Generate a random RatingRecord with all required fields populated.

    security_id is constrained to printable ASCII letters, digits, and a
    small set of punctuation characters that are safe to embed in URL paths.
    """
    composite = draw(_valid_score)
    # Map composite to a valid rating label
    if composite >= 4.5:
        rating = "Strong Buy"
    elif composite >= 3.5:
        rating = "Buy"
    elif composite >= 2.5:
        rating = "Neutral"
    elif composite >= 1.5:
        rating = "Sell"
    else:
        rating = "Strong Sell"

    # Use only URL-safe printable characters for security_id so the test
    # client can embed it in a URL path without triggering InvalidURL errors.
    _url_safe_chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~"
    security_id = draw(
        st.text(
            alphabet=st.sampled_from(_url_safe_chars),
            min_size=1,
            max_size=20,
        )
    )

    return RatingRecord(
        record_id=str(uuid.uuid4()),
        security_id=security_id,
        asset_class=draw(st.sampled_from(["FX", "Equity", "Crypto", "Index", "Commodity"])),
        composite_score=composite,
        rating=rating,
        sentiment_score=draw(_valid_score),
        orderflow_score=draw(_valid_score),
        economic_score=draw(_valid_score),
        weight_profile=draw(valid_weight_profiles()),
        data_deficient=draw(st.booleans()),
        computed_at=draw(
            st.datetimes(
                min_value=datetime(2020, 1, 1),
                max_value=datetime(2030, 12, 31),
                timezones=st.just(timezone.utc),
            )
        ),
    )


# Feature: quant-ratings, Property 17: JSON schema completeness
@given(record=rating_records())
@settings(max_examples=100)
def test_json_schema_completeness(record: RatingRecord) -> None:
    """**Validates: Requirements 10.6**

    For any RatingRecord, serialising it via RatingRecordResponse must produce
    a JSON object containing all fields defined in the schema with the correct
    field names.
    """
    # Build the registry with the security so the endpoint doesn't 404
    registry = SecurityRegistry()
    registry.add(
        Security(
            identifier=record.security_id,
            asset_class=AssetClass.FX,  # asset class doesn't matter for this test
        )
    )

    store = MockStore(latest=record)
    client = _make_client(store=store, registry=registry)

    response = client.get(f"/ratings/{record.security_id}/latest")
    assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

    body = response.json()

    # All fields defined in RatingRecordResponse must be present
    expected_fields = set(RatingRecordResponse.model_fields.keys())
    actual_fields = set(body.keys())

    missing = expected_fields - actual_fields
    assert not missing, f"Missing fields in JSON response: {missing}"

    # Nested weight_profile must also contain all expected fields
    from quant_ratings.api.schemas import WeightProfileResponse
    expected_wp_fields = set(WeightProfileResponse.model_fields.keys())
    actual_wp_fields = set(body["weight_profile"].keys())
    missing_wp = expected_wp_fields - actual_wp_fields
    assert not missing_wp, f"Missing weight_profile fields in JSON response: {missing_wp}"


# ---------------------------------------------------------------------------
# Task 15.4 — Unit tests for API endpoints
# ---------------------------------------------------------------------------


def test_get_latest_returns_200() -> None:
    """Mock store returns a record; assert HTTP 200 with correct JSON body.

    Note: security IDs containing '/' cannot be embedded directly in URL
    path segments (Starlette treats %2F as a path separator). Tests use
    slash-free identifiers (e.g. 'AAPL') which are representative of the
    Equity / Crypto asset classes.
    """
    record = _make_record(security_id="AAPL", asset_class="Equity")

    registry = SecurityRegistry()
    registry.add(Security(identifier="AAPL", asset_class=AssetClass.Equity))

    store = MockStore(latest=record)
    client = _make_client(store=store, registry=registry)

    response = client.get("/ratings/AAPL/latest")
    assert response.status_code == 200

    body = response.json()
    assert body["security_id"] == "AAPL"
    assert body["asset_class"] == "Equity"
    assert body["composite_score"] == pytest.approx(3.85)
    assert body["rating"] == "Buy"
    assert body["data_deficient"] is False
    assert "weight_profile" in body
    assert body["weight_profile"]["asset_class"] == "FX"
    assert body["weight_profile"]["sentiment_pct"] == pytest.approx(20.0)
    assert body["weight_profile"]["orderflow_pct"] == pytest.approx(30.0)
    assert body["weight_profile"]["economic_pct"] == pytest.approx(50.0)


def test_unknown_security_returns_404() -> None:
    """Security not in registry; assert HTTP 404 with SECURITY_NOT_FOUND."""
    registry = SecurityRegistry()  # empty — no securities registered
    store = MockStore()
    client = _make_client(store=store, registry=registry)

    response = client.get("/ratings/UNKNOWN/latest")
    assert response.status_code == 404

    body = response.json()
    # FastAPI wraps HTTPException detail in {"detail": ...}
    detail = body.get("detail", body)
    assert detail["code"] == "SECURITY_NOT_FOUND"


def test_store_failure_returns_503() -> None:
    """Store raises StorageError; assert HTTP 503 with STORE_UNAVAILABLE."""
    registry = SecurityRegistry()
    registry.add(Security(identifier="AAPL", asset_class=AssetClass.Equity))

    store = MockStore(raise_on_get=True)
    client = _make_client(store=store, registry=registry)

    response = client.get("/ratings/AAPL/latest")
    assert response.status_code == 503

    body = response.json()
    detail = body.get("detail", body)
    assert detail["code"] == "STORE_UNAVAILABLE"


def test_health_endpoint() -> None:
    """Assert HTTP 200 with last_successful_cycle_at and securities_rated fields."""
    last_cycle = datetime(2025, 1, 15, 14, 0, 0, tzinfo=timezone.utc)
    engine = MockRatingEngine(
        last_successful_cycle_at=last_cycle,
        last_cycle_security_count=42,
    )
    client = _make_client(engine=engine)

    response = client.get("/health")
    assert response.status_code == 200

    body = response.json()
    assert "last_successful_cycle_at" in body
    assert "securities_rated" in body
    assert body["securities_rated"] == 42
    assert body["status"] == "ok"
    # Verify the timestamp is present and parseable
    assert body["last_successful_cycle_at"] is not None
    parsed = datetime.fromisoformat(body["last_successful_cycle_at"].replace("Z", "+00:00"))
    assert parsed.year == 2025


def test_health_endpoint_degraded_when_no_cycle() -> None:
    """Health endpoint returns 'degraded' when no cycle has run yet."""
    engine = MockRatingEngine(last_successful_cycle_at=None, last_cycle_security_count=0)
    client = _make_client(engine=engine)

    response = client.get("/health")
    assert response.status_code == 200

    body = response.json()
    assert body["status"] == "degraded"
    assert body["last_successful_cycle_at"] is None
    assert body["securities_rated"] == 0


def test_get_history_returns_records() -> None:
    """History endpoint returns list of records for a known security."""
    record = _make_record(security_id="AAPL", asset_class="Equity")

    registry = SecurityRegistry()
    registry.add(Security(identifier="AAPL", asset_class=AssetClass.Equity))

    store = MockStore(history=[record])
    client = _make_client(store=store, registry=registry)

    response = client.get(
        "/ratings/AAPL/history",
        params={"from_dt": "2025-01-01T00:00:00+00:00", "to_dt": "2025-12-31T00:00:00+00:00"},
    )
    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, list)
    assert len(body) == 1
    assert body[0]["security_id"] == "AAPL"


def test_get_history_invalid_date_returns_400() -> None:
    """Malformed date parameter returns HTTP 400 with INVALID_PARAMETERS."""
    registry = SecurityRegistry()
    registry.add(Security(identifier="AAPL", asset_class=AssetClass.Equity))

    store = MockStore()
    client = _make_client(store=store, registry=registry)

    response = client.get(
        "/ratings/AAPL/history",
        params={"from_dt": "not-a-date"},
    )
    assert response.status_code == 400

    body = response.json()
    detail = body.get("detail", body)
    assert detail["code"] == "INVALID_PARAMETERS"


def test_get_latest_by_asset_class_returns_200() -> None:
    """Asset-class endpoint returns list of records for a valid asset class."""
    record = _make_record(security_id="EUR/USD", asset_class="FX")

    store = MockStore(by_asset_class=[record])
    client = _make_client(store=store)

    response = client.get("/ratings/asset-class/FX/latest")
    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, list)
    assert len(body) == 1
    assert body[0]["asset_class"] == "FX"


def test_get_latest_by_unknown_asset_class_returns_404() -> None:
    """Unknown asset class string returns HTTP 404 with ASSET_CLASS_NOT_FOUND."""
    store = MockStore()
    client = _make_client(store=store)

    response = client.get("/ratings/asset-class/UnknownClass/latest")
    assert response.status_code == 404

    body = response.json()
    detail = body.get("detail", body)
    assert detail["code"] == "ASSET_CLASS_NOT_FOUND"
