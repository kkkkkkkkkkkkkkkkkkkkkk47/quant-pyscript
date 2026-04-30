"""Sentiment scorer for the Quant Ratings engine.

Computes a Sentiment_Score (0.0–5.0) for a security based on retail positioning
data, VIX fear index, and AUD/JPY risk-on/off barometer.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from quant_ratings.models.market_data import RetailPositioning
from quant_ratings.models.results import ScoreResult
from quant_ratings.models.security import Security


def _clamp(value: float, min_val: float, max_val: float) -> float:
    """Clamp *value* to the closed interval [min_val, max_val]."""
    return max(min_val, min(max_val, value))


class SentimentScorer:
    """Computes the Sentiment_Score for a security using a contrarian retail-positioning model.

    The scorer applies three layers of logic:
    1. Extreme contrarian signals when retail positioning is heavily one-sided.
    2. Linear interpolation for moderate positioning.
    3. VIX amplification that widens the distance from neutral when fear is elevated.
    """

    NEUTRAL_SCORE: float = 2.5
    MAX_SCORE: float = 5.0
    MIN_SCORE: float = 0.0
    EXTREME_THRESHOLD: float = 0.80          # 80% retail positioning triggers contrarian signal
    VIX_FEAR_THRESHOLD: float = 30.0         # VIX above this level is considered "fear"
    CONTRARIAN_BOOST: float = 0.20           # 20% amplification of distance from neutral
    AUDJPY_RISK_ON_THRESHOLD: float = 80.0   # AUD/JPY above this = risk-on environment

    def compute(
        self,
        security: Security,
        positioning: Optional[RetailPositioning],
        vix: Optional[float],
        audjpy: Optional[float],
    ) -> ScoreResult:
        """Compute the Sentiment_Score for *security*.

        Args:
            security: The security being scored (used for logging / future extensions).
            positioning: Retail positioning snapshot; ``None`` triggers neutral fallback.
            vix: CBOE Volatility Index value; ``None`` disables VIX amplification.
            audjpy: AUD/JPY exchange rate used as a risk-on/off barometer; ``None``
                means risk-off conditions are assumed.

        Returns:
            A :class:`~quant_ratings.models.results.ScoreResult` with the computed
            score, fallback flag, and any data-unavailability warnings.
        """
        # --- Fallback: no positioning data available ---
        if positioning is None:
            return ScoreResult(
                score=self.NEUTRAL_SCORE,
                is_fallback=True,
                warnings=["Retail positioning unavailable"],
            )

        # --- Risk-on/off determination via AUD/JPY ---
        risk_on: bool = audjpy is not None and audjpy > self.AUDJPY_RISK_ON_THRESHOLD

        # --- Contrarian extreme signals ---
        if positioning.short_pct >= self.EXTREME_THRESHOLD and risk_on:
            # Extreme short positioning in a risk-on environment → contrarian bullish
            base_score: float = self.MAX_SCORE
        elif positioning.long_pct >= self.EXTREME_THRESHOLD and not risk_on:
            # Extreme long positioning in a risk-off environment → contrarian bearish
            base_score = self.MIN_SCORE
        else:
            # Linear interpolation:
            #   100% long  → 0.0  (bearish)
            #   100% short → 5.0  (bullish)
            base_score = self.MAX_SCORE * (1.0 - positioning.long_pct)

        # --- VIX amplification ---
        if vix is not None and vix > self.VIX_FEAR_THRESHOLD:
            # Amplify the distance from neutral by CONTRARIAN_BOOST (20%)
            distance = base_score - self.NEUTRAL_SCORE
            base_score = _clamp(
                self.NEUTRAL_SCORE + distance * (1.0 + self.CONTRARIAN_BOOST),
                self.MIN_SCORE,
                self.MAX_SCORE,
            )

        return ScoreResult(
            score=_clamp(base_score, self.MIN_SCORE, self.MAX_SCORE),
            is_fallback=False,
        )
