"""Tests for the Aggregator — property-based and unit tests.

Feature: quant-ratings
"""

from __future__ import annotations

import math

import pytest
from hypothesis import given, settings, assume
import hypothesis.strategies as st

from quant_ratings.aggregator.aggregator import Aggregator
from quant_ratings.models.results import AggregationResult, ScoreResult
from quant_ratings.models.weight_profile import WeightProfile, WeightProfileError


# ---------------------------------------------------------------------------
# Shared helpers / strategies
# ---------------------------------------------------------------------------

def _make_score(score: float, is_fallback: bool = False) -> ScoreResult:
    return ScoreResult(score=score, is_fallback=is_fallback)


def _make_profile(s: float, o: float, e: float) -> WeightProfile:
    return WeightProfile(
        asset_class="FX",
        sub_category="Major",
        sentiment_pct=s,
        orderflow_pct=o,
        economic_pct=e,
    )


# Strategy: generate a valid weight triple that sums to exactly 100.
# Draw a in [0, 100], b in [0, 100-a], c = 100 - a - b.
@st.composite
def valid_weight_profiles(draw) -> WeightProfile:
    a = draw(st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False))
    b = draw(st.floats(min_value=0.0, max_value=100.0 - a, allow_nan=False, allow_infinity=False))
    c = 100.0 - a - b
    return WeightProfile(
        asset_class="FX",
        sub_category="Major",
        sentiment_pct=a,
        orderflow_pct=b,
        economic_pct=c,
    )


# Strategy: sub-scores in [0.0, 5.0]
_sub_score_strategy = st.floats(
    min_value=0.0, max_value=5.0, allow_nan=False, allow_infinity=False
)


# ---------------------------------------------------------------------------
# Task 10.2 — Property 1: Score bounds (Aggregator)
# ---------------------------------------------------------------------------

# Feature: quant-ratings, Property 1: Score bounds (Aggregator)
@given(
    s=_sub_score_strategy,
    o=_sub_score_strategy,
    e=_sub_score_strategy,
    profile=valid_weight_profiles(),
)
def test_composite_score_bounds(s: float, o: float, e: float, profile: WeightProfile) -> None:
    """**Validates: Requirements 1.3**

    For any valid sub-scores and valid weight profile, the composite score
    must lie in the closed interval [0.0, 5.0].
    """
    aggregator = Aggregator()
    result = aggregator.aggregate(
        _make_score(s),
        _make_score(o),
        _make_score(e),
        profile,
    )
    assert 0.0 <= result.composite_score <= 5.0


# ---------------------------------------------------------------------------
# Task 10.3 — Property 2: Weighted sum formula
# ---------------------------------------------------------------------------

# Feature: quant-ratings, Property 2: Weighted sum formula
@given(
    s=_sub_score_strategy,
    o=_sub_score_strategy,
    e=_sub_score_strategy,
    profile=valid_weight_profiles(),
)
def test_composite_score_weighted_sum(
    s: float, o: float, e: float, profile: WeightProfile
) -> None:
    """**Validates: Requirements 1.2**

    The composite score must equal s*(ws/100) + o*(wo/100) + e*(we/100)
    within floating-point tolerance.
    """
    aggregator = Aggregator()
    result = aggregator.aggregate(
        _make_score(s),
        _make_score(o),
        _make_score(e),
        profile,
    )

    expected = (
        s * (profile.sentiment_pct / 100.0)
        + o * (profile.orderflow_pct / 100.0)
        + e * (profile.economic_pct / 100.0)
    )
    # Clamp expected to [0.0, 5.0] to match aggregator behaviour
    expected = max(0.0, min(5.0, expected))

    assert math.isclose(result.composite_score, expected, rel_tol=1e-9, abs_tol=1e-9)


# ---------------------------------------------------------------------------
# Task 10.4 — Property 3: Invalid weight rejection
# ---------------------------------------------------------------------------

