"""Scoring and aggregation result models for the Quant Ratings engine."""

from dataclasses import dataclass, field


@dataclass
class ScoreResult:
    """Result produced by a single scorer (Sentiment, OrderFlow, or Economic).

    Attributes:
        score: The computed score in the range 0.0–5.0.
        is_fallback: True when the neutral score (2.5) was used because the
            required input data was unavailable.
        warnings: Human-readable data-unavailability messages emitted during
            scoring. Empty when all required data was present.
    """

    score: float
    is_fallback: bool
    warnings: list[str] = field(default_factory=list)


@dataclass
class AggregationResult:
    """Result produced by the Aggregator after combining the three sub-scores.

    Attributes:
        composite_score: The weighted composite score in the range 0.0–5.0.
        rating: The discrete rating label derived from the composite score.
            One of: "Strong Buy", "Buy", "Neutral", "Sell", "Strong Sell".
        data_deficient: True when all three sub-scorers fell back to the
            neutral score due to data unavailability, indicating the rating
            should be treated with low confidence.
    """

    composite_score: float
    rating: str
    data_deficient: bool
