"""Factory for building a fully-wired RatingEngine with live data providers.

Usage::

    from quant_ratings.config.engine_factory import build_live_engine

    engine = build_live_engine()
    summary = engine.run_cycle()
"""

from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy import create_engine as sa_create_engine

from quant_ratings.aggregator.aggregator import Aggregator
from quant_ratings.config.api_keys import (
    ALPHA_VANTAGE_API_KEY,
    FRED_API_KEY,
    POLYGON_API_KEY,
    TWELVE_DATA_API_KEY,
)
from quant_ratings.config.security_registry import SecurityRegistry
from quant_ratings.config.weight_profile_registry import WeightProfileRegistry
from quant_ratings.engine.data_manager import DataManager
from quant_ratings.engine.rating_engine import RatingEngine
from quant_ratings.models.enums import AssetClass
from quant_ratings.models.security import Security
from quant_ratings.observability.alert_sink import LogAlertSink
from quant_ratings.observability.logger import JsonStructuredLogger
from quant_ratings.persistence.sqlalchemy_store import SQLAlchemyRatingStore
from quant_ratings.providers.live_provider import LiveDataProvider
from quant_ratings.scorers.economic_scorer import EconomicScorer
from quant_ratings.scorers.orderflow_scorer import OrderFlowScorer
from quant_ratings.scorers.sentiment_scorer import SentimentScorer

logger = logging.getLogger(__name__)

# Default securities to rate when no external registry file is provided
_DEFAULT_SECURITIES: list[Security] = [
    # FX Majors
    Security(identifier="EUR/USD", asset_class=AssetClass.FX, sub_category="Major"),
    Security(identifier="GBP/USD", asset_class=AssetClass.FX, sub_category="Major"),
    Security(identifier="USD/JPY", asset_class=AssetClass.FX, sub_category="Major"),
    # FX Volatile Crosses
    Security(identifier="GBP/JPY", asset_class=AssetClass.FX, sub_category="Volatile_Cross"),
    # FX Emerging
    Security(identifier="USD/ZAR", asset_class=AssetClass.FX, sub_category="Emerging"),
    # Equities
    Security(
        identifier="AAPL",
        asset_class=AssetClass.Equity,
        primary_region="US",
        denominating_currency="USD",
    ),
    Security(
        identifier="MSFT",
        asset_class=AssetClass.Equity,
        primary_region="US",
        denominating_currency="USD",
    ),
    # Crypto
    Security(identifier="BTC/USD", asset_class=AssetClass.Crypto, denominating_currency="USD"),
    Security(identifier="ETH/USD", asset_class=AssetClass.Crypto, denominating_currency="USD"),
]


def build_live_engine(
    db_url: str = "sqlite:///quant_ratings.db",
    securities_config_path: Optional[str] = None,
    version: str = "0.1.0",
) -> RatingEngine:
    """Build and return a fully-wired RatingEngine using live data providers.

    Args:
        db_url: SQLAlchemy database URL. Defaults to a local SQLite file.
        securities_config_path: Optional path to a YAML/JSON securities config
            file. If None, the default set of securities is used.
        version: Software version string for structured log entries.

    Returns:
        A configured :class:`~quant_ratings.engine.rating_engine.RatingEngine`
        ready to call ``run_cycle()`` on.
    """
    # --- Security registry ---
    security_registry = SecurityRegistry()
    if securities_config_path:
        security_registry.load(securities_config_path)
        logger.info("Loaded securities from %s", securities_config_path)
    else:
        for sec in _DEFAULT_SECURITIES:
            security_registry.add(sec)
        logger.info("Using %d default securities", len(_DEFAULT_SECURITIES))

    # --- Weight profile registry (pre-seeded with FX defaults) ---
    weight_registry = WeightProfileRegistry()

    # --- Live data provider ---
    live_provider = LiveDataProvider(
        twelve_data_api_key=TWELVE_DATA_API_KEY,
        polygon_api_key=POLYGON_API_KEY,
        fred_api_key=FRED_API_KEY,
        alpha_vantage_api_key=ALPHA_VANTAGE_API_KEY,
    )
    data_manager = DataManager(providers=[live_provider])

    # --- Scorers and aggregator ---
    sentiment_scorer = SentimentScorer()
    orderflow_scorer = OrderFlowScorer()
    economic_scorer = EconomicScorer()
    aggregator = Aggregator()

    # --- Persistence ---
    db_engine = sa_create_engine(db_url)
    store = SQLAlchemyRatingStore(db_engine)

    # --- Observability ---
    structured_logger = JsonStructuredLogger(version=version)
    alert_sink = LogAlertSink()

    # --- Wire everything together ---
    return RatingEngine(
        security_registry=security_registry,
        weight_registry=weight_registry,
        data_manager=data_manager,
        sentiment_scorer=sentiment_scorer,
        orderflow_scorer=orderflow_scorer,
        economic_scorer=economic_scorer,
        aggregator=aggregator,
        store=store,
        alert_sink=alert_sink,
        structured_logger=structured_logger,
    )
