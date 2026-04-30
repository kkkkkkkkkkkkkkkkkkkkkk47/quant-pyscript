"""Order Flow scorer for the Quant Ratings engine.

Computes an OrderFlow_Score (0.0–5.0) for a security based on tick volume data,
footprint order-flow data, and Depth of Market (DOM) data.
"""

from __future__ import annotations

from typing import Optional

from quant_ratings.models.market_data import DOMData, FootprintData, TickVolumeData
from quant_ratings.models.results import ScoreResult
from quant_ratings.models.security import Security


def _clamp(value: float, min_val: float, max_val: float) -> float:
    """Clamp *value* to the closed interval [min_val, max_val]."""
    return max(min_val, min(max_val, value))


class OrderFlowScorer:
    """Computes the OrderFlow_Score for a security using tick volume and order-flow data.

    The scorer applies three layers of logic:
    1. Confirmed breakout: price broke resistance AND volume is rising → floor of 4.0.
    2. Unconfirmed breakout: price broke resistance but volume is NOT rising → ceiling of 2.0.
    3. No breakout: score proportional to the volume ratio (current / avg_20_period), clamped.
    4. DOM + Footprint institutional confirmation boost of +1.0 (clamped to 5.0).
    """

    NEUTRAL_SCORE: float = 2.5
    BREAKOUT_CONFIRMED_MIN: float = 4.0
    BREAKOUT_UNCONFIRMED_MAX: float = 2.0
    DOM_BOOST: float = 1.0

    def compute(
        self,
        security: Security,
        tick_volume: Optional[TickVolumeData],
        footprint: Optional[FootprintData],
        dom: Optional[DOMData],
    ) -> ScoreResult:
        """Compute the OrderFlow_Score for *security*.

        Args:
            security: The security being scored.
            tick_volume: Tick volume snapshot; ``None`` triggers neutral fallback.
            footprint: Footprint order-flow data; ``None`` disables the boost.
            dom: Depth of Market data; ``None`` disables the boost.

        Returns:
            A :class:`~quant_ratings.models.results.ScoreResult` with the computed
            score, fallback flag, and any data-unavailability warnings.
        """
        # --- Fallback: no tick volume data available ---
        if tick_volume is None:
            return ScoreResult(
                score=self.NEUTRAL_SCORE,
                is_fallback=True,
                warnings=["Tick volume unavailable"],
            )

        volume_rising: bool = tick_volume.current > tick_volume.avg_20_period
        price_broke_resistance: bool = tick_volume.price_broke_4h_resistance

        if price_broke_resistance and volume_rising:
            # Confirmed breakout: floor of 4.0
            base_score: float = self.BREAKOUT_CONFIRMED_MIN
        elif price_broke_resistance and not volume_rising:
            # Unconfirmed breakout: ceiling of 2.0
            base_score = self.BREAKOUT_UNCONFIRMED_MAX
        else:
            # No breakout: score proportional to volume ratio
            ratio = tick_volume.current / tick_volume.avg_20_period
            base_score = _clamp(2.5 * ratio, 0.0, 5.0)

        # --- DOM + Footprint institutional confirmation boost ---
        if (
            dom is not None
            and dom.has_institutional_bids_at_or_below_price()
            and footprint is not None
            and footprint.net_delta > 0
        ):
            base_score = _clamp(base_score + self.DOM_BOOST, 0.0, 5.0)

        return ScoreResult(
            score=_clamp(base_score, 0.0, 5.0),
            is_fallback=False,
        )
