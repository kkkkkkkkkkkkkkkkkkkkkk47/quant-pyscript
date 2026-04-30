"""Unit tests for WeightProfileRegistry.

Validates: Requirements 2.2
"""

import pytest

from quant_ratings.config.weight_profile_registry import WeightProfileRegistry
from quant_ratings.models.enums import AssetClass
from quant_ratings.models.weight_profile import WeightProfile


class TestDefaultFXProfiles:
    """Verify exact weight values for the three default FX profiles."""

    def setup_method(self):
        self.registry = WeightProfileRegistry()

    def test_fx_major_weights(self):
        """FX Major profile: sentiment=20, orderflow=30, economic=50."""
        profile = self.registry.get_profile("FX", "Major")
        assert profile.sentiment_pct == 20.0
        assert profile.orderflow_pct == 30.0
        assert profile.economic_pct == 50.0

    def test_fx_volatile_cross_weights(self):
        """FX Volatile_Cross profile: sentiment=40, orderflow=40, economic=20."""
        profile = self.registry.get_profile("FX", "Volatile_Cross")
        assert profile.sentiment_pct == 40.0
        assert profile.orderflow_pct == 40.0
        assert profile.economic_pct == 20.0

    def test_fx_emerging_weights(self):
        """FX Emerging profile: sentiment=10, orderflow=10, economic=80."""
        profile = self.registry.get_profile("FX", "Emerging")
        assert profile.sentiment_pct == 10.0
        assert profile.orderflow_pct == 10.0
        assert profile.economic_pct == 80.0


class TestRegisterOverwrite:
    """Verify that register() overwrites an existing profile."""

    def test_register_overwrites_existing_profile(self):
        """Registering a new profile for an existing key replaces the old one."""
        registry = WeightProfileRegistry()

        # Confirm the original FX Major weights
        original = registry.get_profile("FX", "Major")
        assert original.sentiment_pct == 20.0

        # Register a replacement profile with different weights
        new_profile = WeightProfile(
            asset_class="FX",
            sub_category="Major",
            sentiment_pct=25.0,
            orderflow_pct=35.0,
            economic_pct=40.0,
        )
        registry.register(new_profile)

        # get_profile should now return the new weights
        updated = registry.get_profile("FX", "Major")
        assert updated.sentiment_pct == 25.0
        assert updated.orderflow_pct == 35.0
        assert updated.economic_pct == 40.0


class TestFallbackProfile:
    """Verify the equal-weight fallback for unknown asset classes."""

    def test_unknown_asset_class_returns_equal_weight_fallback(self):
        """get_profile for an unknown key returns the 33.3/33.3/33.4 fallback."""
        registry = WeightProfileRegistry()
        profile = registry.get_profile("Unknown", None)
        assert abs(profile.sentiment_pct - 33.3) < 0.01
        assert abs(profile.orderflow_pct - 33.3) < 0.01
        assert abs(profile.economic_pct - 33.4) < 0.01

    def test_fallback_does_not_raise(self):
        """get_profile for an unknown key must not raise any exception."""
        registry = WeightProfileRegistry()
        profile = registry.get_profile("NonExistentClass", "NonExistentSub")
        assert profile is not None


class TestEnumInput:
    """Verify that AssetClass enum values are accepted by get_profile."""

    def test_enum_input_returns_same_as_string(self):
        """get_profile(AssetClass.FX, 'Major') equals get_profile('FX', 'Major')."""
        registry = WeightProfileRegistry()
        profile_enum = registry.get_profile(AssetClass.FX, "Major")
        profile_str = registry.get_profile("FX", "Major")
        assert profile_enum.sentiment_pct == profile_str.sentiment_pct
        assert profile_enum.orderflow_pct == profile_str.orderflow_pct
        assert profile_enum.economic_pct == profile_str.economic_pct
