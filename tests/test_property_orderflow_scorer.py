"""Property tests for OrderFlowScorer.

Feature: quant-ratings, Property 8: Breakout direction

**Validates: Requirements 4.2, 4.4**

Property 8: Breakout confirmation determines OrderFlow score direction.
- When price breaks 4h resistance AND volume is rising, score >= 4.0 (confirmed breakout floor).
- When price breaks 4h resistance AND volume is NOT rising, score <= 2.0 (unconfirmed breakout ceiling).
"""

from __future__ import annotations

from datetime import datetime, timezone

from hypothesis import given
import hypothesis.strategies as st

from quant_ratings.models.market_data import TickVolumeData
from quant_ratings.models.enums import AssetClass
from quant_ratings.models.security import Security
from quant_ratings.scorers.orderflow_scorer import OrderFlowScorer

SECURITY = Security(
    identifier="EUR/USD",
    asset_class=AssetClass.FX,
    sub_category="Major",
)

FIXED_TIMESTAMP = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Property 8a: Confirmed breakout → score >= 4.0 (Requirement 4.2)
# ---------------------------------------------------------------------------

@given(
    avg=st.floats(min_value=0.001, max_value=1_000_000.0, allow_nan=False, allow_infinity=False),
    delta=st.floats(min_value=0.001, max_value=1_000_000.0, allow_nan=False, allow_infinity=False),
)
def test_confirmed_breakout_score_at_least_4(avg: float, delta: float) -> None:
    # Feature: quant-ratings, Property 8: Breakout direction
    """When price breaks 4h resistance AND tick volume is rising (current > avg_20_period),
    the OrderFlow score must be >= 4.0 (confirmed breakout floor).

    Validates: Requirements 4.2
    """
    scorer = OrderFlowScorer()
    tick_volume = TickVolumeData(
        current=avg + delta,          # current > avg_20_period (volume rising)
        avg_20_period=avg,
        price_broke_4h_resistance=True,
        timestamp=FIXED_TIMESTAMP,
    )

    result = scorer.compute(
        security=SECURITY,
        tick_volume=tick_volume,
        footprint=None,
        dom=None,
    )

    assert result.score >= 4.0, (
        f"Expected score >= 4.0 for confirmed breakout, got {result.score} "
        f"(current={avg + delta}, avg={avg})"
    )


# ---------------------------------------------------------------------------
# Property 8b: Unconfirmed breakout → score <= 2.0 (Requirement 4.4)
# ---------------------------------------------------------------------------

@given(
    avg=st.floats(min_value=0.001, max_value=1_000_000.0, allow_nan=False, allow_infinity=False),
    current=st.floats(min_value=0.0, max_value=1_000_000.0, allow_nan=False, allow_infinity=False),
)
def test_unconfirmed_breakout_score_at_most_2(avg: float, current: float) -> None:
    # Feature: quant-ratings, Property 8: Breakout direction
    """When price breaks 4h resistance AND tick volume is NOT rising (current <= avg_20_period),
    the OrderFlow score must be <= 2.0 (unconfirmed breakout ceiling).

    Validates: Requirements 4.4
    """
    from hypothesis import assume
    assume(current <= avg)  # volume not rising: current <= avg_20_period

    scorer = OrderFlowScorer()
    tick_volume = TickVolumeData(
        current=current,
        avg_20_period=avg,
        price_broke_4h_resistance=True,
        timestamp=FIXED_TIMESTAMP,
    )

    result = scorer.compute(
        security=SECURITY,
        tick_volume=tick_volume,
        footprint=None,
        dom=None,
    )

    assert result.score <= 2.0, (
        f"Expected score <= 2.0 for unconfirmed breakout, got {result.score} "
        f"(current={current}, avg={avg})"
    )


# ---------------------------------------------------------------------------
# Property 9: DOM/Footprint boost adds exactly +1.0 (clamped to 5.0)
# (Requirement 4.3)
# ---------------------------------------------------------------------------

from quant_ratings.models.market_data import DOMData, FootprintData
from quant_ratings.models.market_data import INSTITUTIONAL_BID_THRESHOLD


@given(
    avg=st.floats(min_value=0.001, max_value=1_000_000.0, allow_nan=False, allow_infinity=False),
    ratio=st.floats(min_value=0.0, max_value=2.0, allow_nan=False, allow_infinity=False),
    net_delta=st.floats(min_value=0.001, max_value=1_000_000.0, allow_nan=False, allow_infinity=False),
    bid_volume=st.floats(min_value=INSTITUTIONAL_BID_THRESHOLD, max_value=1_000_000.0, allow_nan=False, allow_infinity=False),
)
def test_dom_footprint_boost_adds_exactly_one(
    avg: float,
    ratio: float,
    net_delta: float,
    bid_volume: float,
) -> None:
    # Feature: quant-ratings, Property 9: DOM/Footprint boost
    """When DOM has institutional bids at/below price and footprint.net_delta > 0,
    the final score equals min(base_score + 1.0, 5.0).

    Strategy: use no-breakout path (price_broke_4h_resistance=False) with a known
    volume ratio to get a predictable base_score. Compute once without boost
    (footprint=None, dom=None) to capture base_score, then compute again with
    boost conditions and assert the difference is exactly +1.0 (clamped to 5.0).

    **Validates: Requirements 4.3**
    """
    scorer = OrderFlowScorer()
    current = avg * ratio

    tick_volume = TickVolumeData(
        current=current,
        avg_20_period=avg,
        price_broke_4h_resistance=False,  # no-breakout path → predictable base_score
        timestamp=FIXED_TIMESTAMP,
    )

    # Capture base_score without boost
    base_result = scorer.compute(
        security=SECURITY,
        tick_volume=tick_volume,
        footprint=None,
        dom=None,
    )
    base_score = base_result.score

    # Build DOM with an institutional bid at or below current_price
    current_price = 1.0
    dom = DOMData(
        bid_levels=[(current_price, bid_volume)],  # price <= current_price, volume >= threshold
        ask_levels=[],
        current_price=current_price,
        timestamp=FIXED_TIMESTAMP,
    )
    footprint = FootprintData(net_delta=net_delta, timestamp=FIXED_TIMESTAMP)

    # Compute with boost
    boosted_result = scorer.compute(
        security=SECURITY,
        tick_volume=tick_volume,
        footprint=footprint,
        dom=dom,
    )

    expected_score = min(base_score + 1.0, 5.0)

    assert boosted_result.score == expected_score, (
        f"Expected score {expected_score} (base={base_score} + 1.0 clamped to 5.0), "
        f"got {boosted_result.score} (avg={avg}, ratio={ratio}, net_delta={net_delta})"
    )
