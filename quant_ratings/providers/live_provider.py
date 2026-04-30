"""LiveDataProvider — composite provider that chains all real data sources.

Wraps TwelveDataProvider, PolygonProvider, FredProvider, and
AlphaVantageProvider into a single DataProviderAdapter.  For each data type,
the first non-None result from the chain is returned.

Usage::

    from quant_ratings.providers.live_provider import LiveDataProvider

    provider = LiveDataProvider(
        twelve_data_api_key="...",
        polygon_api_key="...",
        fred_api_key="...",
        alpha_vantage_api_key="...",
    )
"""

from __future__ import annotations

import logging
from typing import Optional

from quant_ratings.models.market_data import (
    DOMData,
    FootprintData,
    MacroData,
    RetailPositioning,
    TickVolumeData,
)
from quant_ratings.models.security import Security
from quant_ratings.providers.alpha_vantage_provider import AlphaVantageProvider
from quant_ratings.providers.base import DataProviderAdapter
from quant_ratings.providers.fred_provider import FredProvider
from quant_ratings.providers.polygon_provider import PolygonProvider
from quant_ratings.providers.twelve_data_provider import TwelveDataProvider

logger = logging.getLogger(__name__)


class LiveDataProvider(DataProviderAdapter):
    """Composite DataProviderAdapter that chains all four real data sources.

    Each fetch method tries providers in priority order and returns the first
    non-None result.  If all providers return None, None is returned and the
    DataManager will apply the neutral fallback score.

    Priority order per data type:
    - fetch_vix:               TwelveData → Polygon → AlphaVantage
    - fetch_audjpy:            TwelveData → Polygon → AlphaVantage
    - fetch_tick_volume:       TwelveData → Polygon → AlphaVantage
    - fetch_dom:               TwelveData → Polygon
    - fetch_retail_positioning: Polygon
    - fetch_footprint:         (none — not available from any free API)
    - fetch_macro:             FRED → AlphaVantage

    Args:
        twelve_data_api_key: Twelve Data API key.
        polygon_api_key: Polygon.io API key.
        fred_api_key: FRED (St. Louis Fed) API key.
        alpha_vantage_api_key: Alpha Vantage API key.
    """

    def __init__(
        self,
        twelve_data_api_key: str,
        polygon_api_key: str,
        fred_api_key: str,
        alpha_vantage_api_key: str,
    ) -> None:
        self._twelve = TwelveDataProvider(api_key=twelve_data_api_key)
        self._polygon = PolygonProvider(api_key=polygon_api_key)
        self._fred = FredProvider(api_key=fred_api_key)
        self._av = AlphaVantageProvider(api_key=alpha_vantage_api_key)

    # ------------------------------------------------------------------
    # DataProviderAdapter interface
    # ------------------------------------------------------------------

    def fetch_retail_positioning(self, security: Security) -> Optional[RetailPositioning]:
        """Fetch retail positioning — Polygon only (equities)."""
        return self._polygon.fetch_retail_positioning(security)

    def fetch_vix(self) -> Optional[float]:
        """Fetch VIX — TwelveData → Polygon → AlphaVantage."""
        for provider in (self._twelve, self._polygon, self._av):
            result = provider.fetch_vix()
            if result is not None:
                return result
        logger.warning("All providers returned None for VIX")
        return None

    def fetch_audjpy(self) -> Optional[float]:
        """Fetch AUD/JPY — TwelveData → Polygon → AlphaVantage."""
        for provider in (self._twelve, self._polygon, self._av):
            result = provider.fetch_audjpy()
            if result is not None:
                return result
        logger.warning("All providers returned None for AUD/JPY")
        return None

    def fetch_tick_volume(self, security: Security) -> Optional[TickVolumeData]:
        """Fetch tick volume — TwelveData → Polygon → AlphaVantage."""
        for provider in (self._twelve, self._polygon, self._av):
            result = provider.fetch_tick_volume(security)
            if result is not None:
                return result
        logger.warning("All providers returned None for tick volume: %s", security.identifier)
        return None

    def fetch_footprint(self, security: Security) -> Optional[FootprintData]:
        """Footprint data not available from any free API — returns None."""
        return None

    def fetch_dom(self, security: Security) -> Optional[DOMData]:
        """Fetch DOM — TwelveData → Polygon."""
        for provider in (self._twelve, self._polygon):
            result = provider.fetch_dom(security)
            if result is not None:
                return result
        logger.warning("All providers returned None for DOM: %s", security.identifier)
        return None

    def fetch_macro(self, security: Security) -> Optional[MacroData]:
        """Fetch macro data — FRED → AlphaVantage."""
        for provider in (self._fred, self._av):
            result = provider.fetch_macro(security)
            if result is not None:
                return result
        logger.warning("All providers returned None for macro: %s", security.identifier)
        return None
