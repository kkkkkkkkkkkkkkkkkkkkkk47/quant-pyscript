"""Unit tests for SecurityRegistry.

Validates: Requirements 6.2
"""

import json
import os

import pytest

from quant_ratings.config.security_registry import SecurityRegistry
from quant_ratings.models.enums import AssetClass
from quant_ratings.models.security import Security

# Path to the shared fixture file
FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")
SECURITIES_FIXTURE = os.path.join(FIXTURES_DIR, "securities.json")


class TestLoad:
    """Verify load() populates the registry from a JSON fixture file."""

    def setup_method(self):
        self.registry = SecurityRegistry()
        self.registry.load(SECURITIES_FIXTURE)

    def test_load_populates_all_securities(self):
        """After load(), all_securities() returns all entries from the fixture."""
        securities = self.registry.all_securities()
        assert len(securities) == 3

    def test_load_eurusd_identifier_and_asset_class(self):
        """get('EUR/USD') returns a Security with correct identifier and asset_class."""
        security = self.registry.get("EUR/USD")
        assert security is not None
        assert security.identifier == "EUR/USD"
        assert security.asset_class == AssetClass.FX

    def test_load_eurusd_sub_category(self):
        """get('EUR/USD') returns a Security with sub_category='Major'."""
        security = self.registry.get("EUR/USD")
        assert security is not None
        assert security.sub_category == "Major"

    def test_load_aapl_asset_class(self):
        """get('AAPL') returns a Security with asset_class=AssetClass.Equity."""
        security = self.registry.get("AAPL")
        assert security is not None
        assert security.asset_class == AssetClass.Equity

    def test_load_gbpjpy_present(self):
        """get('GBP/JPY') returns a Security after loading the fixture."""
        security = self.registry.get("GBP/JPY")
        assert security is not None
        assert security.identifier == "GBP/JPY"
        assert security.sub_category == "Volatile_Cross"


class TestGetUnknown:
    """Verify get() returns None for an unknown identifier."""

    def test_get_unknown_returns_none(self):
        """get('UNKNOWN') returns None when the identifier is not in the registry."""
        registry = SecurityRegistry()
        result = registry.get("UNKNOWN")
        assert result is None

    def test_get_unknown_after_load_returns_none(self):
        """get('UNKNOWN') returns None even after loading a fixture."""
        registry = SecurityRegistry()
        registry.load(SECURITIES_FIXTURE)
        result = registry.get("UNKNOWN")
        assert result is None


class TestAdd:
    """Verify add() registers a security at runtime."""

    def test_add_security_then_get_returns_it(self):
        """After add(), get() returns the added Security."""
        registry = SecurityRegistry()
        security = Security(identifier="BTC/USD", asset_class=AssetClass.Crypto)
        registry.add(security)
        result = registry.get("BTC/USD")
        assert result is not None
        assert result.identifier == "BTC/USD"
        assert result.asset_class == AssetClass.Crypto

    def test_add_security_appears_in_all_securities(self):
        """After add(), all_securities() includes the new Security."""
        registry = SecurityRegistry()
        security = Security(identifier="ETH/USD", asset_class=AssetClass.Crypto)
        registry.add(security)
        all_ids = [s.identifier for s in registry.all_securities()]
        assert "ETH/USD" in all_ids

    def test_add_overwrites_existing_identifier(self):
        """add() with a duplicate identifier overwrites the existing entry."""
        registry = SecurityRegistry()
        original = Security(identifier="AAPL", asset_class=AssetClass.Equity)
        registry.add(original)

        updated = Security(
            identifier="AAPL",
            asset_class=AssetClass.Equity,
            primary_region="US",
        )
        registry.add(updated)

        result = registry.get("AAPL")
        assert result is not None
        assert result.primary_region == "US"


class TestAllSecuritiesEmpty:
    """Verify all_securities() returns an empty list when the registry is empty."""

    def test_all_securities_empty_on_new_registry(self):
        """A freshly created registry has no securities."""
        registry = SecurityRegistry()
        assert registry.all_securities() == []

    def test_all_securities_returns_list_type(self):
        """all_securities() always returns a list, even when empty."""
        registry = SecurityRegistry()
        result = registry.all_securities()
        assert isinstance(result, list)


class TestLoadWithTmpPath:
    """Verify load() works with a dynamically created JSON file (tmp_path)."""

    def test_load_from_tmp_path(self, tmp_path):
        """load() correctly reads a JSON file written to a temporary directory."""
        data = [
            {"identifier": "USD/JPY", "asset_class": "FX", "sub_category": "Major"},
            {"identifier": "GOLD", "asset_class": "Commodity"},
        ]
        fixture = tmp_path / "test_securities.json"
        fixture.write_text(json.dumps(data), encoding="utf-8")

        registry = SecurityRegistry()
        registry.load(str(fixture))

        assert len(registry.all_securities()) == 2
        usd_jpy = registry.get("USD/JPY")
        assert usd_jpy is not None
        assert usd_jpy.asset_class == AssetClass.FX
        gold = registry.get("GOLD")
        assert gold is not None
        assert gold.asset_class == AssetClass.Commodity
