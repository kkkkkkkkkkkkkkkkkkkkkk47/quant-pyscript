"""RatingEngine — orchestrates a full Quant Ratings computation cycle.

Iterates all registered securities, computes three sub-scores for each,
aggregates them into a :class:`~quant_ratings.models.rating_record.RatingRecord`,
persists the record (with one retry on :class:`~quant_ratings.persistence.base.StorageError`),
and returns a :class:`~quant_ratings.models.cycle_summary.CycleSummary`.

After all securities are processed the engine:
- Emits a structured cycle-summary log entry.
- Evaluates the data-deficiency alert threshold (>20% → high-severity alert).
- Updates internal health-check state.

Requirements: 1.1, 6.4, 8.1, 8.3, 8.4, 9.5
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional

from quant_ratings.models.cycle_summary import CycleSummary
from quant_ratings.models.rating_record import RatingRecord
from quant_ratings.models.weight_profile import WeightProfileError
from quant_ratings.persistence.base import StorageError

if TYPE_CHECKING:
    from quant_ratings.aggregator.aggregator import Aggregator
    from quant_ratings.config.security_registry import SecurityRegistry
    from quant_ratings.config.weight_profile_registry import WeightProfileRegistry
    from quant_ratings.engine.data_manager import DataManager
    from quant_ratings.models.security import Security
    from quant_ratings.observability.alert_sink import AlertSink
    from quant_ratings.observability.logger import StructuredLogger
    from quant_ratings.persistence.base import RatingStore
    from quant_ratings.scorers.economic_scorer import EconomicScorer
    from quant_ratings.scorers.orderflow_scorer import OrderFlowScorer
    from quant_ratings.scorers.sentiment_scorer import SentimentScorer

# Module-level standard logger used as a fallback when no StructuredLogger is
# injected, and for internal diagnostic messages.
logger = logging.getLogger(__name__)

# Alert threshold: fraction of data-deficient records that triggers a
# high-severity alert (Requirement 11.2).
_DATA_DEFICIENCY_ALERT_THRESHOLD: float = 0.20


class RatingEngine:
    """Orchestrates a full Quant Ratings computation cycle.

    Args:
        security_registry: Registry of all supported securities.
        weight_registry: Registry of asset-class weight profiles.
        data_manager: Fetches and validates market data for each security.
        sentiment_scorer: Computes the Sentiment_Score sub-score.
        orderflow_scorer: Computes the OrderFlow_Score sub-score.
        economic_scorer: Computes the Economic_Score sub-score.
        aggregator: Combines the three sub-scores into a Composite_Score.
        store: Persistence backend for :class:`RatingRecord` objects.
        alert_sink: Channel for emitting high-severity operational alerts.
        logger: Structured (JSON) logger; falls back to the standard Python
            ``logging`` module when ``None``.
    """

    def __init__(
        self,
        security_registry: "SecurityRegistry",
        weight_registry: "WeightProfileRegistry",
        data_manager: "DataManager",
        sentiment_scorer: "SentimentScorer",
        orderflow_scorer: "OrderFlowScorer",
        economic_scorer: "EconomicScorer",
        aggregator: "Aggregator",
        store: "RatingStore",
        alert_sink: "AlertSink",
        structured_logger: Optional["StructuredLogger"] = None,
    ) -> None:
        self._security_registry = security_registry
        self._weight_registry = weight_registry
        self._data_manager = data_manager
        self._sentiment_scorer = sentiment_scorer
        self._orderflow_scorer = orderflow_scorer
        self._economic_scorer = economic_scorer
        self._aggregator = aggregator
        self._store = store
        self._alert_sink = alert_sink
        self._structured_logger = structured_logger

        # Health-check state (Requirement 11.4)
        self.last_successful_cycle_at: Optional[datetime] = None
        self.last_cycle_security_count: int = 0

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def run_cycle(self) -> CycleSummary:
        """Execute a full rating computation cycle.

        Iterates every security in the registry, calls :meth:`_rate_security`
        for each, collects results into a :class:`CycleSummary`, emits a
        cycle-summary log entry, evaluates alert thresholds, and updates
        health-check state.

        Returns:
            A :class:`~quant_ratings.models.cycle_summary.CycleSummary`
            describing the outcome of the cycle.
        """
        started_at = datetime.now(timezone.utc)
        securities = self._security_registry.all_securities()

        records_produced: int = 0
        failures: int = 0
        data_deficient_count: int = 0

        for security in securities:
            try:
                record = self._rate_security(security)
                records_produced += 1
                if record.data_deficient:
                    data_deficient_count += 1
            except Exception as exc:  # noqa: BLE001
                failures += 1
                logger.error(
                    "Failed to rate security: security_id=%r error=%r",
                    security.identifier,
                    str(exc),
                )

        completed_at = datetime.now(timezone.utc)
        securities_attempted = len(securities)

        summary = CycleSummary(
            started_at=started_at,
            completed_at=completed_at,
            securities_attempted=securities_attempted,
            records_produced=records_produced,
            failures=failures,
            data_deficient_count=data_deficient_count,
        )

        # --- Emit cycle summary log ---
        self._log_cycle_summary(summary)

        # --- Evaluate alert thresholds (Requirement 11.2) ---
        if securities_attempted > 0:
            deficiency_rate = data_deficient_count / securities_attempted
            if deficiency_rate > _DATA_DEFICIENCY_ALERT_THRESHOLD:
                try:
                    self._alert_sink.send_high_severity(
                        title="High data-deficiency rate detected",
                        body=(
                            f"Data-deficient records: {data_deficient_count} / "
                            f"{securities_attempted} "
                            f"({deficiency_rate:.1%}) exceed the "
                            f"{_DATA_DEFICIENCY_ALERT_THRESHOLD:.0%} threshold."
                        ),
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.error(
                        "Failed to send high-severity alert: error=%r", str(exc)
                    )

        # --- Update health-check state (Requirement 11.4) ---
        self.last_successful_cycle_at = completed_at
        self.last_cycle_security_count = securities_attempted

        return summary

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _rate_security(self, security: "Security") -> RatingRecord:
        """Compute and persist a single :class:`RatingRecord`.

        Steps:
        1. Fetch market data via :attr:`_data_manager`.
        2. Compute the three sub-scores.
        3. Load the weight profile for the security's asset class / sub-category.
        4. Aggregate sub-scores into a Composite_Score and Rating label.
        5. Build a :class:`RatingRecord` with a UUID ``record_id`` and UTC
           ``computed_at`` timestamp.
        6. Persist the record; retry once on :class:`StorageError`.

        Args:
            security: The security to rate.

        Returns:
            The persisted :class:`RatingRecord`.

        Raises:
            WeightProfileError: If the weight profile is invalid (propagated
                from the Aggregator).  The caller (:meth:`run_cycle`) catches
                this and increments the failure counter.
            StorageError: If both persistence attempts fail.
            Exception: Any other unrecoverable error.
        """
        # 1. Fetch market data
        bundle = self._data_manager.fetch(security)

        # 2. Compute sub-scores
        sentiment = self._sentiment_scorer.compute(
            security=security,
            positioning=bundle.retail_positioning,
            vix=bundle.vix,
            audjpy=bundle.audjpy,
        )
        orderflow = self._orderflow_scorer.compute(
            security=security,
            tick_volume=bundle.tick_volume,
            footprint=bundle.footprint,
            dom=bundle.dom,
        )
        economic = self._economic_scorer.compute(
            security=security,
            macro=bundle.macro,
        )

        # 3. Load weight profile — WeightProfileError propagates to run_cycle
        profile = self._weight_registry.get_profile(
            security.asset_class, security.sub_category
        )

        # 4. Aggregate
        agg_result = self._aggregator.aggregate(sentiment, orderflow, economic, profile)

        # 5. Build RatingRecord
        computed_at = datetime.now(timezone.utc)
        record = RatingRecord(
            record_id=str(uuid.uuid4()),
            security_id=security.identifier,
            asset_class=security.asset_class.value
            if hasattr(security.asset_class, "value")
            else str(security.asset_class),
            composite_score=agg_result.composite_score,
            rating=agg_result.rating,
            sentiment_score=sentiment.score,
            orderflow_score=orderflow.score,
            economic_score=economic.score,
            weight_profile=profile,
            data_deficient=agg_result.data_deficient,
            computed_at=computed_at,
        )

        # 6. Persist with one retry on StorageError (Requirement 8.4)
        try:
            self._store.save(record)
        except StorageError as first_exc:
            logger.warning(
                "StorageError on first save attempt, retrying: "
                "security_id=%r error=%r",
                security.identifier,
                str(first_exc),
            )
            try:
                self._store.save(record)
            except StorageError as second_exc:
                logger.error(
                    "StorageError on retry — record not persisted: "
                    "security_id=%r error=%r",
                    security.identifier,
                    str(second_exc),
                )
                raise

        return record

    def _log_cycle_summary(self, summary: CycleSummary) -> None:
        """Emit a structured log entry for the completed cycle.

        Uses the injected :class:`StructuredLogger` when available; falls back
        to the standard Python ``logging`` module otherwise.

        Args:
            summary: The :class:`CycleSummary` to log.
        """
        fields = {
            "started_at": summary.started_at.isoformat(),
            "completed_at": summary.completed_at.isoformat()
            if summary.completed_at
            else None,
            "securities_attempted": summary.securities_attempted,
            "records_produced": summary.records_produced,
            "failures": summary.failures,
            "data_deficient_count": summary.data_deficient_count,
        }

        if self._structured_logger is not None:
            self._structured_logger.info("cycle_complete", **fields)
        else:
            logger.info(
                "cycle_complete: securities_attempted=%d records_produced=%d "
                "failures=%d data_deficient_count=%d",
                summary.securities_attempted,
                summary.records_produced,
                summary.failures,
                summary.data_deficient_count,
            )
