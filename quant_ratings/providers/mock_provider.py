"""Mock data provider for use in tests and integration scenarios."""

from __future__ import annotations

from typing import Callable, Optional, Union

from quant_ratings.models.market_data import (
    DOMData,
    FootprintData,
    MacroData,
    RetailPositioning,
    TickVolumeData,
)
from quant_ratings.models.security import Security
from quant_ratings.providers.base import DataProviderAdapter

# Type alias: a value can be a fixed result or a callable that accepts a Security.
_ValueOrCallable = Union[object, Callable[[Security], object]]


def _resolve(value: _ValueOrCallable, security: Optional[Security]) -> object:
    """Return *value* directly, or call it with *security* if it is callable."""
    if callable(value):
        return value(security)
    return value


class MockDataProvider(DataProviderAdapter):
    """Configurable deterministic data provider for tests and integration scenarios.

    Each data type can be supplied as either a fixed value (returned for every
    security) or a callable ``(security) -> value`` that allows per-security
    customisation.  Any data type that is not supplied defaults to ``None``,
    simulating unavailable data.

    Example usage::

        mock = MockDataProvider(vix=25.0, audjpy=85.0)
        mock.fetch_vix()                        # returns 25.0
        mock.fetch_retail_positioning(security)  # returns None
    """

    def __init__(
        self,
        *,
        retail_positioning: _ValueOrCallable = None,
        vix: _ValueOrCallable = None,
        audjpy: _ValueOrCallable = None,
        tick_volume: _ValueOrCallable = None,
        footprint: _ValueOrCallable = None,
        dom: _ValueOrCallable = None,
        macro: _ValueOrCallable = None,
    ) -> None:
        self._retail_positioning = retail_positioning
        self._vix = vix
        self._audjpy = audjpy
        self._tick_volume = tick_volume
        self._footprint = footprint
        self._dom = dom
        self._macro = macro

    # ------------------------------------------------------------------
    # DataProviderAdapter interface
    # ------------------------------------------------------------------

    def fetch_retail_positioning(self, security: Security) -> Optional[RetailPositioning]:
        return _resolve(self._retail_positioning, security)  # type: ignore[return-value]

    def fetch_vix(self) -> Optional[float]:
        return _resolve(self._vix, None)  # type: ignore[return-value]

    def fetch_audjpy(self) -> Optional[float]:
        return _resolve(self._audjpy, None)  # type: ignore[return-value]

    def fetch_tick_volume(self, security: Security) -> Optional[TickVolumeData]:
        return _resolve(self._tick_volume, security)  # type: ignore[return-value]

    def fetch_footprint(self, security: Security) -> Optional[FootprintData]:
        return _resolve(self._footprint, security)  # type: ignore[return-value]

    def fetch_dom(self, security: Security) -> Optional[DOMData]:
        return _resolve(self._dom, security)  # type: ignore[return-value]

    def fetch_macro(self, security: Security) -> Optional[MacroData]:
        return _resolve(self._macro, security)  # type: ignore[return-value]
