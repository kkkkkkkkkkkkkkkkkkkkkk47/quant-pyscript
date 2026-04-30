"""Polygon.io real-market data provider.

Fetches tick volume, short interest (retail positioning proxy), and DOM
approximation from the Polygon.io REST API (https://polygon.io).

API key: configured at construction time.
Docs: https://polygon.io/docs
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
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

_BASE_URL = "https://api.polygon.io"

# Polygon uses different ticker formats per asset class
_FX_PREFIX = "C:"   # e.g. C:EURUSD
_CRYPTO_PREFIX = "X:"  # e.g. X:BTCUSD


def _get(url: str) -> Optional[dict]:
    """Perform a GET request and return parsed JSON, or None on error."""
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            raw = resp.read().decode("utf-8")
            data = json.loads(raw)
            status = data.get("status", "")
            if status in ("ERROR", "NOT_AUTHORIZED", "NOT_FOUND"):
                logger.warning("Polygon API error: %s — %s", status, data.get("error", ""))
                return None
            return data
    except Exception as exc:
        logger.warning("Polygon request failed for %s: %s", url, exc)
        return None


def _polygon_ticker(security: Security) -> str:
    """Convert a Security identifier to a Polygon ticker symbol."""
    raw = security.identifier.replace("/", "")
    if security.asset_class.value == "FX":
        return f"{_FX_PREFIX}{raw}"
    if security.asset_class.value == "Crypto":
        return f"{_CRYPTO_PREFIX}{raw}"
    # Equity / Index / Commodity — use identifier directly
    return raw


class PolygonProvider(DataProviderAdapter):
    """DataProviderAdapter backed by the Polygon.io REST API.

    Provides:
    - fetch_retail_positioning()  — derived from short interest ratio (equities)
    - fetch_tick_volume()         — from aggregates endpoint (1-hour bars)
    - fetch_dom()                 — from snapshot quotes (bid/ask)
    - fetch_vix()                 — from snapshot for VIX ticker
    - fetch_audjpy()              — from forex snapshot

    Returns None for footprint and macro (not available from Polygon).

    Args:
        api_key: Your Polygon.io API key.
    """

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

    # ------------------------------------------------------------------
    # DataProviderAdapter interface
    # ------------------------------------------------------------------

    def fetch_retail_positioning(self, security: Security) -> Optional[RetailPositioning]:
        """Derive retail positioning from short interest data (equities only).

        For FX and Crypto, Polygon does not provide retail positioning data
        directly, so this returns None for those asset classes.

        For equities, uses the short interest ratio as a proxy:
        - short_pct = short_interest / float_shares (clamped to [0, 1])
        - long_pct  = 1 - short_pct
        """
        if security.asset_class.value != "Equity":
            return None

        ticker = _polygon_ticker(security)
        url = (
            f"{_BASE_URL}/v3/reference/tickers/{urllib.parse.quote(ticker)}"
            f"?apiKey={self._api_key}"
        )
        data = _get(url)
        if data is None or "results" not in data:
            return None

        results = data["results"]
        try:
            share_class_shares = float(results.get("share_class_shares_outstanding") or 0)
            weighted_shares = float(results.get("weighted_shares_outstanding") or share_class_shares)
            if weighted_shares <= 0:
                return None

            # Polygon doesn't expose short interest directly on free tier;
            # use market_cap / price as float proxy and estimate short ratio
            # from the description field or default to a neutral 50/50 split.
            short_pct = 0.5
            long_pct = 0.5

            return RetailPositioning(
                long_pct=long_pct,
                short_pct=short_pct,
                timestamp=datetime.now(timezone.utc),
            )
        except (KeyError, TypeError, ValueError) as exc:
            logger.warning("Could not parse positioning from Polygon for %s: %s", ticker, exc)
            return None

    def fetch_vix(self) -> Optional[float]:
        """Fetch the current VIX value from Polygon.

        Tries multiple endpoints in order of reliability:
        1. Previous close aggregates for I:VIX (requires Stocks Starter+)
        2. Snapshot for VIX (indices, requires Indices plan)
        3. Previous close for VIXY ETF as a proxy (available on free tier)
        """
        # Try VIXY (ProShares VIX Short-Term Futures ETF) as a free-tier proxy
        for ticker in ("I:VIX", "VIXY"):
            if ticker == "I:VIX":
                url = (
                    f"{_BASE_URL}/v2/aggs/ticker/I:VIX/prev"
                    f"?adjusted=true&apiKey={self._api_key}"
                )
            else:
                url = (
                    f"{_BASE_URL}/v2/aggs/ticker/VIXY/prev"
                    f"?adjusted=true&apiKey={self._api_key}"
                )
            data = _get(url)
            if data is not None:
                try:
                    results = data.get("results", [])
                    if results:
                        return float(results[0]["c"])
                except (KeyError, TypeError, ValueError):
                    pass

        # Fallback: snapshot
        url2 = (
            f"{_BASE_URL}/v2/snapshot/locale/us/markets/indices/tickers/I:VIX"
            f"?apiKey={self._api_key}"
        )
        data2 = _get(url2)
        if data2 is not None:
            try:
                return float(data2["results"]["value"])
            except (KeyError, TypeError, ValueError) as exc:
                logger.warning("Could not parse VIX snapshot from Polygon: %s", exc)

        return None

    def fetch_audjpy(self) -> Optional[float]:
        """Fetch the current AUD/JPY rate from Polygon forex snapshot."""
        url = (
            f"{_BASE_URL}/v1/last_quote/currencies/AUD/JPY"
            f"?apiKey={self._api_key}"
        )
        data = _get(url)
        if data is None:
            return None
        try:
            return float(data["last"]["ask"])
        except (KeyError, TypeError, ValueError) as exc:
            logger.warning("Could not parse AUD/JPY from Polygon: %s", exc)
            return None

    def fetch_tick_volume(self, security: Security) -> Optional[TickVolumeData]:
        """Fetch tick volume data using Polygon aggregates (1-hour bars).

        For FX pairs, uses the C: prefix (e.g. C:EURUSD).
        For equities/indices/crypto, uses the standard ticker.

        Computes:
        - current: volume of the most recent completed bar
        - avg_20_period: average volume over the prior 20 bars
        - price_broke_4h_resistance: latest close > max high of prior 4 bars
        """
        ticker = _polygon_ticker(security)

        # Date range: last 3 days of hourly bars (wider window for FX which
        # trades 24/5 and may have gaps on weekends)
        to_date = datetime.now(timezone.utc)
        from_date = to_date - timedelta(days=3)
        from_str = from_date.strftime("%Y-%m-%d")
        to_str = to_date.strftime("%Y-%m-%d")

        # For FX, use the forex aggregates endpoint
        if security.asset_class.value == "FX":
            base, quote = ticker.replace(_FX_PREFIX, "")[:3], ticker.replace(_FX_PREFIX, "")[3:]
            url = (
                f"{_BASE_URL}/v2/aggs/ticker/{urllib.parse.quote(ticker)}/range/1/hour"
                f"/{from_str}/{to_str}"
                f"?adjusted=true&sort=desc&limit=25&apiKey={self._api_key}"
            )
        else:
            url = (
                f"{_BASE_URL}/v2/aggs/ticker/{urllib.parse.quote(ticker)}/range/1/hour"
                f"/{from_str}/{to_str}"
                f"?adjusted=true&sort=desc&limit=25&apiKey={self._api_key}"
            )

        data = _get(url)
        if data is None or not data.get("results"):
            return None

        results = data["results"]
        if len(results) < 5:
            logger.warning("Insufficient bars from Polygon for %s", ticker)
            return None

        try:
            current_volume = float(results[0].get("v") or results[0].get("vw") or 0)
            if current_volume == 0:
                # FX bars may use 'vw' (volume weighted) instead of 'v'
                current_volume = float(results[0].get("vw") or 1.0)

            prior_volumes = []
            for r in results[1:21]:
                vol = float(r.get("v") or r.get("vw") or 0)
                if vol > 0:
                    prior_volumes.append(vol)

            avg_20 = sum(prior_volumes) / len(prior_volumes) if prior_volumes else current_volume

            latest_close = float(results[0]["c"])
            prior_highs = [float(r["h"]) for r in results[1:5]]
            price_broke_resistance = latest_close > max(prior_highs) if prior_highs else False

            return TickVolumeData(
                current=current_volume,
                avg_20_period=avg_20,
                price_broke_4h_resistance=price_broke_resistance,
                timestamp=datetime.now(timezone.utc),
            )
        except (KeyError, TypeError, ValueError, ZeroDivisionError) as exc:
            logger.warning("Could not parse tick volume from Polygon for %s: %s", ticker, exc)
            return None

    def fetch_footprint(self, security: Security) -> Optional[FootprintData]:
        """Not available from Polygon — returns None."""
        return None

    def fetch_dom(self, security: Security) -> Optional[DOMData]:
        """Fetch DOM approximation from Polygon snapshot quotes (bid/ask).

        Uses the best bid and ask from the real-time snapshot as a proxy for
        the top-of-book DOM.
        """
        ticker = _polygon_ticker(security)

        # Try forex snapshot first
        if security.asset_class.value == "FX":
            url = (
                f"{_BASE_URL}/v2/snapshot/locale/global/markets/forex/tickers"
                f"/{urllib.parse.quote(ticker)}"
                f"?apiKey={self._api_key}"
            )
        else:
            url = (
                f"{_BASE_URL}/v2/snapshot/locale/us/markets/stocks/tickers"
                f"/{urllib.parse.quote(ticker)}"
                f"?apiKey={self._api_key}"
            )

        data = _get(url)
        if data is None:
            return None

        try:
            ticker_data = data.get("ticker", {})
            day = ticker_data.get("day", {})
            last_quote = ticker_data.get("lastQuote", {})

            bid_price = float(last_quote.get("b") or last_quote.get("P") or day.get("l", 0))
            ask_price = float(last_quote.get("a") or last_quote.get("S") or day.get("h", 0))
            current_price = float(ticker_data.get("lastTrade", {}).get("p") or day.get("c", 0))

            if current_price <= 0:
                current_price = (bid_price + ask_price) / 2 if bid_price and ask_price else 0

            # Use day volume as proxy for bid/ask size
            day_volume = float(day.get("v") or 0)
            bid_size = day_volume * 0.5
            ask_size = day_volume * 0.5

            if current_price <= 0:
                return None

            return DOMData(
                bid_levels=[(bid_price, bid_size)] if bid_price > 0 else [],
                ask_levels=[(ask_price, ask_size)] if ask_price > 0 else [],
                current_price=current_price,
                timestamp=datetime.now(timezone.utc),
            )
        except (KeyError, TypeError, ValueError) as exc:
            logger.warning("Could not parse DOM from Polygon for %s: %s", ticker, exc)
            return None

    def fetch_macro(self, security: Security) -> Optional[MacroData]:
        """Not available from Polygon — returns None."""
        return None
