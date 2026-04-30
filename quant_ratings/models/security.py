"""Security data model for the Quant Ratings engine."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from quant_ratings.models.enums import AssetClass


@dataclass
class Security:
    """Represents a tradable instrument supported by the platform."""

    identifier: str
    """Unique identifier, e.g. 'EUR/USD', 'AAPL', 'BTC/USD'."""

    asset_class: AssetClass
    """Top-level asset class: FX | Equity | Index | Commodity | Crypto."""

    sub_category: Optional[str] = field(default=None)
    """FX sub-category only: 'Major' | 'Volatile_Cross' | 'Emerging'."""

    primary_region: Optional[str] = field(default=None)
    """Primary economic region for non-FX economic scoring (e.g. 'US', 'EU')."""

    denominating_currency: Optional[str] = field(default=None)
    """Denominating currency for non-FX instruments (e.g. 'USD')."""
