"""SQLAlchemy ORM model for the Quant Ratings persistence layer.

Defines the ``RatingRecordORM`` mapped class that backs the ``rating_records``
table.  Uses SQLAlchemy 2.x declarative style with ``DeclarativeBase``.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Shared declarative base for all ORM models in this package."""


class RatingRecordORM(Base):
    """ORM model for a single persisted :class:`~quant_ratings.models.rating_record.RatingRecord`.

    Maps to the ``rating_records`` table.  All columns are non-nullable except
    ``weight_profile_sub_category``, which is ``None`` for asset classes that
    do not use sub-categories.
    """

    __tablename__ = "rating_records"

    # Primary key
    record_id: Mapped[str] = mapped_column(String, primary_key=True)

    # Security identification
    security_id: Mapped[str] = mapped_column(String, nullable=False)
    asset_class: Mapped[str] = mapped_column(String, nullable=False)

    # Scores
    composite_score: Mapped[float] = mapped_column(Float, nullable=False)
    rating: Mapped[str] = mapped_column(String, nullable=False)
    sentiment_score: Mapped[float] = mapped_column(Float, nullable=False)
    orderflow_score: Mapped[float] = mapped_column(Float, nullable=False)
    economic_score: Mapped[float] = mapped_column(Float, nullable=False)

    # Weight profile (flattened)
    weight_profile_sentiment_pct: Mapped[float] = mapped_column(Float, nullable=False)
    weight_profile_orderflow_pct: Mapped[float] = mapped_column(Float, nullable=False)
    weight_profile_economic_pct: Mapped[float] = mapped_column(Float, nullable=False)
    weight_profile_asset_class: Mapped[str] = mapped_column(String, nullable=False)
    weight_profile_sub_category: Mapped[str | None] = mapped_column(String, nullable=True)

    # Metadata
    data_deficient: Mapped[bool] = mapped_column(Boolean, nullable=False)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"RatingRecordORM(record_id={self.record_id!r}, "
            f"security_id={self.security_id!r}, "
            f"computed_at={self.computed_at!r})"
        )
