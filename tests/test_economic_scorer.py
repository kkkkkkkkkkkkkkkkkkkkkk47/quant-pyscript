"""Tests for EconomicScorer — score bounds, macro alignment, carry boost, and unit tests.

Feature: quant-ratings
"""

from __future__ import annotations

import math
from datetime import datetime, timezone

import pytest
from hypothesis import assume, given, settings
import hypothesis.strategies as st

from quant_ratings.models.enums import AssetClass
from quant_ratings.models.market_data import MacroData
from quant_ratings.models.security import Security
from quant_ratings.scorers.economic_scorer import EconomicScorer

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

SECURITY = Security(
    identifier="EUR/USD",
    asset_class=AssetClass.FX,
    sub_category="Major",
)

_NOW = datetime.now(timezone.utc)

_STANCES = ["hawkish", "neutral", "dovish", None]


def _make_macro(
    pmi: float | None,
    prior_pmi: float | None,
    cpi: float | None,
    prior_cpi: float | None,
    central_bank_stance: str | None,
    interest_rate_differential: float | None,
) -> MacroData:
    return MacroData(
        pmi=pmi,
        prior_pmi=prior_pmi,
        cpi=cpi,
        prior_cpi=prior_cpi,
        central_bank_stance=central_bank_stance,
        interest_rate_differential=interest_rate_differential,
        timestamp=_NOW,
    )


# ---------------------------------------------------------------------------
# Hypothesis strategies
# ---------------------------------------------------------------------------

_pmi_strategy = st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False)
_cpi_strategy = st.floats(min_value=-5.0, max_value=20.0, allow_nan=False, allow_infinity=False)
_stance_strategy = st.sampled_from(_STANCES)
_ird_strategy = st.one_of(
    st.none(),
    st.floats(min_value=-1000.0, max_value=1000.0, allow_nan=False, allow_infinity=False),
)

_valid_macro_strategy = st.builds(
    _make_macro,
    pmi=_pmi_strategy,
    prior_pmi=_pmi_strategy,
    cpi=_cpi_strategy,
    prior_cpi=_cpi_strategy,
    central_bank_stance=_stance_strategy,
    interest_rate_differential=_ird_strategy,
)


# ---------------------------------------------------------------------------
# Task 8.2 — Property 1: Score bounds (EconomicScorer)
# ---------------------------------------------------------------------------

# Feature: quant-ratings, Property 1: Score bounds (EconomicScorer)
@given(macro=_valid_macro_strategy)
def test_score_bounds(macro: MacroData) -> None:
    """**Validates: Requirements 1.3, 5.7**

    For any valid MacroData, the produced Economic score must lie in [0.0, 5.0].
    """
    scorer = EconomicScorer()
    result = scorer.compute(SECURITY, macro)

    assert 0.0 <= result.score <= 5.0


# ---------------------------------------------------------------------------
# Task 8.3 — Property 10: Macro alignment
# ---------------------------------------------------------------------------

# Feature: quant-ratings, Property 10: Macro alignment
@given(
    pmi=st.floats(min_value=50.01, max_value=100.0, allow_nan=False, allow_infinity=False),
    prior_pmi=st.floats(min_value=0.0, max_value=50.0, allow_nan=False, allow_infinity=False),
    cpi=st.floats(min_value=2.51, max_value=20.0, allow_nan=False, allow_infinity=False),
    prior_cpi=st.floats(min_value=-5.0, max_value=2.5, allow_nan=False, allow_infinity=False),
    ird=_ird_strategy,
)
def test_full_bull_macro_score_at_least_4_5(
    pmi: float,
    prior_pmi: float,
    cpi: float,
    prior_cpi: float,
    ird: float | None,
) -> None:
    """**Validates: Requirements 5.2, 5.4**

    When PMI is improving (pmi > prior_pmi), CPI is improving (cpi > prior_cpi),
    and stance is hawkish, the Economic score must be >= 4.5.

    Note: carry boost can only push the score higher (>= 4.5 still holds).
    """
    assume(pmi > prior_pmi)
    assume(cpi > prior_cpi)

    macro = _make_macro(
        pmi=pmi,
        prior_pmi=prior_pmi,
        cpi=cpi,
        prior_cpi=prior_cpi,
        central_bank_stance="hawkish",
        interest_rate_differential=ird,
    )
    scorer = EconomicScorer()
    result = scorer.compute(SECURITY, macro)

    assert result.score >= 4.5


# Feature: quant-ratings, Property 10: Macro alignment
@given(
    pmi=st.floats(min_value=0.0, max_value=49.99, allow_nan=False, allow_infinity=False),
    prior_pmi=st.floats(min_value=50.0, max_value=100.0, allow_nan=False, allow_infinity=False),
    cpi=st.floats(min_value=-5.0, max_value=2.49, allow_nan=False, allow_infinity=False),
    prior_cpi=st.floats(min_value=2.5, max_value=20.0, allow_nan=False, allow_infinity=False),
)
def test_full_bear_macro_score_at_most_1_5(
    pmi: float,
    prior_pmi: float,
    cpi: float,
    prior_cpi: float,
) -> None:
    """**Validates: Requirements 5.2, 5.4**

    When PMI is declining (pmi < prior_pmi), CPI is declining (cpi < prior_cpi),
    and stance is dovish, the Economic score must be <= 1.5.

    Note: interest_rate_differential is set to None to avoid carry boost pushing
    the score above 1.5 (carry boost would add +0.5, giving 2.0 > 1.5).
    """
    assume(pmi < prior_pmi)
    assume(cpi < prior_cpi)

    macro = _make_macro(
        pmi=pmi,
        prior_pmi=prior_pmi,
        cpi=cpi,
        prior_cpi=prior_cpi,
        central_bank_stance="dovish",
        interest_rate_differential=None,  # no carry boost to keep score <= 1.5
    )
    scorer = EconomicScorer()
    result = scorer.compute(SECURITY, macro)

    assert result.score <= 1.5


