"""Persistence base abstractions for the Quant Ratings engine.

Defines the :class:`RatingStore` ABC and :class:`StorageError` exception.
The concrete implementation (SQLAlchemy-backed) will be added in task 13.1.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from quant_ratings.models.enums import AssetClass
    from quant_ratings.models.rating_record import RatingRecord


class StorageError(Exception):
    """Raised by :class:`RatingStore` implementations when a persistence
    operation fails (e.g. database unavailable, constraint violation)."""


class RatingStore(ABC):
    """Abstract base class for Rating_Record persistence backends.

    Implementations must be thread-safe and must never overwrite an existing
    record (Requirement 8.3).
    """

    @abstractmethod
    def save(self, record: "RatingRecord") -> None:
        """Persist *record*.

        Args:
            record: The :class:`~quant_ratings.models.rating_record.RatingRecord`
                to store.

        Raises:
            StorageError: If the record cannot be persisted.
        """

    @abstractmethod
    def get_latest(self, security_id: str) -> Optional["RatingRecord"]:
        """Return the most recent :class:`RatingRecord` for *security_id*,
        or ``None`` if no records exist."""

    @abstractmethod
    def get_history(
        self,
        security_id: str,
        from_utc: datetime,
        to_utc: datetime,
    ) -> list["RatingRecord"]:
        """Return all :class:`RatingRecord` objects for *security_id* within
        the half-open interval ``[from_utc, to_utc)``."""

    @abstractmethod
    def get_latest_by_asset_class(
        self, asset_class: "AssetClass"
    ) -> list["RatingRecord"]:
        """Return the most recent :class:`RatingRecord` for every security
        belonging to *asset_class*."""
