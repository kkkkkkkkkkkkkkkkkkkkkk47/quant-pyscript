"""Integration tests for the Quant Ratings engine.

Tasks 18.1, 18.2, 18.3 — end-to-end cycle, API ↔ store, and scheduler cadence.

Requirements: 1.1, 6.4, 7.1, 8.1, 8.2, 10.1, 10.2, 10.3, 10.6
"""

from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone
from typing import Optional

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from quant_ratings.aggregator.aggregator import Aggregator
from quant_ratings.api.app import app
from quant_ratings.api.router import get_rating_engine, get_security_registry, get_store
from quant_ratings.config.security_registry import SecurityRegistry
from quant_ratings.config.weight_profile_registry import WeightProfileRegistry
from quant_ratings.engine.data_manager import DataManager
from quant_ratings.engine.rating_engine import RatingEngine
from quant_ratings.models.cycle_summary import CycleSummary
from quant_ratings.models.enums import AssetClass
from quant_ratings.models.market_data import MacroData, RetailPositioning, TickVolumeData
from quant_ratings.models.rating_record import RatingRecord
from quant_ratings.models.security import Security
from quant_ratings.models.weight_profile import WeightProfile
from quant_ratings.observability.alert_sink import LogAlertSink
from quant_ratings.persistence.orm import Base
from quant_ratings.persistence.sqlalchemy_store import SQLAlchemyRatingStore
from quant_ratings.providers.mock_provider import MockDataProvider
from quant_ratings.scheduler.scheduler import Scheduler, SchedulerConfig
from quant_ratings.scorers.economic_scorer import EconomicScorer
from quant_ratings.scorers.orderflow_scorer import OrderFlowScorer
from quant_ratings.scorers.sentiment_scorer import SentimentScorer


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _make_in_memory_store() -> SQLAlchemyRatingStore:
    """Create a fresh in-memory SQLite store with all tables created.

    Uses StaticPool so that all SQLAlchemy sessions share the same underlying
    connection — required for in-memory SQLite where each new connection would
    otherwise get a fresh empty database.
    """
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    return SQLAlchemyRatingStore(engine)


def _make_fx_major_security(identifier: str) -> Security:
    return Security(
        identifier=identifier,
        asset_class=AssetClass.FX,
        sub_category="Major",
    )


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


