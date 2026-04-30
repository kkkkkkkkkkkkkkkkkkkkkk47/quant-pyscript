"""Tests for OrderFlowScorer — score bounds, breakout direction, DOM/Footprint boost, and unit tests.

Feature: quant-ratings
"""

from __future__ import annotations

import math
from datetime import datetime, timezone

import pytest
from hypothesis import assume, given
import hypothesis.strategies as st

from quant_ratings.models.enums import AssetClass
from quant_ratings.models.market_data import DOMData, FootprintData, TickVolumeData
from quant_ratings.models.security import Security
from quant_ratings.scorers.orderflow_scorer import OrderFlowScorer

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

SECURITY = Security(
    identifier="EUR/USD",
    asset_class=AssetClass.FX,
    sub_category="Major",
)

_NOW = datetime.now(timezone.utc)


def _make_tick_volume(
    current: float,
    avg_20_period: float,
    price_broke_4h_resistance: bool,
) -> TickVolumeData:
    return TickVolumeData(
        current=current,
        avg_20_period=avg_20_period,
        price_broke_4h_resistance=price_broke_4h_resistance,
        timestamp=_NOW,
    )


def _make_footprint(net_delta: float) -> FootprintData:
    return FootprintData(net_delta=net_delta, timestamp=_NOW)


def _make_dom(
    bid_levels: list[tuple[float, float]],
    current_price: float,
) -> DOMData:
    return DOMData(
        bid_levels=bid_levels,
        ask_levels=[],
        current_price=current_price,
        timestamp=_NOW,
    )


# ---------------------------------------------------------------------------
# Hypothesis strategies
# ---------------------------------------------------------------------------

_tick_volume_strategy = st.builds(
    _make_tick_volume,
    current=st.floats(min_value=0.0, max_value=1_000_000.0),
    avg_20_period=st.floats(min_value=1e-9, max_value=1_000_000.0),
    price_broke_4h_resistance=st.booleans(),
)

_footprint_strategy = st.builds(
    _make_footprint,
    net_delta=st.floats(min_value=-1_000_000.0, max_value=1_000_000.0),
)

_bid_levels_strategy = st.lists(
    st.tuples(
        st.floats(min_value=0.0, max_value=1000.0),
        st.floats(min_value=0.0, max_value=10000.0),
    ),
    max_size=5,
)

_dom_strategy = st.builds(
    _make_dom,
    bid_levels=_bid_levels_strategy,
    current_price=st.floats(min_value=1e-9, max_value=1000.0),
)


# ---------------------------------------------------------------------------
# Task 7.2 — Property 1: Score bounds (OrderFlowScorer)
# ---------------------------------------------------------------------------

# Feature: quant-ratings, Property 1: Score bounds (OrderFlowScorer)
@given(
    tick_volume=st.one_of(st.none(), _tick_volume_strategy),
    footprint=st.one_of(st.none(), _footprint_strategy),
    dom=st.one_of(st.none(), _dom_strategy),
)
def test_score_bounds(
    tick_volume: TickVolumeData | None,
    footprint: FootprintData | None,
    dom: DOMData | None,
) -> None:
    """**Validates: Requirements 1.3, 4.6**

    For any valid inputs to OrderFlowScorer, the produced score must lie in [0.0, 5.0].
    """
    # Filter out NaN values that would break arithmetic
    if tick_volume is not None:
        assume(not math.isnan(tick_volume.current))
        assume(not math.isnan(tick_volume.avg_20_period))
        assume(tick_volume.avg_20_period > 0)
    if footprint is not None:
        assume(not math.isnan(footprint.net_delta))
    if dom is not None:
        assume(not math.isnan(dom.current_price))
        assume(dom.current_price > 0)
        for price, volume in dom.bid_levels:
            assume(not math.isnan(price))
            assume(not math.isnan(volume))

    scorer = OrderFlowScorer()
    result = scorer.compute(SECURITY, tick_volume, footprint, dom)

    assert 0.0 <= result.score <= 5.0


# ---------------------------------------------------------------------------
# Task 7.3 — Property 8: Breakout direction
# ---------------------------------------------------------------------------

# Feature: quant-ratings, Property 8: Breakout direction
@given(
    avg_20_period=st.floats(min_value=1.0, max_value=100_000.0),
    extra=st.floats(min_value=1e-6, max_value=100_000.0),
)
def test_confirmed_breakout_score_at_least_4(
    avg_20_period: float,
    extra: float,
) -> None:
    """**Validates: Requirements 4.2, 4.4**

    When price_broke_4h_resistance=True and current > avg_20_period (volume rising),
    the score must be >= 4.0 (no DOM/Footprint boost applied).
    """
    assume(not math.isnan(avg_20_period))
    assume(not math.isnan(extra))

    current = avg_20_period + extra
    tick_volume = _make_tick_volume(
        current=current,
        avg_20_period=avg_20_period,
        price_broke_4h_resistance=True,
    )

    scorer = OrderFlowScorer()
    result = scorer.compute(SECURITY, tick_volume, footprint=None, dom=None)

    assert result.score >= 4.0


# Feature: quant-ratings, Property 8: Breakout direction
@given(
    avg_20_period=st.floats(min_value=1.0, max_value=100_000.0),
    current=st.floats(min_value=0.0, max_value=100_000.0),
)
def test_unconfirmed_breakout_score_at_most_2(
    avg_20_period: float,
    current: float,
) -> None:
    """**Validates: Requirements 4.2, 4.4**

    When price_broke_4h_resistance=True and current <= avg_20_period (volume not rising),
    the score must be <= 2.0 (no DOM/Footprint boost applied).
    """
    assume(not math.isnan(avg_20_period))
    assume(not math.isnan(current))
    assume(current <= avg_20_period)

    tick_volume = _make_tick_volume(
        current=current,
        avg_20_period=avg_20_period,
        price_broke_4h_resistance=True,
    )

    scorer = OrderFlowScorer()
    result = scorer.compute(SECURITY, tick_volume, footprint=None, dom=None)

    assert result.score <= 2.0


