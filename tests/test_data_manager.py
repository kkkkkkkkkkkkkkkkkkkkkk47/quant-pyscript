"""Unit tests for DataManager validation and staleness checks.

Validates: Requirements 9.1, 9.2, 9.3

Tests cover:
- Out-of-range field values are replaced with None and a validation error is logged
- Stale data objects (timestamp older than threshold) are replaced with None
- Valid data passes through unchanged
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta

import pytest

from quant_ratings.engine.data_manager import DataManager
from quant_ratings.models.enums import AssetClass
from quant_ratings.models.market_data import RetailPositioning, TickVolumeData
from quant_ratings.models.security import Security
from quant_ratings.providers.mock_provider import MockDataProvider

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

SECURITY = Security(
    identifier="EUR/USD",
    asset_class=AssetClass.FX,
    sub_category="Major",
)


def _fresh_ts() -> datetime:
    """Return a UTC timestamp that is well within the staleness threshold."""
    return datetime.now(timezone.utc)


def _stale_ts(hours: float = 5.0) -> datetime:
    """Return a UTC timestamp that is older than the default 4-hour threshold."""
    return datetime.now(timezone.utc) - timedelta(hours=hours)


# ---------------------------------------------------------------------------
# 1. Out-of-range VIX → bundle.vix is None
# ---------------------------------------------------------------------------

def test_out_of_range_vix_negative_is_none() -> None:
    """VIX of -1.0 is below the valid range [0.0, 200.0]; must be replaced with None."""
    provider = MockDataProvider(vix=-1.0)
    manager = DataManager(providers=[provider])
    bundle = manager.fetch(SECURITY)
    assert bundle.vix is None


# ---------------------------------------------------------------------------
# 2. Out-of-range AUD/JPY → bundle.audjpy is None
# ---------------------------------------------------------------------------

def test_out_of_range_audjpy_too_high_is_none() -> None:
    """AUD/JPY of 600.0 exceeds the valid range [0.0, 500.0]; must be replaced with None."""
    provider = MockDataProvider(audjpy=600.0)
    manager = DataManager(providers=[provider])
    bundle = manager.fetch(SECURITY)
    assert bundle.audjpy is None


# ---------------------------------------------------------------------------
# 3. Out-of-range RetailPositioning.long_pct → bundle.retail_positioning is None
# ---------------------------------------------------------------------------

def test_out_of_range_retail_positioning_long_pct_is_none() -> None:
    """RetailPositioning with long_pct=1.5 exceeds [0.0, 1.0]; whole object must be None."""
    positioning = RetailPositioning(long_pct=1.5, short_pct=0.3, timestamp=_fresh_ts())
    provider = MockDataProvider(retail_positioning=positioning)
    manager = DataManager(providers=[provider])
    bundle = manager.fetch(SECURITY)
    assert bundle.retail_positioning is None


# ---------------------------------------------------------------------------
# 4. Out-of-range TickVolumeData.avg_20_period (0.0 — division-by-zero risk)
#    → bundle.tick_volume is None
# ---------------------------------------------------------------------------

def test_out_of_range_tick_volume_avg_zero_is_none() -> None:
    """TickVolumeData with avg_20_period=0.0 violates the strictly-positive range;
    the whole object must be replaced with None to prevent division-by-zero downstream."""
    tick_volume = TickVolumeData(
        current=100.0,
        avg_20_period=0.0,
        price_broke_4h_resistance=False,
        timestamp=_fresh_ts(),
    )
    provider = MockDataProvider(tick_volume=tick_volume)
    manager = DataManager(providers=[provider])
    bundle = manager.fetch(SECURITY)
    assert bundle.tick_volume is None


# ---------------------------------------------------------------------------
# 5. Stale RetailPositioning (5 hours ago) → bundle.retail_positioning is None
# ---------------------------------------------------------------------------

def test_stale_retail_positioning_is_none() -> None:
    """RetailPositioning with a timestamp 5 hours ago exceeds the 4-hour threshold;
    must be replaced with None."""
    positioning = RetailPositioning(long_pct=0.4, short_pct=0.6, timestamp=_stale_ts(hours=5.0))
    provider = MockDataProvider(retail_positioning=positioning)
    manager = DataManager(providers=[provider])
    bundle = manager.fetch(SECURITY)
    assert bundle.retail_positioning is None


# ---------------------------------------------------------------------------
# 6. Stale TickVolumeData (5 hours ago) → bundle.tick_volume is None
# ---------------------------------------------------------------------------

def test_stale_tick_volume_is_none() -> None:
    """TickVolumeData with a timestamp 5 hours ago exceeds the 4-hour threshold;
    must be replaced with None."""
    tick_volume = TickVolumeData(
        current=200.0,
        avg_20_period=150.0,
        price_broke_4h_resistance=True,
        timestamp=_stale_ts(hours=5.0),
    )
    provider = MockDataProvider(tick_volume=tick_volume)
    manager = DataManager(providers=[provider])
    bundle = manager.fetch(SECURITY)
    assert bundle.tick_volume is None


# ---------------------------------------------------------------------------
# 7. Valid VIX passes through unchanged
# ---------------------------------------------------------------------------

def test_valid_vix_passes_through() -> None:
    """A valid VIX value of 25.0 is within [0.0, 200.0] and must be returned as-is."""
    provider = MockDataProvider(vix=25.0)
    manager = DataManager(providers=[provider])
    bundle = manager.fetch(SECURITY)
    assert bundle.vix == 25.0


# ---------------------------------------------------------------------------
# 8. Valid RetailPositioning passes through unchanged
# ---------------------------------------------------------------------------

def test_valid_retail_positioning_passes_through() -> None:
    """RetailPositioning with long_pct=0.4, short_pct=0.6 is valid and must not be None."""
    positioning = RetailPositioning(long_pct=0.4, short_pct=0.6, timestamp=_fresh_ts())
    provider = MockDataProvider(retail_positioning=positioning)
    manager = DataManager(providers=[provider])
    bundle = manager.fetch(SECURITY)
    assert bundle.retail_positioning is not None
    assert bundle.retail_positioning.long_pct == 0.4
    assert bundle.retail_positioning.short_pct == 0.6


# ---------------------------------------------------------------------------
# 9. Validation error is logged when VIX is out of range
# ---------------------------------------------------------------------------

def test_out_of_range_vix_logs_validation_error(caplog: pytest.LogCaptureFixture) -> None:
    """When VIX is out of range, a validation error must be logged at ERROR level
    containing the field name and the received value."""
    provider = MockDataProvider(vix=-1.0)
    manager = DataManager(providers=[provider])

    with caplog.at_level(logging.ERROR, logger="quant_ratings.engine.data_manager"):
        bundle = manager.fetch(SECURITY)

    assert bundle.vix is None

    # At least one ERROR-level log record must mention the field name and value.
    error_records = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert error_records, "Expected at least one ERROR log record for out-of-range VIX"

    combined_message = " ".join(r.getMessage() for r in error_records)
    assert "vix" in combined_message.lower(), (
        f"Expected 'vix' in log message, got: {combined_message!r}"
    )
    assert "-1.0" in combined_message or "-1" in combined_message, (
        f"Expected the invalid value '-1.0' in log message, got: {combined_message!r}"
    )
