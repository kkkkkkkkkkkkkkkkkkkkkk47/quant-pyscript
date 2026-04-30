"""Unit tests for core data models.

Covers:
- WeightProfile.validate() — Requirements 1.4
- DOMData.has_institutional_bids_at_or_below_price() — Requirements 4.1
- RatingRecord field completeness — Requirements 8.2
"""

import uuid
from datetime import datetime, timezone

import pytest

from quant_ratings.models import (
    DOMData,
    RatingRecord,
    WeightProfile,
    WeightProfileError,
)


# ---------------------------------------------------------------------------
# WeightProfile.validate()
# ---------------------------------------------------------------------------


class TestWeightProfileValidate:
    """Tests for WeightProfile.validate()."""

    def test_valid_profile_does_not_raise(self):
        """A profile whose weights sum to exactly 100 passes without raising."""
        profile = WeightProfile(
            asset_class="FX",
            sub_category="Major",
            sentiment_pct=20.0,
            orderflow_pct=30.0,
            economic_pct=50.0,
        )
        # Should not raise
        profile.validate()

    def test_invalid_profile_raises_weight_profile_error(self):
        """A profile whose weights do not sum to 100 raises WeightProfileError."""
        profile = WeightProfile(
            asset_class="FX",
            sub_category="Major",
            sentiment_pct=20.0,
            orderflow_pct=30.0,
            economic_pct=40.0,  # sums to 90, not 100
        )
        with pytest.raises(WeightProfileError):
            profile.validate()

    def test_weights_summing_to_99_999_within_tolerance_passes(self):
        """Weights summing to ~99.9995 are within the 0.001 tolerance and should pass."""
        profile = WeightProfile(
            asset_class="FX",
            sub_category=None,
            sentiment_pct=33.3330,
            orderflow_pct=33.3330,
            economic_pct=33.3335,  # total = 99.9995, abs diff = 0.0005 < 0.001
        )
        # abs(99.9995 - 100.0) = 0.0005, which is NOT > 0.001, so should pass
        profile.validate()

    def test_weights_summing_to_100_002_outside_tolerance_raises(self):
        """Weights summing to 100.002 exceed the 0.001 tolerance and should raise."""
        profile = WeightProfile(
            asset_class="FX",
            sub_category=None,
            sentiment_pct=33.334,
            orderflow_pct=33.334,
            economic_pct=33.334,  # total = 100.002, outside tolerance
        )
        with pytest.raises(WeightProfileError):
            profile.validate()


# ---------------------------------------------------------------------------
# DOMData.has_institutional_bids_at_or_below_price()
# ---------------------------------------------------------------------------


class TestDOMDataHasInstitutionalBids:
    """Tests for DOMData.has_institutional_bids_at_or_below_price()."""

    def _make_dom(self, bid_levels, current_price=100.0):
        return DOMData(
            bid_levels=bid_levels,
            ask_levels=[],
            current_price=current_price,
            timestamp=datetime.now(timezone.utc),
        )

    def test_returns_true_when_bid_at_or_below_price_with_sufficient_volume(self):
        """Returns True when a bid level has price <= current_price AND volume >= 100.0."""
        dom = self._make_dom(
            bid_levels=[(99.5, 150.0)],  # price below current, volume above threshold
            current_price=100.0,
        )
        assert dom.has_institutional_bids_at_or_below_price() is True

    def test_returns_true_when_bid_exactly_at_current_price(self):
        """Returns True when a bid level is exactly at current_price with sufficient volume."""
        dom = self._make_dom(
            bid_levels=[(100.0, 100.0)],  # price == current, volume == threshold
            current_price=100.0,
        )
        assert dom.has_institutional_bids_at_or_below_price() is True

    def test_returns_false_when_all_bids_above_current_price(self):
        """Returns False when all bid levels have price > current_price."""
        dom = self._make_dom(
            bid_levels=[(101.0, 200.0), (102.0, 500.0)],
            current_price=100.0,
        )
        assert dom.has_institutional_bids_at_or_below_price() is False

    def test_returns_false_when_bids_at_or_below_price_have_insufficient_volume(self):
        """Returns False when bid levels at/below price have volume < 100.0."""
        dom = self._make_dom(
            bid_levels=[(99.0, 50.0)],  # price below current, but volume below threshold
            current_price=100.0,
        )
        assert dom.has_institutional_bids_at_or_below_price() is False

    def test_returns_false_when_bid_levels_is_empty(self):
        """Returns False when bid_levels is empty."""
        dom = self._make_dom(bid_levels=[], current_price=100.0)
        assert dom.has_institutional_bids_at_or_below_price() is False


# ---------------------------------------------------------------------------
# RatingRecord construction
# ---------------------------------------------------------------------------


class TestRatingRecordConstruction:
    """Tests for RatingRecord field completeness (Requirement 8.2)."""

    def _make_weight_profile(self):
        return WeightProfile(
            asset_class="FX",
            sub_category="Major",
            sentiment_pct=20.0,
            orderflow_pct=30.0,
            economic_pct=50.0,
        )

    def test_all_fields_are_non_none_after_construction(self):
        """All required RatingRecord fields are non-None after construction with valid values."""
        record = RatingRecord(
            record_id=str(uuid.uuid4()),
            security_id="EUR/USD",
            asset_class="FX",
            composite_score=3.85,
            rating="Buy",
            sentiment_score=3.2,
            orderflow_score=4.1,
            economic_score=3.9,
            weight_profile=self._make_weight_profile(),
            data_deficient=False,
            computed_at=datetime.now(timezone.utc),
        )

        assert record.record_id is not None
        assert record.security_id is not None
        assert record.asset_class is not None
        assert record.composite_score is not None
        assert record.rating is not None
        assert record.sentiment_score is not None
        assert record.orderflow_score is not None
        assert record.economic_score is not None
        assert record.weight_profile is not None
        assert record.data_deficient is not None
        assert record.computed_at is not None