# ---------------------------------------------------------------------------
# Task 7.4 — Property 9: DOM/Footprint boost
# ---------------------------------------------------------------------------

# Feature: quant-ratings, Property 9: DOM/Footprint boost
@given(
    avg_20_period=st.floats(min_value=1.0, max_value=100_000.0),
    current=st.floats(min_value=0.0, max_value=100_000.0),
    net_delta=st.floats(min_value=1e-9, max_value=1_000_000.0),
    bid_price_offset=st.floats(min_value=0.0, max_value=10.0),
)
def test_dom_footprint_boost_adds_exactly_1(
    avg_20_period: float,
    current: float,
    net_delta: float,
    bid_price_offset: float,
) -> None:
    """**Validates: Requirements 4.3**

    For any base score (no breakout, no boost), when DOM has institutional bids at/below
    current_price AND footprint net_delta > 0, the final score must equal
    min(base_score + 1.0, 5.0).
    """
    assume(not math.isnan(avg_20_period))
    assume(not math.isnan(current))
    assume(not math.isnan(net_delta))
    assume(not math.isnan(bid_price_offset))
    assume(avg_20_period > 0)

    # Use price_broke_4h_resistance=False to stay in the volume-ratio branch
    tick_volume = _make_tick_volume(
        current=current,
        avg_20_period=avg_20_period,
        price_broke_4h_resistance=False,
    )

    scorer = OrderFlowScorer()

    # Step 1: compute base score without boost
    base_result = scorer.compute(SECURITY, tick_volume, footprint=None, dom=None)
    base_score = base_result.score

    # Step 2: build DOM with an institutional bid at or below current_price
    current_price = 100.0
    bid_price = current_price - bid_price_offset  # at or below current_price
    dom = _make_dom(
        bid_levels=[(bid_price, 200.0)],  # volume >= 100.0 → institutional
        current_price=current_price,
    )
    footprint = _make_footprint(net_delta=net_delta)

    boosted_result = scorer.compute(SECURITY, tick_volume, footprint=footprint, dom=dom)
    boosted_score = boosted_result.score

    expected = min(base_score + 1.0, 5.0)
    assert boosted_score == pytest.approx(expected)


# ---------------------------------------------------------------------------
# Task 7.5 — Unit tests
# ---------------------------------------------------------------------------

def test_fallback_when_tick_volume_none() -> None:
    """When tick_volume is None, the scorer must return score=2.5 and is_fallback=True."""
    scorer = OrderFlowScorer()
    result = scorer.compute(SECURITY, tick_volume=None, footprint=None, dom=None)

    assert result.score == 2.5
    assert result.is_fallback is True


def test_confirmed_breakout_exact_score() -> None:
    """price_broke_4h_resistance=True, current=200, avg=100 (volume rising), no boost → score==4.0."""
    scorer = OrderFlowScorer()
    tick_volume = _make_tick_volume(
        current=200.0,
        avg_20_period=100.0,
        price_broke_4h_resistance=True,
    )
    result = scorer.compute(SECURITY, tick_volume, footprint=None, dom=None)

    assert result.score == pytest.approx(4.0)
    assert result.is_fallback is False


def test_unconfirmed_breakout_exact_score() -> None:
    """price_broke_4h_resistance=True, current=50, avg=100 (volume not rising), no boost → score==2.0."""
    scorer = OrderFlowScorer()
    tick_volume = _make_tick_volume(
        current=50.0,
        avg_20_period=100.0,
        price_broke_4h_resistance=True,
    )
    result = scorer.compute(SECURITY, tick_volume, footprint=None, dom=None)

    assert result.score == pytest.approx(2.0)
    assert result.is_fallback is False


def test_no_breakout_volume_ratio_score() -> None:
    """price_broke_4h_resistance=False, current=100, avg=100 (ratio=1.0), no boost → score==2.5.

    Expected: 2.5 * (100 / 100) = 2.5
    """
    scorer = OrderFlowScorer()
    tick_volume = _make_tick_volume(
        current=100.0,
        avg_20_period=100.0,
        price_broke_4h_resistance=False,
    )
    result = scorer.compute(SECURITY, tick_volume, footprint=None, dom=None)

    assert result.score == pytest.approx(2.5)
    assert result.is_fallback is False


def test_dom_footprint_boost_applied() -> None:
    """Confirmed breakout (score=4.0) + DOM institutional bids + footprint net_delta>0 → score==5.0.

    Expected: 4.0 (confirmed breakout) + 1.0 (DOM/Footprint boost) = 5.0
    """
    scorer = OrderFlowScorer()
    tick_volume = _make_tick_volume(
        current=200.0,
        avg_20_period=100.0,
        price_broke_4h_resistance=True,
    )
    # DOM with an institutional bid (volume >= 100) at or below current_price
    dom = _make_dom(
        bid_levels=[(99.0, 200.0)],  # price=99 <= current_price=100, volume=200 >= threshold
        current_price=100.0,
    )
    footprint = _make_footprint(net_delta=500.0)  # net_delta > 0

    result = scorer.compute(SECURITY, tick_volume, footprint=footprint, dom=dom)

    assert result.score == pytest.approx(5.0)
    assert result.is_fallback is False
