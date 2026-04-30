"""Alpha Vantage real-market data provider.

Fetches FX rates, equity tick volume, and macro indicators from the
Alpha Vantage REST API (https://www.alphavantage.co).

API key: configured at construction time.
Docs: https://www.alphavantage.co/documentation/
"""

from __future__ import annotations

import logging
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

_BASE_URL = "https://www.alphavantage.co/query"


def _get(params: dict) -> Optional[dict]:
    """Perform a GET request to Alpha Vantage and return parsed JSON."""
    query = urllib.parse.urlencode(params)
    url = f"{_BASE_URL}?{query}"
    try:
        with urllib.request.urlopen(url, timeout=15) as resp:
            raw = resp.read().decode("utf-8")
            data = json.loads(raw)
            # Alpha Vantage returns error messages in a top-level "Note" or
            # "Information" key when rate-limited or on error.
            if "Note" in data:
                logger.warning("Alpha Vantage rate limit: %s", data["Note"])
                return None
            if "Information" in data:
                logger.warning("Alpha Vantage info: %s", data["Information"])
                return None
            if "Error Message" in data:
                logger.warning("Alpha Vantage error: %s", data["Error Message"])
                return None
            return data
    except Exception as exc:
        logger.warning("Alpha Vantage request failed: %s", exc)
        return None


def _parse_fx_pair(identifier: str) -> tuple[str, str]:
    """Parse 'EUR/USD' → ('EUR', 'USD')."""
    parts = identifier.replace("-", "/").split("/")
    if len(parts) == 2:
        return parts[0].upper(), parts[1].upper()
    return identifier.upper(), "USD"