def _make_rating_record(
    *,
    security_id: str,
    asset_class: str = "FX",
    composite_score: float = 3.85,
    rating: str = "Buy",
    sentiment_score: float = 2.0,
    orderflow_score: float = 4.0,
    economic_score: float = 4.5,
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
# Task 18.1 — End-to-end cycle integration test
# Requirements: 1.1, 6.4, 8.1, 8.2
# ---------------------------------------------------------------------------

class TestEndToEndCycle:
    """End-to-end test: RatingEngine.run_cycle() with real SQLAlchemyRatingStore.

    Deterministic data:
      - vix=25.0 (below 30, no VIX amplification)
      - audjpy=85.0 (above 80.0 threshold → risk-on)
      - retail_positioning: long_pct=0.6, short_pct=0.4
          → base_score = 5.0 * (1 - 0.6) = 2.0  (no extreme threshold hit)
          → sentiment = 2.0
      - tick_volume: current=200, avg_20_period=100, price_broke_4h_resistance=True
          → volume_rising=True, breakout confirmed → orderflow = 4.0
      - macro: pmi=55 > prior_pmi=50 (improving), cpi=3.0 > prior_cpi=2.5 (improving),
               central_bank_stance="hawkish", interest_rate_differential=None
          → full-bull: economic = 4.5

    FX Major weights: sentiment=20%, orderflow=30%, economic=50%
      composite = 2.0*0.20 + 4.0*0.30 + 4.5*0.50
               = 0.40 + 1.20 + 2.25 = 3.85 → "Buy"
    """

    def _build_engine(
        self,
        store: SQLAlchemyRatingStore,
        registry: SecurityRegistry,
    ) -> RatingEngine:
        now = datetime.now(timezone.utc)

        provider = MockDataProvider(
            vix=25.0,
            audjpy=85.0,
            retail_positioning=RetailPositioning(
                long_pct=0.6,
                short_pct=0.4,
                timestamp=now,
            ),
            tick_volume=TickVolumeData(
                current=200.0,
                avg_20_period=100.0,
                price_broke_4h_resistance=True,
                timestamp=now,
            ),
            macro=MacroData(
                pmi=55.0,
                prior_pmi=50.0,
                cpi=3.0,
                prior_cpi=2.5,
                central_bank_stance="hawkish",
                interest_rate_differential=None,
                timestamp=now,
            ),
        )

        data_manager = DataManager(providers=[provider])
        weight_registry = WeightProfileRegistry()  # pre-seeded with FX Major (20/30/50)

        return RatingEngine(
            security_registry=registry,
            weight_registry=weight_registry,
            data_manager=data_manager,
            sentiment_scorer=SentimentScorer(),
            orderflow_scorer=OrderFlowScorer(),
            economic_scorer=EconomicScorer(),
            aggregator=Aggregator(),
            store=store,
            alert_sink=LogAlertSink(),
        )

    def test_run_cycle_persists_correct_scores_and_rating(self) -> None:
        """run_cycle() persists RatingRecords with expected composite scores and labels.

        Validates: Requirements 1.1, 6.4, 8.1, 8.2
        """
        store = _make_in_memory_store()

        registry = SecurityRegistry()
        registry.add(_make_fx_major_security("EUR/USD"))
        registry.add(_make_fx_major_security("GBP/USD"))

        engine = self._build_engine(store, registry)
        summary = engine.run_cycle()

        # Cycle summary assertions
        assert summary.securities_attempted == 2
        assert summary.records_produced == 2
        assert summary.failures == 0
        assert summary.timed_out is False
        assert summary.completed_at is not None

        # Verify persisted records for each security
        for security_id in ("EUR/USD", "GBP/USD"):
            record = store.get_latest(security_id)
            assert record is not None, f"No record found for {security_id}"

            # Schema completeness (Requirement 8.2)
            assert record.record_id is not None
            assert record.security_id == security_id
            assert record.asset_class == "FX"
            assert record.weight_profile is not None
            assert record.computed_at is not None
            assert record.data_deficient is False

            # Sub-scores
            assert record.sentiment_score == pytest.approx(2.0, abs=1e-6), (
                f"Expected sentiment_score=2.0 for {security_id}, got {record.sentiment_score}"
            )
            assert record.orderflow_score == pytest.approx(4.0, abs=1e-6), (
                f"Expected orderflow_score=4.0 for {security_id}, got {record.orderflow_score}"
            )
            assert record.economic_score == pytest.approx(4.5, abs=1e-6), (
                f"Expected economic_score=4.5 for {security_id}, got {record.economic_score}"
            )

            # Composite score: 2.0*0.20 + 4.0*0.30 + 4.5*0.50 = 3.85
            assert record.composite_score == pytest.approx(3.85, abs=1e-6), (
                f"Expected composite_score=3.85 for {security_id}, got {record.composite_score}"
            )
            assert record.rating == "Buy", (
                f"Expected rating='Buy' for {security_id}, got {record.rating!r}"
            )

    def test_run_cycle_records_have_distinct_record_ids(self) -> None:
        """Each persisted RatingRecord must have a unique record_id (UUID).

        Validates: Requirements 8.2
        """
        store = _make_in_memory_store()

        registry = SecurityRegistry()
        registry.add(_make_fx_major_security("EUR/USD"))
        registry.add(_make_fx_major_security("GBP/USD"))

        engine = self._build_engine(store, registry)
        engine.run_cycle()

        record_eurusd = store.get_latest("EUR/USD")
        record_gbpusd = store.get_latest("GBP/USD")

        assert record_eurusd is not None
        assert record_gbpusd is not None
        assert record_eurusd.record_id != record_gbpusd.record_id

    def test_run_cycle_empty_registry_produces_no_records(self) -> None:
        """An empty SecurityRegistry produces a cycle with zero records.

        Validates: Requirements 6.4, 8.1
        """
        store = _make_in_memory_store()
        registry = SecurityRegistry()  # empty

        engine = self._build_engine(store, registry)
        summary = engine.run_cycle()

        assert summary.securities_attempted == 0
        assert summary.records_produced == 0
        assert summary.failures == 0


# ---------------------------------------------------------------------------
# Task 18.2 — API ↔ Store integration test
# Requirements: 10.1, 10.2, 10.3, 10.6
# ---------------------------------------------------------------------------

class TestAPIStoreIntegration:
    """Integration tests: FastAPI endpoints backed by a real SQLAlchemyRatingStore.

    Uses the real store with in-memory SQLite and overrides FastAPI dependencies
    to inject the real store and a real SecurityRegistry.

    Note: Security IDs containing '/' cannot be embedded in URL path segments
    (Starlette treats %2F as a path separator). Tests use slash-free identifiers
    such as "EURUSD" and "GBPUSD" which are representative FX identifiers.
    """

    def _setup(self) -> tuple[SQLAlchemyRatingStore, SecurityRegistry, TestClient]:
        """Create a store, registry, and TestClient with dependency overrides."""
        store = _make_in_memory_store()

        registry = SecurityRegistry()
        # Use slash-free identifiers so they can be embedded in URL path segments
        registry.add(Security(identifier="EURUSD", asset_class=AssetClass.FX, sub_category="Major"))
        registry.add(Security(identifier="GBPUSD", asset_class=AssetClass.FX, sub_category="Major"))

        # Minimal mock engine for health endpoint (not under test here)
        class _MinimalEngine:
            last_successful_cycle_at: Optional[datetime] = None
            last_cycle_security_count: int = 0

        app.dependency_overrides[get_store] = lambda: store
        app.dependency_overrides[get_security_registry] = lambda: registry
        app.dependency_overrides[get_rating_engine] = lambda: _MinimalEngine()

        client = TestClient(app)
        return store, registry, client

    def _teardown(self) -> None:
        """Remove dependency overrides after each test."""
        app.dependency_overrides.pop(get_store, None)
        app.dependency_overrides.pop(get_security_registry, None)
        app.dependency_overrides.pop(get_rating_engine, None)

    def test_get_latest_returns_persisted_record(self) -> None:
        """GET /ratings/{security_id}/latest returns the persisted record.

        Validates: Requirements 10.1, 10.6
        """
        store, registry, client = self._setup()
        try:
            record = _make_rating_record(
                security_id="EURUSD",
                composite_score=3.85,
                rating="Buy",
                sentiment_score=2.0,
                orderflow_score=4.0,
                economic_score=4.5,
            )
            store.save(record)

            response = client.get("/ratings/EURUSD/latest")
            assert response.status_code == 200, (
                f"Expected 200, got {response.status_code}: {response.text}"
            )

            body = response.json()
            assert body["security_id"] == "EURUSD"
            assert body["asset_class"] == "FX"
            assert body["composite_score"] == pytest.approx(3.85, abs=1e-4)
            assert body["rating"] == "Buy"
            assert body["sentiment_score"] == pytest.approx(2.0, abs=1e-4)
            assert body["orderflow_score"] == pytest.approx(4.0, abs=1e-4)
            assert body["economic_score"] == pytest.approx(4.5, abs=1e-4)
            assert body["data_deficient"] is False
            assert body["record_id"] == record.record_id

            # Verify all required fields are present (Requirement 10.6)
            required_fields = {
                "record_id", "security_id", "asset_class", "composite_score",
                "rating", "sentiment_score", "orderflow_score", "economic_score",
                "weight_profile", "data_deficient", "computed_at",
            }
            assert required_fields.issubset(set(body.keys())), (
                f"Missing fields: {required_fields - set(body.keys())}"
            )

            # Verify weight_profile fields
            wp = body["weight_profile"]
            assert wp["asset_class"] == "FX"
            assert wp["sub_category"] == "Major"
            assert wp["sentiment_pct"] == pytest.approx(20.0, abs=1e-4)
            assert wp["orderflow_pct"] == pytest.approx(30.0, abs=1e-4)
            assert wp["economic_pct"] == pytest.approx(50.0, abs=1e-4)
        finally:
            self._teardown()

    def test_get_history_returns_record_within_time_range(self) -> None:
        """GET /ratings/{security_id}/history returns the persisted record within range.

        Validates: Requirements 10.2, 10.6
        """
        store, registry, client = self._setup()
        try:
            computed_at = datetime(2025, 6, 15, 12, 0, 0, tzinfo=timezone.utc)
            record = _make_rating_record(
                security_id="EURUSD",
                computed_at=computed_at,
            )
            store.save(record)

            response = client.get(
                "/ratings/EURUSD/history",
                params={
                    "from_dt": "2025-06-01T00:00:00+00:00",
                    "to_dt": "2025-07-01T00:00:00+00:00",
                },
            )
            assert response.status_code == 200, (
                f"Expected 200, got {response.status_code}: {response.text}"
            )

            body = response.json()
            assert isinstance(body, list)
            assert len(body) == 1
            assert body[0]["security_id"] == "EURUSD"
            assert body[0]["record_id"] == record.record_id

        finally:
            self._teardown()

    def test_get_history_excludes_records_outside_range(self) -> None:
        """GET /ratings/{security_id}/history excludes records outside the time range.

        Validates: Requirements 10.2
        """
        store, registry, client = self._setup()
        try:
            # Record before the query range
            record_before = _make_rating_record(
                security_id="EURUSD",
                computed_at=datetime(2025, 5, 1, 0, 0, 0, tzinfo=timezone.utc),
            )
            # Record inside the query range
            record_inside = _make_rating_record(
                security_id="EURUSD",
                computed_at=datetime(2025, 6, 15, 12, 0, 0, tzinfo=timezone.utc),
            )
            store.save(record_before)
            store.save(record_inside)

            response = client.get(
                "/ratings/EURUSD/history",
                params={
                    "from_dt": "2025-06-01T00:00:00+00:00",
                    "to_dt": "2025-07-01T00:00:00+00:00",
                },
            )
            assert response.status_code == 200

            body = response.json()
            assert len(body) == 1
            assert body[0]["record_id"] == record_inside.record_id

        finally:
            self._teardown()

    def test_get_latest_by_asset_class_returns_all_fx_records(self) -> None:
        """GET /ratings/asset-class/FX/latest returns records for all FX securities.

        Validates: Requirements 10.3, 10.6
        """
        store, registry, client = self._setup()
        try:
            record_eur = _make_rating_record(
                security_id="EURUSD",
                composite_score=3.85,
                rating="Buy",
            )
            record_gbp = _make_rating_record(
                security_id="GBPUSD",
                composite_score=3.85,
                rating="Buy",
            )
            store.save(record_eur)
            store.save(record_gbp)

            response = client.get("/ratings/asset-class/FX/latest")
            assert response.status_code == 200, (
                f"Expected 200, got {response.status_code}: {response.text}"
            )

            body = response.json()
            assert isinstance(body, list)
            assert len(body) == 2

            returned_ids = {r["security_id"] for r in body}
            assert returned_ids == {"EURUSD", "GBPUSD"}

            # All records must have asset_class == "FX"
            for r in body:
                assert r["asset_class"] == "FX"

        finally:
            self._teardown()

    def test_get_latest_by_asset_class_returns_only_most_recent(self) -> None:
        """GET /ratings/asset-class/FX/latest returns only the most recent record per security.

        Validates: Requirements 10.3
        """
        store, registry, client = self._setup()
        try:
            older = _make_rating_record(
                security_id="EURUSD",
                composite_score=2.5,
                rating="Neutral",
                computed_at=datetime(2025, 6, 1, 0, 0, 0, tzinfo=timezone.utc),
            )
            newer = _make_rating_record(
                security_id="EURUSD",
                composite_score=3.85,
                rating="Buy",
                computed_at=datetime(2025, 6, 15, 0, 0, 0, tzinfo=timezone.utc),
            )
            store.save(older)
            store.save(newer)

            response = client.get("/ratings/asset-class/FX/latest")
            assert response.status_code == 200

            body = response.json()
            # Only one record for EURUSD (the most recent)
            eur_records = [r for r in body if r["security_id"] == "EURUSD"]
            assert len(eur_records) == 1
            assert eur_records[0]["record_id"] == newer.record_id
            assert eur_records[0]["rating"] == "Buy"

        finally:
            self._teardown()

    def test_get_latest_unknown_security_returns_404(self) -> None:
        """GET /ratings/{security_id}/latest returns 404 for unknown security.

        Validates: Requirements 10.1
        """
        store, registry, client = self._setup()
        try:
            response = client.get("/ratings/UNKNOWN/latest")
            assert response.status_code == 404

            body = response.json()
            detail = body.get("detail", body)
            assert detail["code"] == "SECURITY_NOT_FOUND"

        finally:
            self._teardown()


# ---------------------------------------------------------------------------
# Task 18.3 — Scheduler cadence integration test
# Requirements: 7.1
# ---------------------------------------------------------------------------

class _RecordingEngine:
    """Mock engine that records each run_cycle() call with its timestamp."""

    def __init__(self) -> None:
        self.cycle_summaries: list[CycleSummary] = []
        self._security_registry = _FakeRegistry()

    def run_cycle(self) -> CycleSummary:
        started_at = datetime.now(timezone.utc)
        # Small sleep to ensure distinct timestamps
        time.sleep(0.01)
        completed_at = datetime.now(timezone.utc)
        summary = CycleSummary(
            started_at=started_at,
            completed_at=completed_at,
            securities_attempted=0,
            records_produced=0,
            failures=0,
        )
        self.cycle_summaries.append(summary)
        return summary


class _FakeRegistry:
    """Minimal registry stub for the scheduler's security_count log."""

    def all_securities(self) -> list:
        return []


class TestSchedulerCadence:
    """Scheduler cadence integration test.

    Validates: Requirements 7.1
    """

    def test_scheduler_produces_at_least_two_cycles(self) -> None:
        """Scheduler with interval=0 produces ≥2 distinct CycleSummary records in 1.5s.

        interval_seconds=0 causes threading.Timer to fire immediately after each
        cycle completes, so cycles accumulate quickly.  The 0.01s sleep inside
        _RecordingEngine.run_cycle() ensures timestamps are distinct and prevents
        a true busy-loop.

        Start the scheduler, wait ~1.5 seconds, stop it, and assert at least two
        summaries with distinct started_at timestamps were recorded.

        Validates: Requirements 7.1
        """
        engine = _RecordingEngine()
        # interval_seconds=0 → timer fires immediately after each cycle
        config = SchedulerConfig(interval_seconds=0, timeout_seconds=30)
        scheduler = Scheduler(engine=engine, config=config)

        scheduler.start()
        time.sleep(1.5)
        scheduler.stop()

        summaries = engine.cycle_summaries
        assert len(summaries) >= 2, (
            f"Expected at least 2 cycle summaries, got {len(summaries)}"
        )

        # All started_at timestamps must be distinct
        started_ats = [s.started_at for s in summaries]
        assert len(set(started_ats)) == len(started_ats), (
            "Expected all started_at timestamps to be distinct"
        )

        # Verify the second cycle started after the first
        first_start = summaries[0].started_at
        second_start = summaries[1].started_at
        assert second_start > first_start, (
            f"Expected second cycle to start after first: "
            f"{first_start.isoformat()} vs {second_start.isoformat()}"
        )

    def test_scheduler_stops_after_stop_called(self) -> None:
        """After stop(), no further cycles are triggered.

        Validates: Requirements 7.1
        """
        engine = _RecordingEngine()
        config = SchedulerConfig(interval_seconds=0, timeout_seconds=30)
        scheduler = Scheduler(engine=engine, config=config)

        scheduler.start()
        time.sleep(0.5)
        scheduler.stop()

        # Allow any in-flight cycle (already running when stop() was called)
        # to complete before taking the snapshot.
        time.sleep(0.1)
        count_at_stop = len(engine.cycle_summaries)

        # Wait another 0.5s and verify no new cycles were triggered
        time.sleep(0.5)
        count_after_wait = len(engine.cycle_summaries)

        assert count_after_wait == count_at_stop, (
            f"Expected no new cycles after stop(), but count went from "
            f"{count_at_stop} to {count_after_wait}"
        )
