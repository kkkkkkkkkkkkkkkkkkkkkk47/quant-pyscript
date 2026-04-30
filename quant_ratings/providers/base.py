"""Abstract base class for data provider adapters."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from quant_ratings.models.market_data import (
    DOMData,
    FootprintData,
    MacroData,
    RetailPositioning,
    TickVolumeData,
)
from quant_ratings.models.security import Security


class DataProviderAdapter(ABC):
    """Abstract base class for all data provider adapters.

    Concrete implementations fetch raw market data from external or internal
    sources (broker positioning feeds, tick volume APIs, macro data providers,
    etc.) and return typed model objects.  Any method may return ``None`` to
    indicate that the data is currently unavailable for the requested security.
    """

    @abstractmethod
    def fetch_retail_positioning(self, security: Security) -> Optional[RetailPositioning]:
        """Fetch retail trader positioning data for *security*.

        Returns ``None`` if the data is unavailable.
        """

    @abstractmethod
    def fetch_vix(self) -> Optional[float]:
        """Fetch the current CBOE Volatility Index (VIX) value.

        Returns ``None`` if the data is unavailable.
        """

    @abstractmethod
    def fetch_audjpy(self) -> Optional[float]:
        """Fetch the current AUD/JPY exchange rate used as a risk barometer.

        Returns ``None`` if the data is unavailable.
        """

    @abstractmethod
    def fetch_tick_volume(self, security: Security) -> Optional[TickVolumeData]:
        """Fetch tick volume data for *security*.

        Returns ``None`` if the data is unavailable.
        """

    @abstractmethod
    def fetch_footprint(self, security: Security) -> Optional[FootprintData]:
        """Fetch order-flow footprint data for *security*.

        Returns ``None`` if the data is unavailable.
        """

    @abstractmethod
    def fetch_dom(self, security: Security) -> Optional[DOMData]:
        """Fetch Depth of Market data for *security*.

        Returns ``None`` if the data is unavailable.
        """

    @abstractmethod
    def fetch_macro(self, security: Security) -> Optional[MacroData]:
        """Fetch macro-economic indicator data for *security*.

        Returns ``None`` if the data is unavailable.
        """
