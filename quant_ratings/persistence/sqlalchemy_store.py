"""SQLAlchemy-backed implementation of :class:`~quant_ratings.persistence.base.RatingStore`.

Provides ``SQLAlchemyRatingStore``, which persists
:class:`~quant_ratings.models.rating_record.RatingRecord` instances to any
relational database supported by SQLAlchemy (PostgreSQL in production, SQLite
for tests).

Records are **immutable** — ``save()`` performs an INSERT only and never
updates an existing row.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from quant_ratings.models.rating_record import RatingRecord
from quant_ratings.models.weight_profile import WeightProfile
from quant_ratings.persistence.base import RatingStore, StorageError
from quant_ratings.persistence.orm import Base, RatingRecordORM

if TYPE_CHECKING:
    from sqlalchemy.engine import Engine


class SQLAlchemyRatingStore(RatingStore):
    """Relational-database-backed :class:`RatingStore` using SQLAlchemy 2.x.

    Args:
        engine: A SQLAlchemy :class:`~sqlalchemy.engine.Engine` instance.
            The caller is responsible for creating and configuring the engine.
            On construction, all required tables are created automatically via
            ``Base.metadata.create_all()``.
    """

    def __init__(self, engine: "Engine") -> None:
        self._engine = engine
        Base.metadata.create_all(engine)

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def save(self, record: RatingRecord) -> None:
        """Persist *record* as a new row in ``rating_records``.

        This is an INSERT-only operation; existing records are never modified.

        Args:
            record: The :class:`RatingRecord` to persist.

        Raises:
            StorageError: If the INSERT fails for any reason (e.g. duplicate
                primary key, database unavailable).
        """
        orm_obj = self._to_orm(record)
        try:
            with Session(self._engine) as session:
                session.add(orm_obj)
                session.commit()
        except SQLAlchemyError as exc:
            raise StorageError(f"Failed to save record {record.record_id}: {exc}") from exc

    def get_latest(self, security_id: str) -> Optional[RatingRecord]:
        """Return the most recent :class:`RatingRecord` for *security_id*.

        "Most recent" is determined by the ``computed_at`` column (descending).

        Returns:
            The latest :class:`RatingRecord`, or ``None`` if no records exist
            for *security_id*.
        """
        stmt = (
            select(RatingRecordORM)
            .where(RatingRecordORM.security_id == security_id)
            .order_by(RatingRecordORM.computed_at.desc())
            .limit(1)
        )
        try:
            with Session(self._engine) as session:
                row = session.execute(stmt).scalar_one_or_none()
                return self._to_record(row) if row is not None else None
        except SQLAlchemyError as exc:
            raise StorageError(
                f"Failed to query latest record for {security_id!r}: {exc}"
            ) from exc

    def get_history(
        self,
        security_id: str,
        from_utc: datetime,
        to_utc: datetime,
    ) -> list[RatingRecord]:
        """Return all :class:`RatingRecord` objects for *security_id* in ``[from_utc, to_utc)``.

        The interval is **half-open**: records with ``computed_at == from_utc``
        are included; records with ``computed_at == to_utc`` are excluded.

        Returns:
            A list of :class:`RatingRecord` instances ordered by ``computed_at``
            ascending.  Returns an empty list if no records match.
        """
        stmt = (
            select(RatingRecordORM)
            .where(
                RatingRecordORM.security_id == security_id,
                RatingRecordORM.computed_at >= from_utc,
                RatingRecordORM.computed_at < to_utc,
            )
            .order_by(RatingRecordORM.computed_at.asc())
        )
        try:
            with Session(self._engine) as session:
                rows = session.execute(stmt).scalars().all()
                return [self._to_record(row) for row in rows]
        except SQLAlchemyError as exc:
            raise StorageError(
                f"Failed to query history for {security_id!r}: {exc}"
            ) from exc

    def get_latest_by_asset_class(self, asset_class: str) -> list[RatingRecord]:
        """Return the most recent :class:`RatingRecord` for every security in *asset_class*.

        For each distinct ``security_id`` in the given asset class, only the
        record with the greatest ``computed_at`` is returned.

        Returns:
            A list of :class:`RatingRecord` instances (one per security).
            Returns an empty list if no records exist for *asset_class*.
        """
        # Subquery: for each security_id in the asset class, find the max computed_at
        from sqlalchemy import func

        subq = (
            select(
                RatingRecordORM.security_id,
                func.max(RatingRecordORM.computed_at).label("max_computed_at"),
            )
            .where(RatingRecordORM.asset_class == asset_class)
            .group_by(RatingRecordORM.security_id)
            .subquery()
        )

        stmt = select(RatingRecordORM).join(
            subq,
            (RatingRecordORM.security_id == subq.c.security_id)
            & (RatingRecordORM.computed_at == subq.c.max_computed_at),
        )

        try:
            with Session(self._engine) as session:
                rows = session.execute(stmt).scalars().all()
                return [self._to_record(row) for row in rows]
        except SQLAlchemyError as exc:
            raise StorageError(
                f"Failed to query latest records for asset class {asset_class!r}: {exc}"
            ) from exc

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _to_orm(record: RatingRecord) -> RatingRecordORM:
        """Convert a :class:`RatingRecord` dataclass to a :class:`RatingRecordORM` instance."""
        wp = record.weight_profile
        return RatingRecordORM(
            record_id=record.record_id,
            security_id=record.security_id,
            asset_class=record.asset_class,
            composite_score=record.composite_score,
            rating=record.rating,
            sentiment_score=record.sentiment_score,
            orderflow_score=record.orderflow_score,
            economic_score=record.economic_score,
            weight_profile_sentiment_pct=wp.sentiment_pct,
            weight_profile_orderflow_pct=wp.orderflow_pct,
            weight_profile_economic_pct=wp.economic_pct,
            weight_profile_asset_class=wp.asset_class,
            weight_profile_sub_category=wp.sub_category,
            data_deficient=record.data_deficient,
            computed_at=record.computed_at,
        )

    @staticmethod
    def _to_record(orm: RatingRecordORM) -> RatingRecord:
        """Convert a :class:`RatingRecordORM` instance to a :class:`RatingRecord` dataclass.

        SQLite stores datetimes as naive values.  We re-attach UTC timezone
        info on read so that callers always receive timezone-aware datetimes.
        """
        from datetime import timezone as _tz

        computed_at = orm.computed_at
        if computed_at is not None and computed_at.tzinfo is None:
            computed_at = computed_at.replace(tzinfo=_tz.utc)

        wp = WeightProfile(
            asset_class=orm.weight_profile_asset_class,
            sub_category=orm.weight_profile_sub_category,
            sentiment_pct=orm.weight_profile_sentiment_pct,
            orderflow_pct=orm.weight_profile_orderflow_pct,
            economic_pct=orm.weight_profile_economic_pct,
        )
        return RatingRecord(
            record_id=orm.record_id,
            security_id=orm.security_id,
            asset_class=orm.asset_class,
            composite_score=orm.composite_score,
            rating=orm.rating,
            sentiment_score=orm.sentiment_score,
            orderflow_score=orm.orderflow_score,
            economic_score=orm.economic_score,
            weight_profile=wp,
            data_deficient=orm.data_deficient,
            computed_at=computed_at,
        )
