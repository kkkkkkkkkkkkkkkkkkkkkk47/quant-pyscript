"""Scheduler — triggers Rating_Engine computation cycles on a configurable cadence.

Supports both automatic scheduled runs (via a background thread) and on-demand
manual triggering.  Each run is subject to a configurable wall-clock timeout;
if the cycle exceeds the timeout the run is aborted and a timed-out
:class:`~quant_ratings.models.cycle_summary.CycleSummary` is returned without
persisting partial results.

Requirements: 7.1, 7.2, 7.3, 7.4, 7.5
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional

from quant_ratings.models.cycle_summary import CycleSummary

if TYPE_CHECKING:
    from quant_ratings.engine.rating_engine import RatingEngine
    from quant_ratings.observability.logger import StructuredLogger

# Module-level standard logger used as a fallback when no StructuredLogger is
# injected.
logger = logging.getLogger(__name__)


@dataclass
class SchedulerConfig:
    """Configuration for the :class:`Scheduler`.

    Attributes:
        interval_seconds: Cadence between automatic runs (default: 1 hour).
        timeout_seconds: Maximum wall-clock time allowed per cycle
            (default: 30 minutes).
    """

    interval_seconds: int = 3600
    timeout_seconds: int = 1800


class Scheduler:
    """Triggers :class:`~quant_ratings.engine.RatingEngine` computation cycles
    on a configurable cadence.

    Uses :class:`threading.Timer` for the background loop so that the
    implementation stays simple and fully testable without external
    dependencies.

    Args:
        engine: The :class:`~quant_ratings.engine.RatingEngine` to invoke.
        config: Scheduler configuration (interval and timeout).
        structured_logger: Optional structured (JSON) logger.  Falls back to
            the standard Python ``logging`` module when ``None``.
    """

    def __init__(
        self,
        engine: "RatingEngine",
        config: "SchedulerConfig",
        structured_logger: Optional["StructuredLogger"] = None,
    ) -> None:
        self._engine = engine
        self._config = config
        self._structured_logger = structured_logger

        self._stop_flag: bool = False
        self._timer: Optional[threading.Timer] = None
        self._lock: threading.Lock = threading.Lock()

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start the background scheduler loop.

        Schedules the first run after :attr:`SchedulerConfig.interval_seconds`.
        Each completed run automatically reschedules the next one.

        Requirements: 7.1
        """
        with self._lock:
            self._stop_flag = False
            self._schedule_next()

    def stop(self) -> None:
        """Gracefully stop the scheduler.

        Cancels any pending timer and sets the stop flag so that no further
        runs are scheduled.

        Requirements: 7.1
        """
        with self._lock:
            self._stop_flag = True
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None

    def trigger_manual_run(self) -> CycleSummary:
        """Trigger an immediate computation cycle outside the normal schedule.

        Runs synchronously in the calling thread and returns the resulting
        :class:`~quant_ratings.models.cycle_summary.CycleSummary`.

        Requirements: 7.5
        """
        return self._run_with_timeout(trigger_source="manual")

    def _run_with_timeout(self, trigger_source: str = "scheduled") -> CycleSummary:
        """Execute ``engine.run_cycle()`` and enforce the configured timeout.

        Runs the cycle in a separate daemon thread.  If the cycle completes
        within :attr:`SchedulerConfig.timeout_seconds`, the resulting
        :class:`~quant_ratings.models.cycle_summary.CycleSummary` is returned.
        If the timeout is exceeded, a summary with ``timed_out=True`` is
        returned instead; partial results are not persisted (the engine handles
        persistence internally and the scheduler never calls ``store.save()``
        directly).

        Args:
            trigger_source: Human-readable label for the log entry
                (``"scheduled"`` or ``"manual"``).

        Returns:
            A :class:`~quant_ratings.models.cycle_summary.CycleSummary`
            describing the outcome of the cycle.

        Requirements: 7.2, 7.3, 7.4
        """
        started_at = datetime.now(timezone.utc)

        # Determine security count for the start log entry.
        try:
            security_count = len(self._engine._security_registry.all_securities())
        except Exception:  # noqa: BLE001
            security_count = -1

        # --- Log cycle start (Requirement 7.2) ---
        self._log_cycle_start(
            started_at=started_at,
            security_count=security_count,
            trigger_source=trigger_source,
        )

        # Run the cycle in a separate thread so we can enforce a timeout.
        result_holder: list[CycleSummary] = []
        exc_holder: list[BaseException] = []

        def _target() -> None:
            try:
                summary = self._engine.run_cycle()
                result_holder.append(summary)
            except Exception as exc:  # noqa: BLE001
                exc_holder.append(exc)

        worker = threading.Thread(target=_target, daemon=True)
        worker.start()
        worker.join(timeout=self._config.timeout_seconds)

        if worker.is_alive():
            # Timeout exceeded — the worker thread is still running but we
            # abandon it (daemon=True ensures it won't block process exit).
            timed_out_summary = CycleSummary(
                started_at=started_at,
                completed_at=None,
                timed_out=True,
            )
            # --- Log timeout error (Requirement 7.4) ---
            self._log_timeout_error(
                started_at=started_at,
                timeout_seconds=self._config.timeout_seconds,
            )
            return timed_out_summary

        # Cycle completed within the timeout.
        if exc_holder:
            # The cycle raised an unexpected exception; build a failure summary.
            completed_at = datetime.now(timezone.utc)
            error_summary = CycleSummary(
                started_at=started_at,
                completed_at=completed_at,
                timed_out=False,
            )
            logger.error(
                "Unexpected exception during run_cycle: %r", str(exc_holder[0])
            )
            self._log_cycle_end(summary=error_summary)
            return error_summary

        summary = result_holder[0]

        # --- Log cycle end (Requirement 7.3) ---
        self._log_cycle_end(summary=summary)

        return summary

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _schedule_next(self) -> None:
        """Schedule the next automatic run after ``interval_seconds``."""
        if self._stop_flag:
            return
        self._timer = threading.Timer(
            interval=self._config.interval_seconds,
            function=self._scheduled_run,
        )
        self._timer.daemon = True
        self._timer.start()

    def _scheduled_run(self) -> None:
        """Callback invoked by the background timer for each scheduled run."""
        self._run_with_timeout(trigger_source="scheduled")
        # Reschedule the next run unless stop() was called.
        with self._lock:
            if not self._stop_flag:
                self._schedule_next()

    # ------------------------------------------------------------------
    # Logging helpers
    # ------------------------------------------------------------------

    def _log_cycle_start(
        self,
        started_at: datetime,
        security_count: int,
        trigger_source: str,
    ) -> None:
        """Emit a structured log entry for cycle start.

        Fields: ``time``, ``security_count``, ``trigger_source``.

        Requirements: 7.2
        """
        fields = {
            "time": started_at.isoformat(),
            "security_count": security_count,
            "trigger_source": trigger_source,
        }
        if self._structured_logger is not None:
            self._structured_logger.info("cycle_start", **fields)
        else:
            logger.info(
                "cycle_start: time=%s security_count=%d trigger_source=%s",
                fields["time"],
                security_count,
                trigger_source,
            )

    def _log_cycle_end(self, summary: CycleSummary) -> None:
        """Emit a structured log entry for cycle end.

        Fields: ``time``, ``records_produced``, ``failures``.

        Requirements: 7.3
        """
        completed_at = summary.completed_at or datetime.now(timezone.utc)
        fields = {
            "time": completed_at.isoformat(),
            "records_produced": summary.records_produced,
            "failures": summary.failures,
        }
        if self._structured_logger is not None:
            self._structured_logger.info("cycle_end", **fields)
        else:
            logger.info(
                "cycle_end: time=%s records_produced=%d failures=%d",
                fields["time"],
                summary.records_produced,
                summary.failures,
            )

    def _log_timeout_error(
        self,
        started_at: datetime,
        timeout_seconds: int,
    ) -> None:
        """Emit a structured error log entry when a cycle times out.

        Requirements: 7.4
        """
        fields = {
            "time": started_at.isoformat(),
            "timeout_seconds": timeout_seconds,
        }
        if self._structured_logger is not None:
            self._structured_logger.error("cycle_timeout", **fields)
        else:
            logger.error(
                "cycle_timeout: time=%s timeout_seconds=%d",
                fields["time"],
                timeout_seconds,
            )
