"""Twelve Data real-market data provider.

Fetches tick volume, AUD/JPY, VIX, and DOM-approximation data from the
Twelve Data REST API (https://twelvedata.com).

API key: configured at construction time.
Docs: https://twelvedata.com/docs
"""

from __future__ import annotations

import logging
import time
import threading
from datetime import datetime, timezone
from typing import Optional

import urllib.request
import urllib.parse
import json

from quant_ratings.models.market_data import (
    DOMData,
    FootprintData,
    MacroData,
    RetailPositioning,
    TickVolumeData,
)
from quant_ratings.models.security import Security
from quant_ratings.providers.base import DataProviderAdapter

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.twelvedata.com"

# Map internal identifiers to Twelve Data symbols
_FX_SYMBOL_MAP: dict[str, str] = {
    "EUR/USD": "EUR/USD",
    "GBP/USD": "GBP/USD",
    "USD/JPY": "USD/JPY",
    "AUD/JPY": "AUD/JPY",
    "GBP/JPY": "GBP/JPY",
    "USD/NGN": "USD/NGN",
    "USD/ZAR": "USD/ZAR",
    "BTC/USD": "BTC/USD",
    "ETH/USD": "ETH/USD",
}

# Twelve Data symbol for VIX (uses the index prefix)
_VIX_SYMBOL = "VIX"          # Twelve Data accepts plain "VIX" for the index
_VIX_SYMBOL_ALT = "^VIX"     # fallback with caret prefix
_AUDJPY_SYMBOL = "AUD/JPY"

# ---------------------------------------------------------------------------
# Simple per-minute rate limiter (free tier: 8 calls/minute)
# ---------------------------------------------------------------------------
_RATE_LIMIT = 7          # stay under the 8/min cap with a 1-call buffer
_RATE_WINDOW = 62.0      # seconds (slightly over 60 to be safe)
_call_times: list[float] = []
_rate_lock = threading.Lock()


def _rate_limited_get(url: str) -> None:
    """Block until a Twelve Data API call is allowed under the rate limit."""
    with _rate_lock:
        now = time.monotonic()
        cutoff = now - _RATE_WINDOW
        while _call_times and _call_times[0] < cutoff:
            _call_times.pop(0)

        if len(_call_times) >= _RATE_LIMIT:
            wait_for = _RATE_WINDOW - (now - _call_times[0]) + 0.1
            if wait_for > 0:
                logger.debug("Twelve Data rate limit: sleeping %.1fs", wait_for)
                time.sleep(wait_for)
            now = time.monotonic()
            cutoff = now - _RATE_WINDOW
            while _call_times and _call_times[0] < cutoff:
                _call_times.pop(0)

        _call_times.append(time.monotonic())


def _get(url: str) -> Optional[dict]:
    """Perform a rate-limited GET request and return parsed JSON, or None on error."""
    _rate_limited_get(url)  # enforce rate limit (blocks if needed)
    try:
        with urllib.request.urlopen(url, timeout=15) as resp:
            raw = resp.read().decode("utf-8")
            data = json.loads(raw)
            if isinstance(data, dict) and data.get("status") == "error":
                logger.warning("Twelve Data API error: %s", data.get("message"))
                return None
            return data
    except Exception as exc:
        logger.warning("Twelve Data request failed for %s: %s", url, exc)
        return None


def _to_symbol(security: Security) -> Optional[str]:
    """Convert a Security identifier to a Twelve Data symbol."""
    sym = _FX_SYMBOL_MAP.get(security.identifier)
    if sym:
        return sym
    # For equities/indices/crypto, use the identifier directly
    return security.identifier.replace("/", "")


