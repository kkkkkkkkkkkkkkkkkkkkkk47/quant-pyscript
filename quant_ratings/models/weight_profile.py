"""Weight profile model for the Quant Ratings engine.

A WeightProfile defines the percentage contribution of each scoring layer
(Sentiment, OrderFlow, Economic) to the final Composite_Score for a given
asset class and optional sub-category.
"""

from dataclasses import dataclass
from typing import Optional


class WeightProfileError(Exception):
    """Raised when a WeightProfile has invalid weights.

    This exception is raised by :meth:`WeightProfile.validate` when the three
    percentage weights do not sum to 100.0 (within a tolerance of 0.001), and
    by the Aggregator when it detects an invalid profile before computing a
    Composite_Score.
    """


@dataclass
class WeightProfile:
    """Percentage weights applied to the three scoring layers for a security.

    Attributes:
        asset_class: Top-level asset class identifier, e.g. ``"FX"``,
            ``"Equity"``, ``"Crypto"``.
        sub_category: Optional sub-grouping within the asset class, e.g.
            ``"Major"``, ``"Volatile_Cross"``, ``"Emerging"``.  ``None`` for
            asset classes that do not have sub-categories.
        sentiment_pct: Percentage weight assigned to the Sentiment_Score
            (e.g. ``20.0`` for 20 %).
        orderflow_pct: Percentage weight assigned to the OrderFlow_Score
            (e.g. ``30.0`` for 30 %).
        economic_pct: Percentage weight assigned to the Economic_Score
            (e.g. ``50.0`` for 50 %).

    The three percentage weights must sum to exactly 100.0 (within a floating-
    point tolerance of 0.001).  Call :meth:`validate` to enforce this
    invariant before the profile is used in a computation.
    """

    asset_class: str
    sub_category: Optional[str]
    sentiment_pct: float
    orderflow_pct: float
    economic_pct: float

    def validate(self) -> None:
        """Verify that the three weights sum to 100.0.

        Raises:
            WeightProfileError: If ``sentiment_pct + orderflow_pct +
                economic_pct`` differs from 100.0 by more than 0.001.
        """
        total = self.sentiment_pct + self.orderflow_pct + self.economic_pct
        if abs(total - 100.0) > 0.001:
            raise WeightProfileError(
                f"Weights sum to {total:.4f}, expected 100.0"
            )
