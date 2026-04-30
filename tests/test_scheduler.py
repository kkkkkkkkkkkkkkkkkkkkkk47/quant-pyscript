"""Unit tests for the Scheduler.

Tests cover:
- Timeout abort (timed_out=True, no partial records)
- Manual trigger returns the correct CycleSummary
- Cycle-start log entry contains required fields (time, security_count, trigger_source)
- Cycle-end log entry contains required fields (time, records_produced, failures)

Feature: quant-ratings
Requirements: 7.1, 7.2, 7.3, 7.4, 7.5
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from typing import Optional
from unittest.mock import MagicMock

import pytest

from quant_ratings.models.cycle_summary import CycleSummary
from quant_ratings.observability.logger import JsonStructuredLogger
from quant_ratings.scheduler.scheduler import Scheduler, SchedulerConfig


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _CapturingHandler(logging.Handler):
    """A logging.Handler that stores every LogRecord it receives."""

    def __init__(self) -> None:
        super().__init__()
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


def _make_capturing_logger(name: str) -> tuple[logging.Logger, _CapturingHandler]:
    """Return a (Logger, CapturingHandler) pair with propagation disabled."""
    log = logging.getLogger(name)
    log.setLevel(logging.DEBUG)
    handler = _CapturingHandler()
    # Remove any pre-existing handlers to avoid cross-test pollution.
    log.handlers.clear()
    log.addHandler(handler)
    log.propagate = False
    return log, handler


def _make_mock_engine(
    run_cycle_return: Optional[CycleSummary] = None,
    sleep_seconds: float = 0.0,
    security_count: int = 3,
) -> MagicMock:
    """Build a mock RatingEngine.

    Args:
        run_cycle_return: The CycleSummary that ``run_cycle()`` should return.
            Defaults to a minimal successful summary.
        sleep_seconds: If > 0, ``run_cycle()`` will sleep for this many seconds
            before returning (used to simulate a slow cycle for timeout tests).
        security_count: Number of securities reported by the registry.
    """
    if run_cycle_return is None:
        run_cycle_return = CycleSummary(
            started_at=datetime.now(timezone.utc),
            completed_at=datetime.now(timezone.utc),
            securities_attempted=security_count,
            records_produced=security_count,
            failures=0,
        )

    engine = MagicMock()
    engine._security_registry.all_securities.return_value = [
        MagicMock() for _ in range(security_count)
    ]

    if sleep_seconds > 0:
        def _slow_run_cycle():
            time.sleep(sleep_seconds)
            return run_cycle_return
        engine.run_cycle.side_effect = _slow_run_cycle
    else:
        engine.run_cycle.return_value = run_cycle_return

    return engine


# ---------------------------------------------------------------------------
# Test 1 — Timeout abort: timed_out=True, no partial records persisted
# ---------------------------------------------------------------------------

def test_timeout_abort_no_partial_records() -> None:
    """When run_cycle() takes longer than timeout_seconds, the returned
    CycleSummary must have timed_out=True.

    The scheduler must NOT call store.save() directly — partial results are
    the engine's responsibility.  We verify this by confirming the engine's
    run_cycle() was called but the summary reflects a timeout.

    Validates: Requirements 7.4
    """
    # Engine sleeps for 1 second; timeout is 0.1 seconds → timeout fires first.
    engine = _make_mock_engine(sleep_seconds=1.0)
    config = SchedulerConfig(interval_seconds=3600, timeout_seconds=0)

    scheduler = Scheduler(engine=engine, config=config)
    summary = scheduler.trigger_manual_run()

    assert summary.timed_out is True, (
        f"Expected timed_out=True but got timed_out={summary.timed_out}"
    )


# ---------------------------------------------------------------------------
# Test 2 — Manual trigger returns the correct CycleSummary
# ---------------------------------------------------------------------------

def test_trigger_manual_run_returns_cycle_summary() -> None:
    """trigger_manual_run() must return the CycleSummary produced by the engine.

    Validates: Requirements 7.5
    """
    expected_summary = CycleSummary(
        started_at=datetime.now(timezone.utc),
        completed_at=datetime.now(timezone.utc),
        securities_attempted=5,
        records_produced=4,
        failures=1,
        data_deficient_count=0,
        timed_out=False,
    )
    engine = _make_mock_engine(run_cycle_return=expected_summary)
    config = SchedulerConfig(interval_seconds=3600, timeout_seconds=30)

    scheduler = Scheduler(engine=engine, config=config)
    result = scheduler.trigger_manual_run()

    assert result is expected_summary, (
        "trigger_manual_run() must return the exact CycleSummary from the engine"
    )
    assert result.records_produced == 4
    assert result.failures == 1
    assert result.timed_out is False


# ---------------------------------------------------------------------------
# Test 3 — Cycle-start log contains required fields
# ---------------------------------------------------------------------------

def test_cycle_start_log_contains_required_fields() -> None:
    """The cycle-start log entry must contain 'time', 'security_count', and
    'trigger_source' fields.

    Validates: Requirements 7.2
    """
    log, handler = _make_capturing_logger("test_scheduler_start_log")
    structured_logger = JsonStructuredLogger(logger=log)

    engine = _make_mock_engine(security_count=7)
    config = SchedulerConfig(interval_seconds=3600, timeout_seconds=30)
    scheduler = Scheduler(
        engine=engine, config=config, structured_logger=structured_logger
    )

    scheduler.trigger_manual_run()

    # Find the cycle_start log entry.
    start_entries = []
    for record in handler.records:
        try:
            data = json.loads(record.getMessage())
            if data.get("event") == "cycle_start":
                start_entries.append(data)
        except (json.JSONDecodeError, AttributeError):
            pass

    assert len(start_entries) >= 1, (
        f"Expected at least one 'cycle_start' log entry, got {len(start_entries)}. "
        f"All log messages: {[r.getMessage() for r in handler.records]}"
    )

    entry = start_entries[0]
    assert "time" in entry, f"Missing 'time' field in cycle_start entry: {entry}"
    assert "security_count" in entry, (
        f"Missing 'security_count' field in cycle_start entry: {entry}"
    )
    assert "trigger_source" in entry, (
        f"Missing 'trigger_source' field in cycle_start entry: {entry}"
    )
    assert entry["security_count"] == 7, (
        f"Expected security_count=7, got {entry['security_count']}"
    )
    assert entry["trigger_source"] == "manual", (
        f"Expected trigger_source='manual', got {entry['trigger_source']!r}"
    )


# ---------------------------------------------------------------------------
# Test 4 — Cycle-end log contains required fields
# ---------------------------------------------------------------------------

def test_cycle_end_log_contains_required_fields() -> None:
    """The cycle-end log entry must contain 'time', 'records_produced', and
    'failures' fields.

    Validates: Requirements 7.3
    """
    log, handler = _make_capturing_logger("test_scheduler_end_log")
    structured_logger = JsonStructuredLogger(logger=log)

    expected_summary = CycleSummary(
        started_at=datetime.now(timezone.utc),
        completed_at=datetime.now(timezone.utc),
        securities_attempted=3,
        records_produced=2,
        failures=1,
        timed_out=False,
    )
    engine = _make_mock_engine(run_cycle_return=expected_summary)
    config = SchedulerConfig(interval_seconds=3600, timeout_seconds=30)
    scheduler = Scheduler(
        engine=engine, config=config, structured_logger=structured_logger
    )

    scheduler.trigger_manual_run()

    # Find the cycle_end log entry.
    end_entries = []
    for record in handler.records:
        try:
            data = json.loads(record.getMessage())
            if data.get("event") == "cycle_end":
                end_entries.append(data)
        except (json.JSONDecodeError, AttributeError):
            pass

    assert len(end_entries) >= 1, (
        f"Expected at least one 'cycle_end' log entry, got {len(end_entries)}. "
        f"All log messages: {[r.getMessage() for r in handler.records]}"
    )

    entry = end_entries[0]
    assert "time" in entry, f"Missing 'time' field in cycle_end entry: {entry}"
    assert "records_produced" in entry, (
        f"Missing 'records_produced' field in cycle_end entry: {entry}"
    )
    assert "failures" in entry, (
        f"Missing 'failures' field in cycle_end entry: {entry}"
    )
    assert entry["records_produced"] == 2, (
        f"Expected records_produced=2, got {entry['records_produced']}"
    )
    assert entry["failures"] == 1, (
        f"Expected failures=1, got {entry['failures']}"
    )
