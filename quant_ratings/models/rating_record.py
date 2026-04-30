"""RatingRecord model for the Quant Ratings engine.

A RatingRecord is the immutable, persisted output of a single rating
computation for one security.  Every field defined in Requirement 8.2 is
present and non-None on a successfully constructed record.
"""

from dataclasses import dataclass
from datetime import datetime

from quant_ratings.models.weight_profile import WeightProfile


@dataclass
class RatingRecord:
    """Immutable record produced by the Rating_Engine for a single security.

    Each record captures the full computation context — sub-scores, the weight
    profile used, and the UTC timestamp — so that historical ratings can be
    audited and reproduced.

    Attributes:
        record_id: Universally unique identifier for this record, stored as
            the canonical string representation of a UUID
            (e.g. ``"550e8400-e29b-41d4-a716-446655440000"``).
        security_id: Human-readable identifier of the rated security
            (e.g. ``"EUR/USD"``, ``"AAPL"``, ``"BTC/USD"``).
        asset_class: Top-level asset class of the security
            (e.g. ``"FX"``, ``"Equity"``, ``"Crypto"``).
        composite_score: Weighted aggregate of the three sub-scores, in the
            closed interval ``[0.0, 5.0]``.
        rating: Discrete rating label derived from ``composite_score`` — one
            of ``"Strong Buy"``, ``"Buy"``, ``"Neutral"``, ``"Sell"``, or
            ``"Strong Sell"``.
        sentiment_score: Output of the Sentiment_Scorer, in ``[0.0, 5.0]``.
        orderflow_score: Output of the OrderFlow_Scorer, in ``[0.0, 5.0]``.
        economic_score: Output of the Economic_Scorer, in ``[0.0, 5.0]``.
        weight_profile: The :class:`~quant_ratings.models.weight_profile.WeightProfile`
            applied when computing ``composite_score``.
        data_deficient: ``True`` when all three sub-scorers fell back to the
            neutral score (2.5) due to data unavailability, indicating the
            rating should be treated with low confidence.
        computed_at: UTC datetime at which this record was produced.
    """

    record_id: str
    security_id: str
    asset_class: str
    composite_score: float
    rating: str
    sentiment_score: float
    orderflow_score: float
    economic_score: float
    weight_profile: WeightProfile
    data_deficient: bool
    computed_at: datetime  # UTC
