"""Tests for SentimentScorer — score bounds, extreme positioning, VIX amplification, and unit tests.

Feature: quant-ratings
"""

from __future__ import annotations

import math
from datetime import datetime, timezone

import pytest
from hypothesis import assume, given
import hypothesis.strategies as st

from quant_ratings.models.enums import AssetClass
from quant_ratings.models.market_data import RetailPositioning
from quant_ratings.models.security import Security
from quant_ratings.scorers.sentiment_scorer import SentimentScorer

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

SECURITY = Security(
    identifier="EUR/USD",
    asset_class=AssetClass.FX,
    sub_category="Major",
)


def _make_positioning(long_pct: float, short_pct: float) -> RetailPositioning:
    return RetailPositioning(
        long_pct=long_pct,
        short_pct=short_pct,
        timestamp=datetime.now(timezone.utc),
    )


# ---------------------------------------------------------------------------
# Task 6.2 — Property 1: Score bounds (SentimentScorer)
# ---------------------------------------------------------------------------

# Feature: quant-ratings, Property 1: Score bounds (SentimentScorer)
@given(
    long_pct=st.floats(min_value=0.0, max_value=1.0),
    short_pct=st.floats(min_value=0.0, max_value=1.0),
    vix=st.one_of(st.none(), st.floats(min_value=0.0, max_value=200.0)),
    audjpy=st.one_of(st.none(), st.floats(min_value=0.0, max_value=500.0)),
)
def test_score_bounds(
    long_pct: float,
    short_pct: float,
    vix: float | None,
    audjpy: float | None,
) -> None:
    """**Validates: Requirements 1.3, 3.6**

    For any valid inputs to SentimentScorer, the produced score must lie in [0.0, 5.0].
    """
    assume(not math.isnan(long_pct))
    assume(not math.isnan(short_pct))
    assume(vix is None or not math.isnan(vix))
    assume(audjpy is None or not math.isnan(audjpy))

    scorer = SentimentScorer()
    positioning = _make_positioning(long_pct, short_pct)
    result = scorer.compute(SECURITY, positioning, vix, audjpy)

    assert 0.0 <= result.score <= 5.0


# ---------------------------------------------------------------------------
# Task 6.3 — Property 6: Extreme positioning
# ---------------------------------------------------------------------------

# Feature: quant-ratings, Property 6: Extreme positioning
@given(
    short_pct=st.floats(min_value=0.80, max_value=1.0),
    audjpy=st.floats(
        min_value=SentimentScorer.AUDJPY_RISK_ON_THRESHOLD + 1e-9,
        max_value=500.0,
    ),
    vix=st.one_of(st.none(), st.floats(min_value=0.0, max_value=200.0)),
)
def test_extreme_short_positioning_score_is_5(
    short_pct: float,
    audjpy: float,
    vix: float | None,
) -> None:
    """**Validates: Requirements 3.2, 3.3**

    For any short_pct >= 0.80 with risk-on AUD/JPY (> threshold) and any VIX,
    the SentimentScorer must return a score of exactly 5.0.

    VIX amplification on score=5.0: distance=2.5, 2.5 + 2.5*1.2 = 5.5, clamped to 5.0.
    """
    assume(not math.isnan(short_pct))
    assume(not math.isnan(audjpy))
    assume(vix is None or not math.isnan(vix))

    long_pct = 1.0 - short_pct
    scorer = SentimentScorer()
    positioning = _make_positioning(long_pct, short_pct)
    result = scorer.compute(SECURITY, positioning, vix=vix, audjpy=audjpy)

    assert result.score == 5.0


