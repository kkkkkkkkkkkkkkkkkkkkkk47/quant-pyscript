"""Economic scorer for the Quant Ratings engine.

Computes an Economic_Score (0.0–5.0) for a security based on macro-economic
indicators: PMI trend, CPI trend, central bank stance, and interest rate
differential (carry trade).
"""

from __future__ import annotations

from typing import Optional

from quant_ratings.models.market_data import MacroData
from quant_ratings.models.results import ScoreResult
from quant_ratings.models.security import Security


def _clamp(value: float, min_val: float, max_val: float) -> float:
    """Clamp *value* to the closed interval [min_val, max_val]."""
    return max(min_val, min(max_val, value))


class EconomicScorer:
    """Computes the Economic_Score for a security using macro-economic indicators.

    The scorer applies three layers of logic:
    1. Full-bull signal: PMI improving, CPI improving, and hawkish stance → floor of 4.5.
    2. Full-bear signal: PMI declining, CPI declining, and dovish stance → ceiling of 1.5.
    3. Partial signals: score interpolated between 1.5 and 4.5 based on bullish signal count.
    4. Carry trade boost of +0.5 when interest rate differential >= 200 bps (clamped to 5.0).
    """

    NEUTRAL_SCORE: float = 2.5
    STRONG_BULL_MIN: float = 4.5
    STRONG_BEAR_MAX: float = 1.5
    CARRY_BOOST: float = 0.5
    CARRY_THRESHOLD_BPS: int = 200

    def compute(
        self,
        security: Security,
        macro: Optional[MacroData],
    ) -> ScoreResult:
        """Compute the Economic_Score for *security*.

        Args:
            security: The security being scored.
            macro: Macro-economic data snapshot; ``None`` or missing PMI/CPI
                triggers neutral fallback.

        Returns:
            A :class:`~quant_ratings.models.results.ScoreResult` with the computed
            score, fallback flag, and any data-unavailability warnings.
        """
        # --- Fallback: no macro data or missing PMI/CPI ---
        if macro is None or macro.pmi is None or macro.cpi is None:
            return ScoreResult(
                score=self.NEUTRAL_SCORE,
                is_fallback=True,
                warnings=["PMI/CPI data unavailable"],
            )

        pmi_improving: bool = macro.pmi > macro.prior_pmi if macro.prior_pmi is not None else False
        cpi_improving: bool = macro.cpi > macro.prior_cpi if macro.prior_cpi is not None else False
        hawkish_base: bool = macro.central_bank_stance == "hawkish"
        dovish_base: bool = macro.central_bank_stance == "dovish"

        if pmi_improving and cpi_improving and hawkish_base:
            # Full-bull: all three signals aligned bullish
            base_score: float = self.STRONG_BULL_MIN
        elif not pmi_improving and not cpi_improving and dovish_base:
            # Full-bear: all three signals aligned bearish
            base_score = self.STRONG_BEAR_MAX
        else:
            # Partial signals: interpolate between 1.5 and 4.5 based on bullish signal count
            # 0 bullish signals → 1.5, 3 bullish signals → 4.5
            bullish_signals: int = sum([pmi_improving, cpi_improving, hawkish_base])
            base_score = self.STRONG_BEAR_MAX + (bullish_signals / 3.0) * 3.0

        # --- Carry trade boost ---
        if (
            macro.interest_rate_differential is not None
            and macro.interest_rate_differential >= self.CARRY_THRESHOLD_BPS
        ):
            base_score = _clamp(base_score + self.CARRY_BOOST, 0.0, 5.0)

        return ScoreResult(
            score=_clamp(base_score, 0.0, 5.0),
            is_fallback=False,
        )
