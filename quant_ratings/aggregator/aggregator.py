"""Aggregator for the Quant Ratings engine.

Combines the three sub-scores (Sentiment, OrderFlow, Economic) into a single
weighted Composite_Score and maps it to a discrete rating label.
"""

from __future__ import annotations

from quant_ratings.models.results import AggregationResult, ScoreResult
from quant_ratings.models.weight_profile import WeightProfile, WeightProfileError


def _clamp(value: float, min_val: float, max_val: float) -> float:
    """Clamp *value* to the closed interval [min_val, max_val]."""
    return max(min_val, min(max_val, value))


class Aggregator:
    """Combines three sub-scores into a weighted Composite_Score and rating.

    The Aggregator validates the weight profile, computes the weighted sum of
    the three scorer outputs, clamps the result to [0.0, 5.0], and maps it to
    one of five discrete rating labels.
    """

    RATING_THRESHOLDS: list[tuple[float, str]] = [
        (4.5, "Strong Buy"),
        (3.5, "Buy"),
        (2.5, "Neutral"),
        (1.5, "Sell"),
        (0.0, "Strong Sell"),
    ]

    def aggregate(
        self,
        sentiment: ScoreResult,
        orderflow: ScoreResult,
        economic: ScoreResult,
        profile: WeightProfile,
    ) -> AggregationResult:
        """Compute the Composite_Score and rating for a security.

        Args:
            sentiment: Score result from the SentimentScorer.
            orderflow: Score result from the OrderFlowScorer.
            economic: Score result from the EconomicScorer.
            profile: Weight profile defining the percentage contribution of
                each scoring layer.

        Returns:
            An :class:`~quant_ratings.models.results.AggregationResult` with
            the composite score, rating label, and data-deficiency flag.

        Raises:
            WeightProfileError: If the profile weights do not sum to 100.0
                (within a tolerance of 0.001).
        """
        total_weight = (
            profile.sentiment_pct + profile.orderflow_pct + profile.economic_pct
        )
        if abs(total_weight - 100.0) > 0.001:
            raise WeightProfileError(
                f"Weights sum to {total_weight}, expected 100"
            )

        w_s = profile.sentiment_pct / 100.0
        w_o = profile.orderflow_pct / 100.0
        w_e = profile.economic_pct / 100.0

        composite = (
            sentiment.score * w_s
            + orderflow.score * w_o
            + economic.score * w_e
        )

        composite = _clamp(composite, 0.0, 5.0)
        rating = self.map_to_rating(composite)

        all_fallback = (
            sentiment.is_fallback
            and orderflow.is_fallback
            and economic.is_fallback
        )

        return AggregationResult(
            composite_score=composite,
            rating=rating,
            data_deficient=all_fallback,
        )

    @staticmethod
    def map_to_rating(composite_score: float) -> str:
        """Map a composite score to a discrete rating label.

        Uses the five-threshold table:
        - score >= 4.5 → "Strong Buy"
        - score >= 3.5 → "Buy"
        - score >= 2.5 → "Neutral"
        - score >= 1.5 → "Sell"
        - otherwise   → "Strong Sell"

        Args:
            composite_score: A float in the range [0.0, 5.0].

        Returns:
            One of: "Strong Buy", "Buy", "Neutral", "Sell", "Strong Sell".
        """
        for threshold, label in Aggregator.RATING_THRESHOLDS:
            if composite_score >= threshold:
                return label
        return "Strong Sell"
