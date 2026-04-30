"""Property tests for DataManager validation.

Feature: quant-ratings, Property 15: Invalid/stale data blocked

**Validates: Requirements 9.1, 9.2, 9.3**

Property 15: Out-of-range or stale data never reaches a scorer.
For any MarketDataBundle containing a field whose value is outside its defined
valid range, the DataManager must pass None for that field to the relevant scorer
(triggering the neutral fallback) rather than the invalid value.
For any data object where the timestamp is older than the configured staleness
threshold, the DataManager must treat that object as unavailable and pass None.
"""

from __future__ import annotations

from datetime import datetime, timezone, timedelta

from hypothesis import given, assume
import hypothesis.strategies as st

from quant_ratings.engine.data_manager import DataManager
from quant_ratings.models.market_data import RetailPositioning, TickVolumeData
from quant_ratings.models.security import Security
from quant_ratings.models.enums import AssetClass
from quant_ratings.providers.mock_provider import MockDataProvider

SECURITY = Security(
    identifier="EUR/USD",
    asset_class=AssetClass.FX,
    sub_category="Major",
)


# ---------------------------------------------------------------------------
# Test 1: Out-of-range VIX is replaced with None
# ---------------------------------------------------------------------------

@given(
    vix=st.one_of(
        st.floats(max_value=-0.001, allow_nan=False),
        st.floats(min_value=200.001, max_value=1e10, allow_nan=False),
    )
)
def test_out_of_range_vix_is_none(vix: float) -> None:
    """Feature: quant-ratings, Property 15: Invalid/stale data blocked

    VIX values outside [0.0, 200.0] must be replaced with None.
    """
    assume(not (vix != vix))  # filter NaN
    provider = MockDataProvider(vix=vix)
    manager = DataManager(providers=[provider])
    bundle = manager.fetch(SECURITY)
    assert bundle.vix is None


# ---------------------------------------------------------------------------
# Test 2: Out-of-range AUD/JPY is replaced with None
# ---------------------------------------------------------------------------

@given(
    audjpy=st.one_of(
        st.floats(max_value=-0.001, allow_nan=False),
        st.floats(min_value=500.001, max_value=1e10, allow_nan=False),
    )
)
def test_out_of_range_audjpy_is_none(audjpy: float) -> None:
    """Feature: quant-ratings, Property 15: Invalid/stale data blocked

    AUD/JPY values outside [0.0, 500.0] must be replaced with None.
    """
    assume(not (audjpy != audjpy))  # filter NaN
    provider = MockDataProvider(audjpy=audjpy)
    manager = DataManager(providers=[provider])
    bundle = manager.fetch(SECURITY)
    assert bundle.audjpy is None


# ---------------------------------------------------------------------------
# Test 3: Stale data objects are replaced with None
# ---------------------------------------------------------------------------

@given(age_hours=st.floats(min_value=4.001, max_value=1000.0, allow_nan=False))
def test_stale_data_is_none(age_hours: float) -> None:
    """Feature: quant-ratings, Property 15: Invalid/stale data blocked

    RetailPositioning with a timestamp older than the 4-hour staleness threshold
    must be replaced with None.
    """
    stale_ts = datetime.now(timezone.utc) - timedelta(hours=age_hours)
    positioning = RetailPositioning(long_pct=0.4, short_pct=0.6, timestamp=stale_ts)
    provider = MockDataProvider(retail_positioning=positioning)
    manager = DataManager(providers=[provider])
    bundle = manager.fetch(SECURITY)
    assert bundle.retail_positioning is None


# ---------------------------------------------------------------------------
# Test 4: Out-of-range RetailPositioning is replaced with None
# ---------------------------------------------------------------------------

@given(long_pct=st.floats(min_value=1.001, max_value=10.0, allow_nan=False))
def test_out_of_range_retail_positioning_is_none(long_pct: float) -> None:
    """Feature: quant-ratings, Property 15: Invalid/stale data blocked

    RetailPositioning with long_pct outside [0.0, 1.0] must be replaced with None.
    """
    assume(not (long_pct != long_pct))  # filter NaN
    ts = datetime.now(timezone.utc)
    positioning = RetailPositioning(long_pct=long_pct, short_pct=0.3, timestamp=ts)
    provider = MockDataProvider(retail_positioning=positioning)
    manager = DataManager(providers=[provider])
    bundle = manager.fetch(SECURITY)
    assert bundle.retail_positioning is None
