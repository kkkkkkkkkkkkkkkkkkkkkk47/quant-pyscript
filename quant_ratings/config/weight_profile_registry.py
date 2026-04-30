"""WeightProfileRegistry — stores and resolves Weight_Profiles.

Falls back to an equal-weight profile (Sentiment 33.3 %, OrderFlow 33.3 %,
Economic 33.4 %) when no profile matches the requested asset class /
sub-category combination, and logs a warning in that case.
"""

from __future__ import annotations

import json
import logging
from typing import Optional, Union

from quant_ratings.models.enums import AssetClass
from quant_ratings.models.weight_profile import WeightProfile

logger = logging.getLogger(__name__)

# Equal-weight fallback used when no profile is registered for a given key.
_FALLBACK_PROFILE = WeightProfile(
    asset_class="fallback",
    sub_category=None,
    sentiment_pct=33.3,
    orderflow_pct=33.3,
    economic_pct=33.4,
)

# Default FX profiles seeded in every registry instance.
_DEFAULT_FX_PROFILES: list[WeightProfile] = [
    WeightProfile(
        asset_class="FX",
        sub_category="Major",
        sentiment_pct=20.0,
        orderflow_pct=30.0,
        economic_pct=50.0,
    ),
    WeightProfile(
        asset_class="FX",
        sub_category="Volatile_Cross",
        sentiment_pct=40.0,
        orderflow_pct=40.0,
        economic_pct=20.0,
    ),
    WeightProfile(
        asset_class="FX",
        sub_category="Emerging",
        sentiment_pct=10.0,
        orderflow_pct=10.0,
        economic_pct=80.0,
    ),
]


class WeightProfileRegistry:
    """Registry that maps (asset_class, sub_category) pairs to WeightProfiles.

    On construction the registry is pre-seeded with the three default FX
    profiles (Major, Volatile_Cross, Emerging).  Additional profiles can be
    registered at runtime via :meth:`register` or loaded in bulk from a YAML
    or JSON file via :meth:`load_from_file`.

    When :meth:`get_profile` is called with a key that has no registered
    profile, the equal-weight fallback profile is returned and a ``WARNING``
    log message is emitted.
    """

    def __init__(self) -> None:
        # Key: (asset_class_str, sub_category_str_or_None)
        self._profiles: dict[tuple[str, Optional[str]], WeightProfile] = {}
        for profile in _DEFAULT_FX_PROFILES:
            self.register(profile)

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def register(self, profile: WeightProfile) -> None:
        """Register or overwrite a WeightProfile.

        Args:
            profile: The :class:`~quant_ratings.models.weight_profile.WeightProfile`
                to store.  The key is derived from ``profile.asset_class`` and
                ``profile.sub_category``.
        """
        key = self._make_key(profile.asset_class, profile.sub_category)
        self._profiles[key] = profile

    def get_profile(
        self,
        asset_class: Union[AssetClass, str],
        sub_category: Optional[str] = None,
    ) -> WeightProfile:
        """Return the WeightProfile for the given asset class / sub-category.

        Accepts both :class:`~quant_ratings.models.enums.AssetClass` enum
        values and plain strings for *asset_class*.

        Falls back to the equal-weight profile and logs a ``WARNING`` if no
        matching profile is found.

        Args:
            asset_class: The asset class to look up (e.g. ``AssetClass.FX``
                or the string ``"FX"``).
            sub_category: Optional sub-category string (e.g. ``"Major"``).

        Returns:
            The registered :class:`WeightProfile`, or the equal-weight
            fallback profile when no match exists.
        """
        # Normalise enum → string so the dict key is always a plain string.
        asset_class_str = (
            asset_class.value
            if isinstance(asset_class, AssetClass)
            else str(asset_class)
        )
        key = self._make_key(asset_class_str, sub_category)
        profile = self._profiles.get(key)
        if profile is None:
            logger.warning(
                "No WeightProfile registered for asset_class=%r sub_category=%r; "
                "falling back to equal-weight profile.",
                asset_class_str,
                sub_category,
            )
            return _FALLBACK_PROFILE
        return profile

    def load_from_file(self, path: str) -> None:
        """Load WeightProfiles from a YAML or JSON file.

        The file must contain a list of profile dicts, each with the keys:
        ``asset_class``, ``sub_category``, ``sentiment_pct``,
        ``orderflow_pct``, ``economic_pct``.

        File format is detected by extension: ``.yaml`` / ``.yml`` → YAML,
        anything else → JSON.

        Args:
            path: Filesystem path to the config file.

        Raises:
            ImportError: If a YAML file is requested but PyYAML is not
                installed.
            ValueError: If the file does not contain a list of profile dicts.
        """
        lower_path = path.lower()
        if lower_path.endswith(".yaml") or lower_path.endswith(".yml"):
            try:
                import yaml  # type: ignore[import]
            except ImportError as exc:
                raise ImportError(
                    "PyYAML is required to load YAML config files. "
                    "Install it with: pip install pyyaml"
                ) from exc
            with open(path, "r", encoding="utf-8") as fh:
                data = yaml.safe_load(fh)
        else:
            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)

        if not isinstance(data, list):
            raise ValueError(
                f"Expected a list of profile dicts in {path!r}, got {type(data).__name__}"
            )

        for item in data:
            profile = WeightProfile(
                asset_class=item["asset_class"],
                sub_category=item.get("sub_category"),
                sentiment_pct=float(item["sentiment_pct"]),
                orderflow_pct=float(item["orderflow_pct"]),
                economic_pct=float(item["economic_pct"]),
            )
            self.register(profile)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _make_key(
        asset_class: str, sub_category: Optional[str]
    ) -> tuple[str, Optional[str]]:
        return (asset_class, sub_category)
