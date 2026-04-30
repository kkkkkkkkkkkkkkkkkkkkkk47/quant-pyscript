"""FRED (Federal Reserve Bank of St. Louis) macro data provider.

Fetches PMI, CPI, and interest rate data from the FRED REST API
(https://fred.stlouisfed.org/docs/api/fred/).

API key: configured at construction time.
Docs: https://fred.stlouisfed.org/docs/api/fred/
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

_BASE_URL = "https://api.stlouisfed.org/fred"

# FRED series IDs for key macro indicators
_SERIES = {
    # US PMI (ISM Manufacturing PMI)
    "US_PMI": "MANEMP",          # Manufacturing employment as PMI proxy
    "US_PMI_COMPOSITE": "NAPM",  # ISM PMI composite
    # US CPI (All Urban Consumers, All Items)
    "US_CPI": "CPIAUCSL",
    # Federal Funds Rate (US benchmark rate)
    "US_RATE": "FEDFUNDS",
    # ECB Main Refinancing Rate (EUR benchmark)
    "EUR_RATE": "ECBDFR",
    # UK Bank Rate
    "GBP_RATE": "BOERUKM",
    # Japan Policy Rate
    "JPY_RATE": "IRSTCI01JPM156N",
    # AUD Cash Rate
    "AUD_RATE": "IRSTCI01AUM156N",
    # EU CPI (HICP)
    "EU_CPI": "CP0000EZ19M086NEST",
    # UK CPI
    "UK_CPI": "GBRCPIALLMINMEI",
}

# Map currency codes to FRED rate series
_CURRENCY_RATE_SERIES: dict[str, str] = {
    "USD": "FEDFUNDS",
    "EUR": "ECBDFR",
    "GBP": "BOERUKM",
    "JPY": "IRSTCI01JPM156N",
    "AUD": "IRSTCI01AUM156N",
    "CAD": "IRSTCI01CAM156N",
    "CHF": "IRSTCI01CHM156N",
    "NZD": "IRSTCI01NZM156N",
}

# Map currency codes to FRED CPI series
_CURRENCY_CPI_SERIES: dict[str, str] = {
    "USD": "CPIAUCSL",
    "EUR": "CP0000EZ19M086NEST",
    "GBP": "GBRCPIALLMINMEI",
    "JPY": "JPNCPIALLMINMEI",
    "AUD": "AUSCPIALLQINMEI",
}

# Map currency codes to FRED PMI series (best available proxy)
# Using ISM Manufacturing for USD, and GDP-based proxies for others
# NAPM was discontinued; use MANEMP (manufacturing employment) as proxy
_CURRENCY_PMI_SERIES: dict[str, str] = {
    "USD": "MANEMP",            # US manufacturing employment (thousands)
    "EUR": "LMUNRRTTEZM156S",   # Euro area unemployment rate (inverse proxy)
    "GBP": "LMUNRRTTGBM156S",   # UK unemployment rate
    "JPY": "LMUNRRTTTJM156S",   # Japan unemployment rate
    "AUD": "LMUNRRTTTAM156S",   # Australia unemployment rate
}

# Fallback is the same — no separate fallback needed
_CURRENCY_PMI_FALLBACK: dict[str, str] = _CURRENCY_PMI_SERIES


def _get(url: str) -> Optional[dict]:
    """Perform a GET request and return parsed JSON, or None on error."""
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw)
    except Exception as exc:
        logger.warning("FRED request failed for %s: %s", url, exc)
        return None


def _latest_value(series_id: str, api_key: str) -> Optional[float]:
    """Fetch the most recent observation value for a FRED series."""
    url = (
        f"{_BASE_URL}/series/observations"
        f"?series_id={urllib.parse.quote(series_id)}"
        f"&api_key={api_key}"
        f"&file_type=json"
        f"&sort_order=desc"
        f"&limit=2"
    )
    data = _get(url)
    if data is None or "observations" not in data:
        return None

    observations = data["observations"]
    for obs in observations:
        val = obs.get("value", ".")
        if val != "." and val is not None:
            try:
                return float(val)
            except ValueError:
                continue
    return None


def _two_latest_values(series_id: str, api_key: str) -> tuple[Optional[float], Optional[float]]:
    """Return (current, prior) values for a FRED series."""
    url = (
        f"{_BASE_URL}/series/observations"
        f"?series_id={urllib.parse.quote(series_id)}"
        f"&api_key={api_key}"
        f"&file_type=json"
        f"&sort_order=desc"
        f"&limit=3"
    )
    data = _get(url)
    if data is None or "observations" not in data:
        return None, None

    observations = data["observations"]
    values: list[float] = []
    for obs in observations:
        val = obs.get("value", ".")
        if val != "." and val is not None:
            try:
                values.append(float(val))
            except ValueError:
                continue
        if len(values) >= 2:
            break

    current = values[0] if len(values) > 0 else None
    prior = values[1] if len(values) > 1 else None
    return current, prior


def _parse_fx_currencies(identifier: str) -> tuple[str, str]:
    """Parse 'EUR/USD' → ('EUR', 'USD')."""
    parts = identifier.replace("-", "/").split("/")
    if len(parts) == 2:
        return parts[0].upper(), parts[1].upper()
    return identifier.upper(), "USD"


def _infer_stance(current_rate: Optional[float], prior_rate: Optional[float]) -> Optional[str]:
    """Infer central bank stance from rate trend."""
    if current_rate is None or prior_rate is None:
        return "neutral"
    if current_rate > prior_rate:
        return "hawkish"
    if current_rate < prior_rate:
        return "dovish"
    return "neutral"


class FredProvider(DataProviderAdapter):
    """DataProviderAdapter backed by the FRED REST API.

    Provides:
    - fetch_macro()  — PMI, CPI, interest rate differential, central bank stance

    Returns None for all other data types (not available from FRED).

    Args:
        api_key: Your FRED API key.
    """

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

    # ------------------------------------------------------------------
    # DataProviderAdapter interface
    # ------------------------------------------------------------------

    def fetch_retail_positioning(self, security: Security) -> Optional[RetailPositioning]:
        """Not available from FRED — returns None."""
        return None

    def fetch_vix(self) -> Optional[float]:
        """Not available from FRED — returns None."""
        return None

    def fetch_audjpy(self) -> Optional[float]:
        """Not available from FRED — returns None."""
        return None

    def fetch_tick_volume(self, security: Security) -> Optional[TickVolumeData]:
        """Not available from FRED — returns None."""
        return None

    def fetch_footprint(self, security: Security) -> Optional[FootprintData]:
        """Not available from FRED — returns None."""
        return None

    def fetch_dom(self, security: Security) -> Optional[DOMData]:
        """Not available from FRED — returns None."""
        return None

    def fetch_macro(self, security: Security) -> Optional[MacroData]:
        """Fetch macro-economic data for *security* from FRED.

        For FX pairs, derives data from the base currency's indicators.
        For non-FX instruments, uses the security's primary_region or
        denominating_currency to select the appropriate FRED series.

        Returns a MacroData instance with PMI, CPI, interest rate differential,
        and inferred central bank stance.
        """
        identifier = security.identifier
        asset_class = security.asset_class.value

        if asset_class == "FX":
            base_ccy, quote_ccy = _parse_fx_currencies(identifier)
        else:
            # For equities/indices/commodities/crypto, use primary region or USD
            region = security.primary_region or "US"
            denom = security.denominating_currency or "USD"
            # Map region to currency
            region_ccy_map = {
                "US": "USD", "EU": "EUR", "UK": "GBP",
                "JP": "JPY", "AU": "AUD", "CA": "CAD",
            }
            base_ccy = region_ccy_map.get(region.upper(), "USD")
            quote_ccy = denom.upper()

        # --- PMI ---
        # Try primary series first, fall back to employment proxy
        pmi_series = _CURRENCY_PMI_SERIES.get(base_ccy)
        pmi_current, pmi_prior = None, None
        if pmi_series:
            pmi_current, pmi_prior = _two_latest_values(pmi_series, self._api_key)

        if pmi_current is None:
            fallback_series = _CURRENCY_PMI_FALLBACK.get(base_ccy, "MANEMP")
            raw_current, raw_prior = _two_latest_values(fallback_series, self._api_key)
            if raw_current is not None:
                # Normalise manufacturing employment to PMI-like scale (40-60)
                # Employment changes are small; use 50 as baseline
                if raw_prior is not None and raw_prior > 0:
                    change_pct = (raw_current - raw_prior) / raw_prior * 100
                    pmi_current = 50.0 + change_pct * 10  # amplify small changes
                    pmi_prior = 50.0
                else:
                    pmi_current = 50.0
                    pmi_prior = 50.0

        # --- CPI ---
        cpi_series = _CURRENCY_CPI_SERIES.get(base_ccy, "CPIAUCSL")
        cpi_current, cpi_prior = _two_latest_values(cpi_series, self._api_key)

        # --- Interest rates ---
        base_rate_series = _CURRENCY_RATE_SERIES.get(base_ccy, "FEDFUNDS")
        quote_rate_series = _CURRENCY_RATE_SERIES.get(quote_ccy, "FEDFUNDS")

        base_rate_current, base_rate_prior = _two_latest_values(base_rate_series, self._api_key)
        quote_rate_current, _ = _two_latest_values(quote_rate_series, self._api_key)

        # Interest rate differential in basis points
        ird: Optional[float] = None
        if base_rate_current is not None and quote_rate_current is not None:
            ird = (base_rate_current - quote_rate_current) * 100  # convert % to bps

        # Central bank stance inferred from rate trend
        stance = _infer_stance(base_rate_current, base_rate_prior)

        # If we got nothing useful, return None
        if pmi_current is None and cpi_current is None and ird is None:
            logger.warning(
                "No macro data available from FRED for %s (base=%s)",
                identifier, base_ccy,
            )
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