# ---------------------------------------------------------------------------
# Task 8.4 — Property 11: Carry trade boost
# ---------------------------------------------------------------------------

# Feature: quant-ratings, Property 11: Carry boost
@given(
    pmi=st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False),
    prior_pmi=st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False),
    cpi=st.floats(min_value=-5.0, max_value=20.0, allow_nan=False, allow_infinity=False),
    prior_cpi=st.floats(min_value=-5.0, max_value=20.0, allow_nan=False, allow_infinity=False),
    ird_boost=st.floats(
        min_value=EconomicScorer.CARRY_THRESHOLD_BPS,
        max_value=1000.0,
        allow_nan=False,
        allow_infinity=False,
    ),
)
def test_carry_boost_adds_exactly_0_5(
    pmi: float,
    prior_pmi: float,
    cpi: float,
    prior_cpi: float,
    ird_boost: float,
) -> None:
    """**Validates: Requirements 5.3**

    For any base Economic score, when interest_rate_differential >= 200 bps,
    the final score must equal min(base_score + 0.5, 5.0).

    Strategy: use partial signals path (not full-bull or full-bear) to get varied
    base scores. Compute base score without carry (ird=None), then compute with
    ird >= 200, assert difference is exactly +0.5 (clamped to 5.0).
    """
    # Exclude full-bull and full-bear to stay in the partial signals path
    # for more varied base scores (though the property holds for all paths)
    pmi_improving = pmi > prior_pmi
    cpi_improving = cpi > prior_cpi

    # Use "neutral" stance to avoid full-bull (hawkish) or full-bear (dovish)
    stance = "neutral"

    scorer = EconomicScorer()

    # Base score without carry boost
    macro_no_carry = _make_macro(
        pmi=pmi,
        prior_pmi=prior_pmi,
        cpi=cpi,
        prior_cpi=prior_cpi,
        central_bank_stance=stance,
        interest_rate_differential=None,
    )
    base_result = scorer.compute(SECURITY, macro_no_carry)
    base_score = base_result.score

    # Score with carry boost applied
    macro_with_carry = _make_macro(
        pmi=pmi,
        prior_pmi=prior_pmi,
        cpi=cpi,
        prior_cpi=prior_cpi,
        central_bank_stance=stance,
        interest_rate_differential=ird_boost,
    )
    boosted_result = scorer.compute(SECURITY, macro_with_carry)
    boosted_score = boosted_result.score

    expected = min(base_score + EconomicScorer.CARRY_BOOST, 5.0)
    assert math.isclose(boosted_score, expected, rel_tol=1e-9, abs_tol=1e-9)


# ---------------------------------------------------------------------------
# Task 8.5 — Unit tests
# ---------------------------------------------------------------------------

def test_fallback_when_macro_none() -> None:
    """When macro is None, the scorer must return score=2.5 and is_fallback=True."""
    scorer = EconomicScorer()
    result = scorer.compute(SECURITY, macro=None)

    assert result.score == 2.5
    assert result.is_fallback is True


def test_fallback_when_pmi_none() -> None:
    """When macro.pmi is None, the scorer must return score=2.5 and is_fallback=True."""
    scorer = EconomicScorer()
    macro = _make_macro(
        pmi=None,
        prior_pmi=50.0,
        cpi=3.0,
        prior_cpi=2.5,
        central_bank_stance="hawkish",
        interest_rate_differential=None,
    )
    result = scorer.compute(SECURITY, macro)

    assert result.score == 2.5
    assert result.is_fallback is True


def test_fallback_when_cpi_none() -> None:
    """When macro.cpi is None, the scorer must return score=2.5 and is_fallback=True."""
    scorer = EconomicScorer()
    macro = _make_macro(
        pmi=55.0,
        prior_pmi=50.0,
        cpi=None,
        prior_cpi=2.5,
        central_bank_stance="hawkish",
        interest_rate_differential=None,
    )
    result = scorer.compute(SECURITY, macro)

    assert result.score == 2.5
    assert result.is_fallback is True


def test_full_bull_exact_score() -> None:
    """pmi=55>50, cpi=3.0>2.5, stance='hawkish', no carry → score==4.5."""
    scorer = EconomicScorer()
    macro = _make_macro(
        pmi=55.0,
        prior_pmi=50.0,
        cpi=3.0,
        prior_cpi=2.5,
        central_bank_stance="hawkish",
        interest_rate_differential=None,
    )
    result = scorer.compute(SECURITY, macro)

    assert result.score == pytest.approx(4.5)
    assert result.is_fallback is False


def test_full_bear_exact_score() -> None:
    """pmi=45<50, cpi=2.0<2.5, stance='dovish', no carry → score==1.5."""
    scorer = EconomicScorer()
    macro = _make_macro(
        pmi=45.0,
        prior_pmi=50.0,
        cpi=2.0,
        prior_cpi=2.5,
        central_bank_stance="dovish",
        interest_rate_differential=None,
    )
    result = scorer.compute(SECURITY, macro)

    assert result.score == pytest.approx(1.5)
    assert result.is_fallback is False


def test_carry_boost_applied() -> None:
    """Full-bull (4.5) + interest_rate_differential=250 → score==5.0."""
    scorer = EconomicScorer()
    macro = _make_macro(
        pmi=55.0,
        prior_pmi=50.0,
        cpi=3.0,
        prior_cpi=2.5,
        central_bank_stance="hawkish",
        interest_rate_differential=250.0,
    )
    result = scorer.compute(SECURITY, macro)

    assert result.score == pytest.approx(5.0)
    assert result.is_fallback is False
