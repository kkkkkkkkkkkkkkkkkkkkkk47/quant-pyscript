"""Property tests for WeightProfileRegistry.

Feature: quant-ratings, Property 5: Unknown profile fallback

**Validates: Requirements 2.4, 6.3**
"""

from hypothesis import assume, given, settings
import hypothesis.strategies as st

from quant_ratings.config.weight_profile_registry import WeightProfileRegistry

# Known registered keys in the default registry (asset_class, sub_category)
KNOWN_KEYS = {("FX", "Major"), ("FX", "Volatile_Cross"), ("FX", "Emerging")}


@given(
    asset_class=st.text(min_size=1),
    sub_category=st.one_of(st.none(), st.text(min_size=1)),
)
def test_unknown_asset_class_falls_back_to_equal_weight(asset_class, sub_category):
    # Feature: quant-ratings, Property 5: Unknown profile fallback
    registry = WeightProfileRegistry()
    # Skip known registered keys
    assume((asset_class, sub_category) not in KNOWN_KEYS)

    profile = registry.get_profile(asset_class, sub_category)

    # Must not raise and must return the equal-weight fallback
    assert abs(profile.sentiment_pct - 33.3) < 0.01
    assert abs(profile.orderflow_pct - 33.3) < 0.01
    assert abs(profile.economic_pct - 33.4) < 0.01
