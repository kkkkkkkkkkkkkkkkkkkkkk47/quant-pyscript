"""SecurityRegistry — configurable registry of supported securities.

Securities can be loaded from a YAML or JSON config file so new instruments
can be added without a code change (Requirement 6.2).  The registry also
supports runtime additions via :meth:`add`.
"""

from __future__ import annotations

import json
import logging
from typing import Optional

from quant_ratings.models.enums import AssetClass
from quant_ratings.models.security import Security

logger = logging.getLogger(__name__)


class SecurityRegistry:
    """Registry that maps security identifiers to :class:`Security` objects.

    Securities are stored in a dict keyed by ``security.identifier`` so
    look-ups are O(1).  The registry can be populated from a YAML or JSON
    config file via :meth:`load`, or programmatically via :meth:`add`.

    Config file format (list of dicts)::

        - identifier: "EUR/USD"
          asset_class: "FX"
          sub_category: "Major"
          primary_region: null
          denominating_currency: null

    Required keys per entry: ``identifier``, ``asset_class``.
    Optional keys: ``sub_category``, ``primary_region``, ``denominating_currency``.

    ``asset_class`` values must match the :class:`~quant_ratings.models.enums.AssetClass`
    enum (e.g. ``"FX"``, ``"Equity"``).
    """

    def __init__(self) -> None:
        # Key: identifier string → Security
        self._securities: dict[str, Security] = {}

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def load(self, config_path: str) -> None:
        """Load securities from a YAML or JSON config file.

        File format is detected by extension: ``.yaml`` / ``.yml`` → YAML,
        anything else → JSON.

        Each entry in the file must have at minimum the keys ``identifier``
        and ``asset_class``.  The ``asset_class`` value is converted to the
        :class:`~quant_ratings.models.enums.AssetClass` enum.

        Args:
            config_path: Filesystem path to the config file.

        Raises:
            ImportError: If a YAML file is requested but PyYAML is not
                installed.
            ValueError: If the file does not contain a list of security dicts,
                or if an ``asset_class`` value is not a valid
                :class:`AssetClass` member.
        """
        lower_path = config_path.lower()
        if lower_path.endswith(".yaml") or lower_path.endswith(".yml"):
            try:
                import yaml  # type: ignore[import]
            except ImportError as exc:
                raise ImportError(
                    "PyYAML is required to load YAML config files. "
                    "Install it with: pip install pyyaml"
                ) from exc
            with open(config_path, "r", encoding="utf-8") as fh:
                data = yaml.safe_load(fh)
        else:
            with open(config_path, "r", encoding="utf-8") as fh:
                data = json.load(fh)

        if not isinstance(data, list):
            raise ValueError(
                f"Expected a list of security dicts in {config_path!r}, "
                f"got {type(data).__name__}"
            )

        for item in data:
            try:
                asset_class = AssetClass(item["asset_class"])
            except (KeyError, ValueError) as exc:
                raise ValueError(
                    f"Invalid or missing 'asset_class' in security entry {item!r}: {exc}"
                ) from exc

            security = Security(
                identifier=item["identifier"],
                asset_class=asset_class,
                sub_category=item.get("sub_category"),
                primary_region=item.get("primary_region"),
                denominating_currency=item.get("denominating_currency"),
            )
            self.add(security)

    def all_securities(self) -> list[Security]:
        """Return all registered securities.

        Returns:
            A list of all :class:`~quant_ratings.models.security.Security`
            objects currently in the registry.
        """
        return list(self._securities.values())

    def get(self, identifier: str) -> Optional[Security]:
        """Look up a security by its identifier.

        Args:
            identifier: The security identifier to look up (e.g. ``"EUR/USD"``).

        Returns:
            The :class:`~quant_ratings.models.security.Security` if found,
            or ``None`` for unknown identifiers.
        """
        return self._securities.get(identifier)

    def add(self, security: Security) -> None:
        """Register a new security at runtime.

        If a security with the same identifier already exists it will be
        overwritten.

        Args:
            security: The :class:`~quant_ratings.models.security.Security`
                to register.
        """
        self._securities[security.identifier] = security
