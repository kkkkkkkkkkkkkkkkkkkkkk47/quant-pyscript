"""Tests for the RatingEngine — property-based and unit tests.

Feature: quant-ratings
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

import pytest
from hypothesis import given, settings
import hypothesis.strategies as st

from quant_ratings.aggregator.aggregator import Aggregator
from quant_ratings.config.security_registry import SecurityRegistry
from quant_ratings.config.weight_profile_registry import WeightProfileRegistry
from quant_ratings.engine.data_manager import DataManager
from quant_ratings.engine.rating_engine import RatingEngine
from quant_ratings.models.enums import AssetClass
from quant_ratings.models.rating_record import RatingRecord
from quant_ratings.models.security import Security
from quant_ratings.models.weight_profile import WeightProfile
from quant_ratings.observability.alert_sink import AlertSink
from quant_ratings.persistence.base import RatingStore, StorageError
from quant_ratings.providers.mock_provider import MockDataProvider
from quant_ratings.scorers.economic_scorer import EconomicScorer
from quant_ratings.scorers.orderflow_scorer import OrderFlowScorer
from quant_ratings.scorers.sentiment_scorer import SentimentScorer


# ---------------------------------------------------------------------------
# Shared mock implementations
# ---------------------------------------------------------------------------

class InMemoryStore(RatingStore):
    """Simple in-memory RatingStore for testing."""

    def __init__(self) -> None:
        self.records: list[RatingRecord] = []

    def save(self, record: RatingRecord) -> None:
        self.records.append(record)

    def get_latest(self, security_id: str) -> Optional[RatingRecord]:
        matches = [r for r in self.records if r.security_id == security_id]
        return matches[-1] if matches else None

    def get_history(self, security_id: str, from_utc: datetime, to_utc: datetime) -> list[RatingRecord]:
        return [
            r for r in self.records
            if r.security_id == security_id and from_utc <= r.computed_at < to_utc
        ]

    def get_latest_by_asset_class(self, asset_class: AssetClass) -> list[RatingRecord]:
        return [r for r in self.records if r.asset_class == asset_class.value]


class RecordingAlertSink(AlertSink):
    """AlertSink that records all high-severity alerts for inspection."""

    def __init__(self) -> None:
        self.alerts: list[tuple[str, str]] = []

    def send_high_severity(self, title: str, body: str) -> None:
        self.alerts.append((title, body))


class FailOnceThenSucceedStore(RatingStore):
    """Store that raises StorageError on the first save, then succeeds."""

    def __init__(self) -> None:
        self.call_count: int = 0
        self.records: list[RatingRecord] = []

    def save(self, record: RatingRecord) -> None:
        self.call_count += 1
        if self.call_count == 1:
            raise StorageError("first attempt fails")
        self.records.append(record)

    def get_latest(self, security_id: str) -> Optional[RatingRecord]:
        matches = [r for r in self.records if r.security_id == security_id]
        return matches[-1] if matches else None

    def get_history(self, security_id: str, from_utc: datetime, to_utc: datetime) -> list[RatingRecord]:
        return []

    def get_latest_by_asset_class(self, asset_class: AssetClass) -> list[RatingRecord]:
        return []


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _make_engine(
    security_registry: SecurityRegistry,
    weight_registry: Optional[WeightProfileRegistry] = None,
    provider: Optional[MockDataProvider] = None,
    store: Optional[RatingStore] = None,
    alert_sink: Optional[AlertSink] = None,
) -> RatingEngine:
    """Build a RatingEngine with sensible defaults for testing."""
    if weight_registry is None:
        weight_registry = WeightProfileRegistry()
    if provider is None:
        provider = MockDataProvider()
    if store is None:
        store = InMemoryStore()
    if alert_sink is None:
        alert_sink = RecordingAlertSink()

    data_manager = DataManager(providers=[provider])
    return RatingEngine(
        security_registry=security_registry,
        weight_registry=weight_registry,
        data_manager=data_manager,
        sentiment_scorer=SentimentScorer(),
        orderflow_scorer=OrderFlowScorer(),
        economic_scorer=EconomicScorer(),
        aggregator=Aggregator(),
        store=store,
        alert_sink=alert_sink,
    )


def _make_security(identifier: str, asset_class: AssetClass = AssetClass.FX) -> Security:
    return Security(identifier=identifier, asset_class=asset_class)


# Strategy: generate N unique security identifiers (N in [1, 10])
@st.composite
def security_registries(draw) -> SecurityRegistry:
    n = draw(st.integers(min_value=1, max_value=10))
    identifiers = draw(
        st.lists(
            st.text(alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd"), whitelist_characters="/_-"), min_size=1, max_size=10),
            min_size=n,
            max_size=n,
            unique=True,
        )
    )
    registry = SecurityRegistry()
    for ident in identifiers:
        registry.add(Security(identifier=ident, asset_class=AssetClass.FX))
    return registry


# ---------------------------------------------------------------------------
# Task 11.2 — Property 12: Every registered security produces a RatingRecord per cycle
# ---------------------------------------------------------------------------

# Feature: quant-ratings, Property 12: All securities rated
@given(registry=security_registries())
def test_all_securities_rated_per_cycle(registry: SecurityRegistry) -> None:
    """**Validates: Requirements 6.4, 8.1**

    For any SecurityRegistry with N securities (N in [1, 10]) and a
    MockDataProvider (all data None → all scorers fall back to neutral),
    records_produced + failures must equal N after run_cycle().
    """
    n = len(registry.all_securities())
    store = InMemoryStore()
    engine = _make_engine(registry, store=store)

    summary = engine.run_cycle()

    assert summary.records_produced + summary.failures == n


# ---------------------------------------------------------------------------
# Task 11.3 — Property 14: RatingRecord schema is always complete
# ---------------------------------------------------------------------------

# Feature: quant-ratings, Property 14: RatingRecord schema
@given(registry=security_registries())
def test_rating_record_schema_complete(registry: SecurityRegistry) -> None:
    """**Validates: Requirements 8.2**

    For any security processed by run_cycle(), all required fields on the
    returned RatingRecord must be present and non-None.
    """
    store = InMemoryStore()
    engine = _make_engine(registry, store=store)

    engine.run_cycle()

    required_fields = [
        "record_id",
        "security_id",
        "asset_class",
        "composite_score",
        "rating",
        "sentiment_score",
        "orderflow_score",
        "economic_score",
        "weight_profile",
        "data_deficient",
        "computed_at",
    ]

    for record in store.records:
        for field_name in required_fields:
            value = getattr(record, field_name, None)
            assert value is not None, (
                f"Field '{field_name}' is None on RatingRecord for security "
                f"'{record.security_id}'"
            )


# ---------------------------------------------------------------------------
# Task 11.4 — Property 16: High data-deficiency rate triggers a high-severity alert
# ---------------------------------------------------------------------------

# Feature: quant-ratings, Property 16: Alert threshold
@given(registry=security_registries())
def test_high_deficiency_rate_triggers_alert(registry: SecurityRegistry) -> None:
    """**Validates: Requirements 11.2**

    When a MockDataProvider returns None for all data types (all scorers fall
    back → data_deficient=True for every security), the deficiency rate is
    100% > 20%, so AlertSink must receive exactly one high-severity alert
    before the cycle summary is finalised.
    """
    # MockDataProvider with all defaults (None) → all scorers fall back
    provider = MockDataProvider()
    alert_sink = RecordingAlertSink()
    engine = _make_engine(registry, provider=provider, alert_sink=alert_sink)

    engine.run_cycle()

    assert len(alert_sink.alerts) == 1, (
        f"Expected exactly 1 high-severity alert, got {len(alert_sink.alerts)}"
    )


# ---------------------------------------------------------------------------
# Task 11.5 — Unit tests
# ---------------------------------------------------------------------------

def test_storage_error_triggers_one_retry() -> None:
    """**Validates: Requirements 8.4**

    A store that raises StorageError on the first save but succeeds on the
    second must have save() called exactly twice.
    """
    registry = SecurityRegistry()
    registry.add(_make_security("EUR/USD", AssetClass.FX))

    store = FailOnceThenSucceedStore()
    engine = _make_engine(registry, store=store)

    summary = engine.run_cycle()

    # The record should have been saved successfully on the second attempt
    assert store.call_count == 2
    assert summary.records_produced == 1
    assert summary.failures == 0


def test_all_fallback_produces_data_deficient_neutral() -> None:
    """**Validates: Requirements 9.5**

    When MockDataProvider returns None for all data types, all three scorers
    fall back to neutral (2.5), so the resulting RatingRecord must have
    data_deficient=True and rating="Neutral".
    """
    registry = SecurityRegistry()
    registry.add(_make_security("EUR/USD", AssetClass.FX))

    store = InMemoryStore()
    # MockDataProvider with all defaults (None) → all scorers fall back
    provider = MockDataProvider()
    engine = _make_engine(registry, provider=provider, store=store)

    engine.run_cycle()

    assert len(store.records) == 1
    record = store.records[0]
    assert record.data_deficient is True
    assert record.rating == "Neutral"


def test_weight_profile_error_skips_security_increments_failures() -> None:
    """**Validates: Requirements 8.4**

    When a WeightProfile with invalid weights (not summing to 100%) is
    registered for a security's asset class, the Aggregator raises
    WeightProfileError. The RatingEngine must catch this, skip the security,
    and increment failures by 1.
    """
    registry = SecurityRegistry()
    # Use a custom asset class string that won't match any default profile
    security = Security(identifier="TEST/ASSET", asset_class=AssetClass.Equity)
    registry.add(security)

    # Register an invalid weight profile for Equity (10+10+10 = 30 ≠ 100)
    weight_registry = WeightProfileRegistry()
    invalid_profile = WeightProfile(
        asset_class="Equity",
        sub_category=None,
        sentiment_pct=10.0,
        orderflow_pct=10.0,
        economic_pct=10.0,
    )
    weight_registry.register(invalid_profile)

    store = InMemoryStore()
    engine = _make_engine(registry, weight_registry=weight_registry, store=store)

    summary = engine.run_cycle()

    # The security should have been skipped due to WeightProfileError
    assert summary.failures == 1
    assert summary.records_produced == 0
    assert len(store.records) == 0