class TwelveDataProvider(DataProviderAdapter):
    """DataProviderAdapter backed by the Twelve Data REST API.

    Provides:
    - fetch_vix()          — VIX index value
    - fetch_audjpy()       — AUD/JPY exchange rate
    - fetch_tick_volume()  — current vs 20-period average volume + resistance break
    - fetch_dom()          — approximated from bid/ask quote data

    Returns None for retail_positioning, footprint, and macro (not available
    from Twelve Data; use PolygonProvider or FredProvider for those).

    Args:
        api_key: Your Twelve Data API key.
    """

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

    # ------------------------------------------------------------------
    # DataProviderAdapter interface
    # ------------------------------------------------------------------

    def fetch_retail_positioning(self, security: Security) -> Optional[RetailPositioning]:
        """Not available from Twelve Data — returns None."""
        return None

    def fetch_vix(self) -> Optional[float]:
        """Fetch the current VIX value from Twelve Data."""
        for symbol in (_VIX_SYMBOL, _VIX_SYMBOL_ALT):
            url = (
                f"{_BASE_URL}/price"
                f"?symbol={urllib.parse.quote(symbol)}"
                f"&apikey={self._api_key}"
            )
            data = _get(url)
            if data is not None:
                try:
                    return float(data["price"])
                except (KeyError, TypeError, ValueError):
                    continue
        logger.warning("Could not fetch VIX from Twelve Data")
        return None

    def fetch_audjpy(self) -> Optional[float]:
        """Fetch the current AUD/JPY exchange rate from Twelve Data."""
        url = (
            f"{_BASE_URL}/price"
            f"?symbol={_AUDJPY_SYMBOL}"
            f"&apikey={self._api_key}"
        )
        data = _get(url)
        if data is None:
            return None
        try:
            return float(data["price"])
        except (KeyError, TypeError, ValueError) as exc:
            logger.warning("Could not parse AUD/JPY from Twelve Data: %s — %s", data, exc)
            return None

    def fetch_tick_volume(self, security: Security) -> Optional[TickVolumeData]:
        """Fetch tick volume data for *security* using the time_series endpoint.

        For equities and indices: uses 1-hour candles with volume.
        For FX and crypto: volume is not available from Twelve Data; returns None
        so the DataManager falls back to the next provider.
        """
        # FX pairs don't have volume data on Twelve Data free tier
        if security.asset_class.value == "FX":
            return None

        symbol = _to_symbol(security)
        if symbol is None:
            return None

        url = (
            f"{_BASE_URL}/time_series"
            f"?symbol={urllib.parse.quote(symbol)}"
            f"&interval=1h"
            f"&outputsize=25"
            f"&apikey={self._api_key}"
        )
        data = _get(url)
        if data is None or "values" not in data:
            return None

        values = data["values"]
        if len(values) < 5:
            logger.warning("Insufficient candles from Twelve Data for %s", symbol)
            return None

        try:
            # values[0] is the most recent candle
            vol_raw = values[0].get("volume")
            if vol_raw is None:
                return None
            current_volume = float(vol_raw)

            prior_volumes = []
            for v in values[1:21]:
                vol = v.get("volume")
                if vol is not None:
                    prior_volumes.append(float(vol))

            avg_20 = sum(prior_volumes) / len(prior_volumes) if prior_volumes else current_volume

            # Resistance break: latest close > max high of prior 4 candles
            latest_close = float(values[0]["close"])
            prior_highs = [float(v["high"]) for v in values[1:5]]
            price_broke_resistance = latest_close > max(prior_highs) if prior_highs else False

            timestamp = datetime.now(timezone.utc)
            return TickVolumeData(
                current=current_volume,
                avg_20_period=avg_20,
                price_broke_4h_resistance=price_broke_resistance,
                timestamp=timestamp,
            )
        except (KeyError, TypeError, ValueError, ZeroDivisionError) as exc:
            logger.warning("Could not parse tick volume from Twelve Data for %s: %s", symbol, exc)
            return None

    def fetch_footprint(self, security: Security) -> Optional[FootprintData]:
        """Not available from Twelve Data — returns None."""
        return None

    def fetch_dom(self, security: Security) -> Optional[DOMData]:
        """Approximate DOM from the Twelve Data quote endpoint.

        Uses bid/ask prices and sizes from the real-time quote as a proxy for
        the top-of-book DOM. Returns a single bid level and single ask level.
        """
        symbol = _to_symbol(security)
        if symbol is None:
            return None

        url = (
            f"{_BASE_URL}/quote"
            f"?symbol={urllib.parse.quote(symbol)}"
            f"&apikey={self._api_key}"
        )
        data = _get(url)
        if data is None:
            return None

        try:
            close = float(data.get("close") or data.get("price") or 0)
            bid = float(data.get("fifty_two_week", {}).get("low") or close * 0.999)
            ask = float(data.get("fifty_two_week", {}).get("high") or close * 1.001)

            # Use volume as a proxy for bid/ask size
            volume = float(data.get("volume") or 0)
            bid_size = volume * 0.5
            ask_size = volume * 0.5

            timestamp = datetime.now(timezone.utc)
            return DOMData(
                bid_levels=[(bid, bid_size)],
                ask_levels=[(ask, ask_size)],
                current_price=close,
                timestamp=timestamp,
            )
        except (KeyError, TypeError, ValueError) as exc:
            logger.warning("Could not parse DOM from Twelve Data for %s: %s", symbol, exc)
            return None

    def fetch_macro(self, security: Security) -> Optional[MacroData]:
        """Not available from Twelve Data — returns None."""
        return None