# Strategy: generate weight triples that do NOT sum to 100 (outside 0.001 tolerance).
@st.composite
def invalid_weight_profiles(draw) -> WeightProfile:
    a = draw(st.floats(min_value=0.0, max_value=200.0, allow_nan=False, allow_infinity=False))
    b = draw(st.floats(min_value=0.0, max_value=200.0, allow_nan=False, allow_infinity=False))
    c = draw(st.floats(min_value=0.0, max_value=200.0, allow_nan=False, allow_infinity=False))
    assume(abs(a + b + c - 100.0) > 0.001)
    return WeightProfile(
        asset_class="FX",
        sub_category="Major",
        sentiment_pct=a,
        orderflow_pct=b,
        economic_pct=c,
    )


# Feature: quant-ratings, Property 3: Invalid weights rejected
@given(
    s=_sub_score_strategy,
    o=_sub_score_strategy,
    e=_sub_score_strategy,
    profile=invalid_weight_profiles(),
)
def test_invalid_weights_raise_error(
    s: float, o: float, e: float, profile: WeightProfile
) -> None:
    """**Validates: Requirements 1.4**

    When the weight profile does not sum to 100% (outside 0.001 tolerance),
    the Aggregator must raise WeightProfileError and produce no composite score.
    """
    aggregator = Aggregator()
    with pytest.raises(WeightProfileError):
        aggregator.aggregate(
            _make_score(s),
            _make_score(o),
            _make_score(e),
            profile,
        )


# ---------------------------------------------------------------------------
# Task 10.5 — Property 4: Rating mapping
# ---------------------------------------------------------------------------

# Feature: quant-ratings, Property 4: Rating mapping
@given(score=st.floats(min_value=0.0, max_value=5.0, allow_nan=False, allow_infinity=False))
def test_rating_mapping_correct(score: float) -> None:
    """**Validates: Requirements 1.5**

    For any composite score in [0.0, 5.0], exactly one rating label is returned
    and it matches the threshold table:
      [4.5, 5.0]  → "Strong Buy"
      [3.5, 4.5)  → "Buy"
      [2.5, 3.5)  → "Neutral"
      [1.5, 2.5)  → "Sell"
      [0.0, 1.5)  → "Strong Sell"
    """
    rating = Aggregator.map_to_rating(score)

    valid_labels = {"Strong Buy", "Buy", "Neutral", "Sell", "Strong Sell"}
    assert rating in valid_labels

    if score >= 4.5:
        assert rating == "Strong Buy"
    elif score >= 3.5:
        assert rating == "Buy"
    elif score >= 2.5:
        assert rating == "Neutral"
    elif score >= 1.5:
        assert rating == "Sell"
    else:
        assert rating == "Strong Sell"


# ---------------------------------------------------------------------------
# Task 10.6 — Unit tests
# ---------------------------------------------------------------------------

def test_all_fallback_produces_data_deficient() -> None:
    """When all three ScoreResults have is_fallback=True, data_deficient must be True."""
    aggregator = Aggregator()
    profile = _make_profile(20.0, 30.0, 50.0)

    result = aggregator.aggregate(
        ScoreResult(score=2.5, is_fallback=True),
        ScoreResult(score=2.5, is_fallback=True),
        ScoreResult(score=2.5, is_fallback=True),
        profile,
    )

    assert result.data_deficient is True


def test_not_all_fallback_not_data_deficient() -> None:
    """When at least one ScoreResult has is_fallback=False, data_deficient must be False."""
    aggregator = Aggregator()
    profile = _make_profile(20.0, 30.0, 50.0)

    # Only sentiment is not a fallback
    result = aggregator.aggregate(
        ScoreResult(score=3.0, is_fallback=False),
        ScoreResult(score=2.5, is_fallback=True),
        ScoreResult(score=2.5, is_fallback=True),
        profile,
    )

    assert result.data_deficient is False


def test_fx_major_weights_exact_composite() -> None:
    """FX Major weights (20/30/50) with known sub-scores produce the expected composite.

    sentiment=3.0, orderflow=4.0, economic=3.5
    expected: 3.0*0.20 + 4.0*0.30 + 3.5*0.50 = 0.60 + 1.20 + 1.75 = 3.55 → "Buy"
    """
    aggregator = Aggregator()
    profile = _make_profile(20.0, 30.0, 50.0)

    result = aggregator.aggregate(
        _make_score(3.0),
        _make_score(4.0),
        _make_score(3.5),
        profile,
    )

    assert math.isclose(result.composite_score, 3.55, rel_tol=1e-9, abs_tol=1e-9)
    assert result.rating == "Buy"
