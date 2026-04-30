"""DataManager — coordinates data fetching, validation, and staleness checks.

Assembles a :class:`~quant_ratings.models.market_data.MarketDataBundle` for a
given security by querying all registered :class:`DataProviderAdapter` instances,
validating each field against its defined valid range, and enforcing a staleness
threshold (default 4 hours).  Fields that fail validation or are stale are set
to ``None`` so that downstream scorers apply their neutral fallback.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from typing import Any, List, Optional, Tuple

from quant_ratings.models.market_data import (
    DOMData,
    FootprintData,
    MacroData,
    MarketDataBundle,
    RetailPositioning,
    TickVolumeData,
)
from quant_ratings.models.security import Security
from quant_ratings.providers.base import DataProviderAdapter

logger = logging.getLogger(__name__)

# Valid ranges (inclusive) for scalar fields.
# Format: (min_value, max_value)
_VIX_RANGE: Tuple[float, float] = (0.0, 200.0)
_AUDJPY_RANGE: Tuple[float, float] = (0.0, 500.0)
_PCT_RANGE: Tuple[float, float] = (0.0, 1.0)
_NON_NEGATIVE_RANGE: Tuple[float, float] = (0.0, float("inf"))
_POSITIVE_RANGE: Tuple[float, float] = (1e-9, float("inf"))  # strictly > 0


class DataManager:
    """Coordinates data fetching, validation, and staleness enforcement.

    On each call to :meth:`fetch`, the manager queries every registered
    :class:`~quant_ratings.providers.base.DataProviderAdapter` and uses the
    first non-``None`` result for each data type.  It then:

    1. Checks each data object's ``timestamp`` against the staleness threshold;
       stale objects are replaced with ``None``.
    2. Validates each numeric field against its defined valid range; out-of-range
       values are replaced with ``None`` and a structured error is logged.

    Args:
        providers: List of :class:`DataProviderAdapter` instances to query.
        staleness_threshold_seconds: Maximum age (in seconds) of a data object
            before it is considered stale.  Defaults to 14 400 (4 hours).
    """

    def __init__(
        self,
        providers: List[DataProviderAdapter],
        staleness_threshold_seconds: int = 14400,
    ) -> None:
        self._providers = providers
        self._staleness_threshold = timedelta(seconds=staleness_threshold_seconds)

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def fetch(self, security: Security) -> MarketDataBundle:
        """Fetch and validate all data required to score *security*.

        Returns a :class:`~quant_ratings.models.market_data.MarketDataBundle`
        where unavailable, stale, or invalid fields are ``None``.
        """
        fetched_at = datetime.now(timezone.utc)

        # --- Collect raw data from providers (first non-None wins) ---
        retail_positioning: Optional[RetailPositioning] = None
        vix: Optional[float] = None
        audjpy: Optional[float] = None
        tick_volume: Optional[TickVolumeData] = None
        footprint: Optional[FootprintData] = None
        dom: Optional[DOMData] = None
        macro: Optional[MacroData] = None

        for provider in self._providers:
            if retail_positioning is None:
                retail_positioning = provider.fetch_retail_positioning(security)
            if vix is None:
                vix = provider.fetch_vix()
            if audjpy is None:
                audjpy = provider.fetch_audjpy()
            if tick_volume is None:
                tick_volume = provider.fetch_tick_volume(security)
            if footprint is None:
                footprint = provider.fetch_footprint(security)
            if dom is None:
                dom = provider.fetch_dom(security)
            if macro is None:
                macro = provider.fetch_macro(security)

        # --- Staleness checks ---
        retail_positioning = self._check_staleness(
            "retail_positioning", retail_positioning, fetched_at
        )
        tick_volume = self._check_staleness("tick_volume", tick_volume, fetched_at)
        footprint = self._check_staleness("footprint", footprint, fetched_at)
        dom = self._check_staleness("dom", dom, fetched_at)
        macro = self._check_staleness("macro", macro, fetched_at)

        # --- Field-level validation ---
        if not self._validate_field("vix", vix, _VIX_RANGE):
            vix = None
        if not self._validate_field("audjpy", audjpy, _AUDJPY_RANGE):
            audjpy = None

        if retail_positioning is not None:
            if not self._validate_field(
                "retail_positioning.long_pct", retail_positioning.long_pct, _PCT_RANGE
            ) or not self._validate_field(
                "retail_positioning.short_pct", retail_positioning.short_pct, _PCT_RANGE
            ):
                retail_positioning = None

        if tick_volume is not None:
            if not self._validate_field(
                "tick_volume.current", tick_volume.current, _NON_NEGATIVE_RANGE
            ) or not self._validate_field(
                "tick_volume.avg_20_period", tick_volume.avg_20_period, _POSITIVE_RANGE
            ):
                tick_volume = None

        return MarketDataBundle(
            security=security,
            fetched_at=fetched_at,
            retail_positioning=retail_positioning,
            vix=vix,
            audjpy=audjpy,
            tick_volume=tick_volume,
            footprint=footprint,
            dom=dom,
            macro=macro,
        )

    def _validate_field(
        self, field_name: str, value: Any, valid_range: Tuple[float, float]
    ) -> bool:
        """Return ``True`` if *value* is within *valid_range* (inclusive).

        ``None`` values are always considered valid (they represent unavailable
        data and are handled by the neutral fallback in each scorer).

        Logs a structured validation error and returns ``False`` when *value*
        is outside the range.

        Args:
            field_name: Human-readable name of the field (used in log messages).
            value: The value to validate.
            valid_range: A ``(min_value, max_value)`` tuple (inclusive).

        Returns:
            ``True`` if the value is valid or ``None``; ``False`` otherwise.
        """
        if value is None:
            return True
        min_val, max_val = valid_range
        if value < min_val or value > max_val:
            logger.error(
                "Validation error: field=%r value=%r is outside valid range [%s, %s]; "
                "replacing with None.",
                field_name,
                value,
                min_val,
                max_val,
            )
            return False
        return True

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _check_staleness(
        self, field_name: str, obj: Any, fetched_at: datetime
    ) -> Any:
        """Return *obj* if it is fresh, or ``None`` if it is stale.

        An object is considered stale when its ``timestamp`` attribute is
        older than ``fetched_at - staleness_threshold``.

        Args:
            field_name: Human-readable name of the field (used in log messages).
            obj: The data object to check.  Must have a ``timestamp`` attribute
                if not ``None``.
            fetched_at: The UTC datetime at which the bundle is being assembled.

        Returns:
            *obj* if fresh or ``None``; ``None`` if stale.
        """
        if obj is None:
            return None
        timestamp: datetime = obj.timestamp
        # Ensure both datetimes are timezone-aware for comparison.
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        age = fetched_at - timestamp
        if age > self._staleness_threshold:
            logger.warning(
                "Stale data: field=%r timestamp=%s age=%s exceeds threshold=%s; "
                "replacing with None.",
                field_name,
                timestamp.isoformat(),
                age,
                self._staleness_threshold,
            )
            return None
        return obj
