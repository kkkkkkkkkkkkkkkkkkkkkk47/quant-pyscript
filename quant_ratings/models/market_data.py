"""Market data models for the Quant Ratings engine."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from quant_ratings.models.security import Security

# Minimum bid volume considered "institutional" for DOM analysis.
INSTITUTIONAL_BID_THRESHOLD: float = 100.0


@dataclass
class RetailPositioning:
    """Retail trader positioning data sourced from broker data."""

    long_pct: float
    """Fraction of retail traders holding a long position (0.0–1.0)."""

    short_pct: float
    """Fraction of retail traders holding a short position (0.0–1.0)."""

    timestamp: datetime
    """UTC timestamp of the data snapshot."""


@dataclass
class TickVolumeData:
    """Tick volume data used as a proxy for institutional trading activity."""

    current: float
    """Tick volume in the current period."""

    avg_20_period: float
    """Average tick volume over the prior 20 periods."""

    price_broke_4h_resistance: bool
    """True if price has broken a 4-hour resistance level in this period."""

    timestamp: datetime
    """UTC timestamp of the data snapshot."""


@dataclass
class FootprintData:
    """Order-flow footprint data showing net buy/sell delta within a candle."""

    net_delta: float
    """Net volume delta: positive = net buying, negative = net selling."""

    timestamp: datetime
    """UTC timestamp of the data snapshot."""


@dataclass
class DOMData:
    """Depth of Market data showing pending orders at each price level."""

    bid_levels: list[tuple[float, float]]
    """List of (price, volume) tuples for pending buy orders."""

    ask_levels: list[tuple[float, float]]
    """List of (price, volume) tuples for pending sell orders."""

    current_price: float
    """Current market price used as the reference for institutional bid detection."""

    timestamp: datetime
    """UTC timestamp of the data snapshot."""

    def has_institutional_bids_at_or_below_price(self) -> bool:
        """Return True if significant institutional bid volume exists at or below current_price.

        A bid level is considered institutional when its volume exceeds
        INSTITUTIONAL_BID_THRESHOLD and its price is at or below current_price.
        """
        return any(
            price <= self.current_price and volume >= INSTITUTIONAL_BID_THRESHOLD
            for price, volume in self.bid_levels
        )


@dataclass
class MacroData:
    """Macro-economic indicators used by the Economic Bias scorer."""

    pmi: Optional[float]
    """Current Purchasing Managers' Index value."""

    prior_pmi: Optional[float]
    """Prior-period PMI value for trend comparison."""

    cpi: Optional[float]
    """Current Consumer Price Index value."""

    prior_cpi: Optional[float]
    """Prior-period CPI value for trend comparison."""

    central_bank_stance: Optional[str]
    """Central bank policy stance: 'hawkish' | 'neutral' | 'dovish'."""

    interest_rate_differential: Optional[float]
    """Interest rate differential between base and quote currency in basis points."""

    timestamp: datetime
    """UTC timestamp of the data snapshot."""


@dataclass
class MarketDataBundle:
    """Aggregated market data required to score a single security."""

    security: Security
    """The security this bundle belongs to."""

    fetched_at: datetime
    """UTC timestamp when this bundle was assembled."""

    retail_positioning: Optional[RetailPositioning] = field(default=None)
    """Retail positioning data; None if unavailable."""

    vix: Optional[float] = field(default=None)
    """CBOE Volatility Index value; None if unavailable."""

    audjpy: Optional[float] = field(default=None)
    """AUD/JPY exchange rate used as a risk-on/off barometer; None if unavailable."""

    tick_volume: Optional[TickVolumeData] = field(default=None)
    """Tick volume data; None if unavailable."""

    footprint: Optional[FootprintData] = field(default=None)
    """Footprint order-flow data; None if unavailable."""

    dom: Optional[DOMData] = field(default=None)
    """Depth of Market data; None if unavailable."""

    macro: Optional[MacroData] = field(default=None)
    """Macro-economic data; None if unavailable."""
