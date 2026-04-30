"""API key configuration for real data providers.

Keys are stored here for convenience. In production, prefer loading from
environment variables or a secrets manager.
"""

from __future__ import annotations

import os

# Twelve Data
TWELVE_DATA_API_KEY: str = os.environ.get(
    "TWELVE_DATA_API_KEY", "f93eef363f474608aa4064002c9c3bb6"
)

# Polygon.io
POLYGON_API_KEY: str = os.environ.get(
    "POLYGON_API_KEY", "v8LZl6tQjNwDsN3v3TYUelmDvOfAMzFI"
)

# FRED (Federal Reserve Bank of St. Louis)
FRED_API_KEY: str = os.environ.get(
    "FRED_API_KEY", "aabc8a18bbe60d24323925ad55aff981"
)

# Alpha Vantage
ALPHA_VANTAGE_API_KEY: str = os.environ.get(
    "ALPHA_VANTAGE_API_KEY", "9U5ZP5EJ40MAIYST"
)
