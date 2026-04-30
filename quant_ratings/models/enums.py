"""Enumerations for the Quant Ratings engine."""

from __future__ import annotations

from enum import Enum


class AssetClass(str, Enum):
    """Top-level grouping of tradable securities."""

    FX = "FX"
    Equity = "Equity"
    Index = "Index"
    Commodity = "Commodity"
    Crypto = "Crypto"