class AlphaVantageProvider(DataProviderAdapter):
    """DataProviderAdapter backed by the Alpha Vantage REST API.

    Provides:
    - fetch_vix()          — via CBOE VIX daily data (TIME_SERIES_DAILY)
    - fetch_audjpy()       — via FX_INTRADAY for AUD/JPY
    - fetch_tick_volume()  — via TIME_SERIES_INTRADAY (equities) or FX_INTRADAY (FX)
    - fetch_macro()        — via REAL_GDP, CPI, FEDERAL_FUNDS_RATE, INFLATION

    Returns None for retail_positioning, footprint, and DOM (not available
    from Alpha Vantage).

    Args:
        api_key: Your Alpha Vantage API key.
    """

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

    # ------------------------------------------------------------------
    # DataProviderAdapter interface
    # ------------------------------------------------------------------

    def fetch_retail_positioning(self, security: Security) -> Optional[RetailPositioning]:
        """Not available from Alpha Vantage — returns None."""
        return None

    def fetch_vix(self) -> Optional[float]:
        """Fetch the most recent VIX value from Alpha Vantage via GLOBAL_QUOTE."""
        data = _get({
            "function": "GLOBAL_QUOTE",
            "symbol": "VIX",
            "apikey": self._api_key,
        })
        if data is None:
            return None
        try:
            quote = data.get("Global Quote", {})
            price = quote.get("05. price") or quote.get("08. previous close")
            if price:
                return float(price)
        except (KeyError, TypeError, ValueError) as exc:
            logger.warning("Could not parse VIX from Alpha Vantage GLOBAL_QUOTE: %s", exc)
        return None

    def fetch_audjpy(self) -> Optional[float]:
        """Fetch the current AUD/JPY exchange rate from Alpha Vantage."""
        data = _get({
            "function": "CURRENCY_EXCHANGE_RATE",
            "from_currency": "AUD",
            "to_currency": "JPY",
            "apikey": self._api_key,
        })
        if data is None:
            return None

        try:
            rate_info = data.get("Realtime Currency Exchange Rate", {})
            return float(rate_info["5. Exchange Rate"])
        except (KeyError, TypeError, ValueError) as exc:
            logger.warning("Could not parse AUD/JPY from Alpha Vantage: %s", exc)
            return None

    def fetch_tick_volume(self, security: Security) -> Optional[TickVolumeData]:
        """Fetch tick volume data from Alpha Vantage.

        Uses FX_INTRADAY for FX pairs and TIME_SERIES_INTRADAY for equities.
        Computes current volume, 20-period average, and resistance break flag.
        """
        asset_class = security.asset_class.value

        if asset_class == "FX":
            return self._fetch_fx_volume(security)
        elif asset_class in ("Equity", "Index"):
            return self._fetch_equity_volume(security)
        elif asset_class == "Crypto":
            return self._fetch_crypto_volume(security)
        return None

    def _fetch_fx_volume(self, security: Security) -> Optional[TickVolumeData]:
        """Fetch FX intraday volume from Alpha Vantage."""
        base, quote = _parse_fx_pair(security.identifier)
        data = _get({
            "function": "FX_INTRADAY",
            "from_symbol": base,
            "to_symbol": quote,
            "interval": "60min",
            "outputsize": "compact",
            "apikey": self._api_key,
        })
        if data is None:
            return None

        ts_key = "Time Series FX (60min)"
        if ts_key not in data:
            return None

        return self._parse_volume_series(data[ts_key])

    def _fetch_equity_volume(self, security: Security) -> Optional[TickVolumeData]:
        """Fetch equity intraday volume from Alpha Vantage."""
        data = _get({
            "function": "TIME_SERIES_INTRADAY",
            "symbol": security.identifier,
            "interval": "60min",
            "outputsize": "compact",
            "apikey": self._api_key,
        })
        if data is None:
            return None

        ts_key = "Time Series (60min)"
        if ts_key not in data:
            return None

        return self._parse_volume_series(data[ts_key])

    def _fetch_crypto_volume(self, security: Security) -> Optional[TickVolumeData]:
        """Fetch crypto intraday volume from Alpha Vantage."""
        base, quote = _parse_fx_pair(security.identifier)
        data = _get({
            "function": "CRYPTO_INTRADAY",
            "symbol": base,
            "market": quote,
            "interval": "60min",
            "outputsize": "compact",
            "apikey": self._api_key,
        })
        if data is None:
            return None

        ts_key = "Time Series Crypto (60min)"
        if ts_key not in data:
            return None

        return self._parse_volume_series(data[ts_key])

    def _parse_volume_series(self, ts: dict) -> Optional[TickVolumeData]:
        """Parse a time-series dict into TickVolumeData."""
        if not ts:
            return None

        sorted_dates = sorted(ts.keys(), reverse=True)
        if len(sorted_dates) < 5:
            return None

        try:
            current_bar = ts[sorted_dates[0]]
            current_volume = float(current_bar.get("5. volume", current_bar.get("5. Volume", 0)))

            prior_volumes = []
            for date_key in sorted_dates[1:21]:
                bar = ts[date_key]
                vol = float(bar.get("5. volume", bar.get("5. Volume", 0)))
                prior_volumes.append(vol)

            avg_20 = sum(prior_volumes) / len(prior_volumes) if prior_volumes else current_volume

            # Resistance break: latest close > max high of prior 4 bars
            latest_close = float(
                current_bar.get("4. close", current_bar.get("4. Close", 0))
            )
            prior_highs = []
            for date_key in sorted_dates[1:5]:
                bar = ts[date_key]
                high = float(bar.get("2. high", bar.get("2. High", 0)))
                prior_highs.append(high)

            price_broke_resistance = (
                latest_close > max(prior_highs) if prior_highs else False
            )

            return TickVolumeData(
                current=current_volume,
                avg_20_period=avg_20,
                price_broke_4h_resistance=price_broke_resistance,
                timestamp=datetime.now(timezone.utc),
            )
        except (KeyError, TypeError, ValueError, ZeroDivisionError) as exc:
            logger.warning("Could not parse volume series from Alpha Vantage: %s", exc)
            return None

    def fetch_footprint(self, security: Security) -> Optional[FootprintData]:
        """Not available from Alpha Vantage — returns None."""
        return None

    def fetch_dom(self, security: Security) -> Optional[DOMData]:
        """Not available from Alpha Vantage — returns None."""
        return None

    def fetch_macro(self, security: Security) -> Optional[MacroData]:
        """Fetch macro-economic data from Alpha Vantage economic indicators.

        Uses:
        - REAL_GDP as a PMI proxy (quarterly)
        - CPI for inflation
        - FEDERAL_FUNDS_RATE for US interest rate
        - INFLATION for CPI YoY

        Note: Alpha Vantage macro endpoints are US-centric. For non-USD
        securities, this provides the US macro context as a baseline.
        """
        # CPI (monthly)
        cpi_data = _get({
            "function": "CPI",
            "interval": "monthly",
            "apikey": self._api_key,
        })
        cpi_current, cpi_prior = self._parse_av_series(cpi_data)

        # Federal Funds Rate (monthly)
        rate_data = _get({
            "function": "FEDERAL_FUNDS_RATE",
            "interval": "monthly",
            "apikey": self._api_key,
        })
        rate_current, rate_prior = self._parse_av_series(rate_data)

        # Real GDP as PMI proxy (quarterly)
        gdp_data = _get({
            "function": "REAL_GDP",
            "interval": "quarterly",
            "apikey": self._api_key,
        })
        gdp_current, gdp_prior = self._parse_av_series(gdp_data)

        # Use GDP growth as PMI proxy (scale to PMI-like range 40-60)
        pmi_current: Optional[float] = None
        pmi_prior: Optional[float] = None
        if gdp_current is not None and gdp_prior is not None:
            # GDP growth rate as PMI proxy: positive growth → above 50
            growth_rate = (gdp_current - gdp_prior) / gdp_prior * 100 if gdp_prior else 0
            pmi_current = 50.0 + growth_rate
            pmi_prior = 50.0  # baseline

        # Infer stance from rate trend
        stance: Optional[str] = "neutral"
        if rate_current is not None and rate_prior is not None:
            if rate_current > rate_prior:
                stance = "hawkish"
            elif rate_current < rate_prior:
                stance = "dovish"

        # Interest rate differential (vs 0 baseline for non-FX)
        ird: Optional[float] = None
        if rate_current is not None:
            ird = rate_current * 100  # convert % to bps vs 0 baseline

        if pmi_current is None and cpi_current is None:
            return None

        return MacroData(
            pmi=pmi_current,
            prior_pmi=pmi_prior,
            cpi=cpi_current,
            prior_cpi=cpi_prior,
            central_bank_stance=stance,
            interest_rate_differential=ird,
            timestamp=datetime.now(timezone.utc),
        )

    @staticmethod
    def _parse_av_series(data: Optional[dict]) -> tuple[Optional[float], Optional[float]]:
        """Parse an Alpha Vantage economic series response into (current, prior) values."""
        if data is None or "data" not in data:
            return None, None

        observations = data["data"]
        if not observations:
            return None, None

        # Sorted descending by date
        sorted_obs = sorted(observations, key=lambda x: x.get("date", ""), reverse=True)

        values: list[float] = []
        for obs in sorted_obs:
            val = obs.get("value", ".")
            if val and val != ".":
                try:
                    values.append(float(val))
                except ValueError:
                    continue
            if len(values) >= 2:
                break

        current = values[0] if len(values) > 0 else None
        prior = values[1] if len(values) > 1 else None
        return current, prior