# Feature: quant-ratings, Property 6: Extreme positioning
@given(
    long_pct=st.floats(min_value=0.80, max_value=1.0),
    audjpy=st.one_of(
        st.none(),
        st.floats(min_value=0.0, max_value=SentimentScorer.AUDJPY_RISK_ON_THRESHOLD),
    ),
    vix=st.one_of(st.none(), st.floats(min_value=0.0, max_value=200.0)),
)
def test_extreme_long_positioning_score_is_0(
    long_pct: float,
    audjpy: float | None,
    vix: float | None,
) -> None:
    """**Validates: Requirements 3.2, 3.3**

    For any long_pct >= 0.80 with risk-off AUD/JPY (<= threshold or None) and any VIX,
    the SentimentScorer must return a score of exactly 0.0.

    VIX amplification on score=0.0: distance=-2.5, 2.5 + (-2.5)*1.2 = -0.5, clamped to 0.0.
    """
    assume(not math.isnan(long_pct))
    assume(audjpy is None or not math.isnan(audjpy))
    assume(vix is None or not math.isnan(vix))

    short_pct = 1.0 - long_pct
    scorer = SentimentScorer()
    positioning = _make_positioning(long_pct, short_pct)
    result = scorer.compute(SECURITY, positioning, vix=vix, audjpy=audjpy)

    assert result.score == 0.0


# ---------------------------------------------------------------------------
# Task 6.4 — Property 7: VIX amplification
# ---------------------------------------------------------------------------

# Feature: quant-ratings, Property 7: VIX amplification
@given(
    long_pct=st.floats(min_value=0.01, max_value=0.79),
    vix=st.floats(min_value=30.001, max_value=200.0),
)
def test_vix_amplification(long_pct: float, vix: float) -> None:
    """**Validates: Requirements 3.4**

    For any non-extreme positioning, when VIX > 30.0, the final score's distance
    from 2.5 must be 1.20× the base distance (without VIX), clamped to [0.0, 5.0].
    """
    assume(not math.isnan(long_pct))
    assume(not math.isnan(vix))

    short_pct = 1.0 - long_pct
    scorer = SentimentScorer()
    positioning = _make_positioning(long_pct, short_pct)

    # Base score without VIX amplification
    base_result = scorer.compute(SECURITY, positioning, vix=None, audjpy=None)
    base_score = base_result.score

    # Score with VIX amplification
    amplified_result = scorer.compute(SECURITY, positioning, vix=vix, audjpy=None)
    amplified_score = amplified_result.score

    # Expected: distance from neutral amplified by 1.20, clamped to [0.0, 5.0]
    neutral = 2.5
    base_distance = base_score - neutral
    expected_score = max(0.0, min(5.0, neutral + base_distance * 1.20))
    expected_distance = abs(expected_score - neutral)
    actual_distance = abs(amplified_score - neutral)

    assert math.isclose(actual_distance, expected_distance, rel_tol=1e-6)


# ---------------------------------------------------------------------------
# Task 6.5 — Unit tests
# ---------------------------------------------------------------------------

def test_fallback_when_positioning_is_none() -> None:
    """When positioning is None, the scorer must return score=2.5 and is_fallback=True."""
    scorer = SentimentScorer()
    result = scorer.compute(SECURITY, positioning=None, vix=None, audjpy=None)

    assert result.score == 2.5
    assert result.is_fallback is True


def test_known_positioning_vix_combination() -> None:
    """With long_pct=0.6, short_pct=0.4, vix=None, audjpy=None the score should be 2.0.

    Expected: 5.0 * (1.0 - 0.6) = 2.0
    """
    scorer = SentimentScorer()
    positioning = _make_positioning(long_pct=0.6, short_pct=0.4)
    result = scorer.compute(SECURITY, positioning, vix=None, audjpy=None)

    assert result.score == pytest.approx(2.0)
    assert result.is_fallback is False


def test_known_positioning_with_vix_amplification() -> None:
    """With long_pct=0.6, short_pct=0.4, vix=35, audjpy=None the score should be 1.9.

    Expected:
      base_score = 5.0 * (1.0 - 0.6) = 2.0
      distance   = 2.0 - 2.5 = -0.5
      amplified  = 2.5 + (-0.5 * 1.20) = 2.5 - 0.6 = 1.9
    """
    scorer = SentimentScorer()
    positioning = _make_positioning(long_pct=0.6, short_pct=0.4)
    result = scorer.compute(SECURITY, positioning, vix=35.0, audjpy=None)

    assert result.score == pytest.approx(1.9)
    assert result.is_fallback is False
