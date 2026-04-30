"""Property and unit tests for the SQLAlchemy persistence layer.

Feature: quant-ratings, Property 13: Historical retention

**Validates: Requirements 8.3**

Property 13: Historical records are never overwritten.
For any security, after K successive computation cycles, the RatingStore must
contain at least K RatingRecords for that security, each with a distinct
``computed_at`` timestamp.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional

import pytest
from hypothesis import given, settings
import hypothesis.strategies as st
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError

from quant_ratings.models.rating_record import RatingRecord
from quant_ratings.models.weight_profile import WeightProfile
from quant_ratings.persistence.base import StorageError
from quant_ratings.persistence.sqlalchemy_store import SQLAlchemyRatingStore


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_weight_profile() -> WeightProfile:
    return WeightProfile(
        asset_class="FX",
        sub_category="Major",
        sentiment_pct=20.0,
        orderflow_pct=30.0,
        economic_pct=50.0,
    )


def _make_record(
    *,
    security_id: str = "EUR/USD",
    asset_class: str = "FX",
    computed_at: Optional[datetime] = None,
    record_id: Optional[str] = None,
) -> RatingRecord:
    if computed_at is None:
        computed_at = datetime.now(timezone.utc)
    if record_id is None:
        record_id = str(uuid.uuid4())
    return RatingRecord(
        record_id=record_id,
        security_id=security_id,
        asset_class=asset_class,
        composite_score=3.5,
        rating="Buy",
        sentiment_score=3.2,
        orderflow_score=4.1,
        economic_score=3.9,
        weight_profile=_make_weight_profile(),
        data_deficient=False,
        computed_at=computed_at,
    )


def _make_store() -> SQLAlchemyRatingStore:
    """Return a fresh in-memory SQLite store for each test."""
    engine = create_engine("sqlite:///:memory:")
    return SQLAlchemyRatingStore(engine)


# ---------------------------------------------------------------------------
# Property 13: Historical records are never overwritten
# ---------------------------------------------------------------------------

@given(k=st.integers(min_value=2, max_value=10))
@settings(max_examples=50)
def test_historical_records_never_overwritten(k: int) -> None:
    """Feature: quant-ratings, Property 13: Historical retention

    **Validates: Requirements 8.3**

    Run K successive save() calls for the same security with distinct
    computed_at timestamps; assert the store contains at least K records
    each with a unique timestamp.
    """
    store = _make_store()
    security_id = "EUR/USD"

    # Generate K distinct timestamps spaced 1 hour apart
    base_time = datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    timestamps = [base_time + timedelta(hours=i) for i in range(k)]

    for ts in timestamps:
        record = _make_record(security_id=security_id, computed_at=ts)
        store.save(record)

    # Retrieve the full history covering all saved records
    from_utc = base_time
    to_utc = base_time + timedelta(hours=k)  # exclusive upper bound
    history = store.get_history(security_id, from_utc, to_utc)

    # Must have at least K records
    assert len(history) >= k, (
        f"Expected at least {k} records, got {len(history)}"
    )

    # All computed_at timestamps must be distinct
    seen_timestamps = {r.computed_at for r in history}
    assert len(seen_timestamps) == len(history), (
        "Duplicate computed_at timestamps found — records were overwritten"
    )


# ---------------------------------------------------------------------------
# Unit tests for SQLAlchemyRatingStore
# ---------------------------------------------------------------------------

class TestGetLatestReturnsMostRecent:
    """test_get_latest_returns_most_recent"""

    def test_get_latest_returns_most_recent(self) -> None:
        """save 3 records with different timestamps; assert get_latest() returns
        the one with the latest computed_at."""
        store = _make_store()
        security_id = "AAPL"

        t1 = datetime(2025, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
        t2 = datetime(2025, 1, 1, 11, 0, 0, tzinfo=timezone.utc)
        t3 = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

        r1 = _make_record(security_id=security_id, computed_at=t1)
        r2 = _make_record(security_id=security_id, computed_at=t2)
        r3 = _make_record(security_id=security_id, computed_at=t3)

        # Save in non-chronological order to ensure ordering is by computed_at
        store.save(r2)
        store.save(r3)
        store.save(r1)

        latest = store.get_latest(security_id)
        assert latest is not None
        assert latest.computed_at == t3

    def test_get_latest_returns_none_for_unknown_security(self) -> None:
        store = _make_store()
        result = store.get_latest("UNKNOWN")
        assert result is None


class TestGetHistoryFiltersByTimeRange:
    """test_get_history_filters_by_time_range"""

    def test_get_history_filters_by_time_range(self) -> None:
        """save records at t1, t2, t3; query [t1, t3) → returns t1 and t2 only."""
        store = _make_store()
        security_id = "BTC/USD"

        t1 = datetime(2025, 3, 1, 8, 0, 0, tzinfo=timezone.utc)
        t2 = datetime(2025, 3, 1, 9, 0, 0, tzinfo=timezone.utc)
        t3 = datetime(2025, 3, 1, 10, 0, 0, tzinfo=timezone.utc)

        r1 = _make_record(security_id=security_id, computed_at=t1)
        r2 = _make_record(security_id=security_id, computed_at=t2)
        r3 = _make_record(security_id=security_id, computed_at=t3)

        store.save(r1)
        store.save(r2)
        store.save(r3)

        # Half-open interval [t1, t3) — t3 must be excluded
        history = store.get_history(security_id, from_utc=t1, to_utc=t3)

        assert len(history) == 2
        returned_timestamps = {r.computed_at for r in history}
        assert t1 in returned_timestamps
        assert t2 in returned_timestamps
        assert t3 not in returned_timestamps

    def test_get_history_returns_empty_for_no_match(self) -> None:
        store = _make_store()
        t1 = datetime(2025, 1, 1, tzinfo=timezone.utc)
        t2 = datetime(2025, 1, 2, tzinfo=timezone.utc)
        result = store.get_history("UNKNOWN", t1, t2)
        assert result == []


class TestGetLatestByAssetClass:
    """test_get_latest_by_asset_class"""

    def test_get_latest_by_asset_class(self) -> None:
        """save records for 2 securities in FX, 1 in Equity;
        assert get_latest_by_asset_class(FX) returns 2 records."""
        store = _make_store()

        t1 = datetime(2025, 4, 1, 10, 0, 0, tzinfo=timezone.utc)
        t2 = datetime(2025, 4, 1, 11, 0, 0, tzinfo=timezone.utc)
        t3 = datetime(2025, 4, 1, 12, 0, 0, tzinfo=timezone.utc)

        # Two FX securities — each with two records; only the latest should be returned
        fx1_old = _make_record(security_id="EUR/USD", asset_class="FX", computed_at=t1)
        fx1_new = _make_record(security_id="EUR/USD", asset_class="FX", computed_at=t2)
        fx2 = _make_record(security_id="GBP/USD", asset_class="FX", computed_at=t3)

        # One Equity security — should NOT appear in FX results
        eq1 = _make_record(security_id="AAPL", asset_class="Equity", computed_at=t1)

        for r in (fx1_old, fx1_new, fx2, eq1):
            store.save(r)

        fx_latest = store.get_latest_by_asset_class("FX")

        assert len(fx_latest) == 2
        security_ids = {r.security_id for r in fx_latest}
        assert security_ids == {"EUR/USD", "GBP/USD"}

        # Verify the latest record for EUR/USD is t2, not t1
        eurusd_record = next(r for r in fx_latest if r.security_id == "EUR/USD")
        assert eurusd_record.computed_at == t2

    def test_get_latest_by_asset_class_returns_empty_for_unknown(self) -> None:
        store = _make_store()
        result = store.get_latest_by_asset_class("Unknown")
        assert result == []


class TestSaveRaisesStorageErrorOnDbFailure:
    """test_save_raises_storage_error_on_db_failure"""

    def test_save_raises_storage_error_on_db_failure(self) -> None:
        """Drop the table after store creation; assert StorageError is raised on save."""
        # Use a file-based SQLite DB so that dispose() actually closes connections
        # and the table drop is visible to subsequent sessions.
        import tempfile, os

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        try:
            engine = create_engine(f"sqlite:///{db_path}")
            store = SQLAlchemyRatingStore(engine)

            # Drop the table to simulate a DB schema failure
            with engine.connect() as conn:
                conn.execute(text("DROP TABLE rating_records"))
                conn.commit()

            record = _make_record()
            with pytest.raises(StorageError):
                store.save(record)
        finally:
            engine.dispose()
            try:
                os.unlink(db_path)
            except OSError:
                pass

    def test_save_raises_storage_error_on_duplicate_primary_key(self) -> None:
        """Saving a record with a duplicate record_id must raise StorageError."""
        store = _make_store()
        record = _make_record()
        store.save(record)

        # Attempt to save the same record again (same primary key)
        with pytest.raises(StorageError):
            store.save(record)
