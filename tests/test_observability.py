"""Unit tests for observability components.

Tests for :class:`JsonStructuredLogger`, :class:`LogAlertSink`, and the
RatingEngine's integration with both.

Feature: quant-ratings
Requirements: 11.1, 11.2, 11.3, 11.5
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Optional

import pytest

from quant_ratings.aggregator.aggregator import Aggregator
from quant_ratings.config.security_registry import SecurityRegistry
from quant_ratings.config.weight_profile_registry import WeightProfileRegistry
from quant_ratings.engine.data_manager import DataManager
from quant_ratings.engine.rating_engine import RatingEngine
from quant_ratings.models.enums import AssetClass
from quant_ratings.models.rating_record import RatingRecord
from quant_ratings.models.security import Security
from quant_ratings.observability.alert_sink import AlertSink, LogAlertSink
from quant_ratings.observability.logger import JsonStructuredLogger
from quant_ratings.persistence.base import RatingStore
from quant_ratings.providers.base import DataProviderAdapter
from quant_ratings.providers.mock_provider import MockDataProvider
from quant_ratings.scorers.economic_scorer import EconomicScorer
from quant_ratings.scorers.orderflow_scorer import OrderFlowScorer
from quant_ratings.scorers.sentiment_scorer import SentimentScorer


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


def _make_capturing_logger(name: str = "test_logger") -> tuple[logging.Logger, _CapturingHandler]:
    """Return a (Logger, CapturingHandler) pair with propagation disabled."""
    log = logging.getLogger(name)
    log.setLevel(logging.DEBUG)
    handler = _CapturingHandler()
    log.addHandler(handler)
    log.propagate = False
    return log, handler


class _AlwaysFailingProvider(DataProviderAdapter):
    """DataProviderAdapter that returns None for all data — simulates a broken feed.

    All data fields return None, causing all scorers to fall back to neutral
    and producing data_deficient=True records. With 100% deficiency rate
    (exceeding the 20% threshold), the engine emits a high-severity alert.
    """

    def fetch_retail_positioning(self, security: Security):  # type: ignore[override]
        return None

    def fetch_vix(self):  # type: ignore[override]
        return None

    def fetch_audjpy(self):  # type: ignore[override]
        return None

    def fetch_tick_volume(self, security: Security):  # type: ignore[override]
        return None

    def fetch_footprint(self, security: Security):  # type: ignore[override]
        return None

    def fetch_dom(self, security: Security):  # type: ignore[override]
        return None

    def fetch_macro(self, security: Security):  # type: ignore[override]
        return None


class _InMemoryStore(RatingStore):
    """Minimal in-memory RatingStore for testing."""

    def __init__(self) -> None:
        self.records: list[RatingRecord] = []

    def save(self, record: RatingRecord) -> None:
        self.records.append(record)

    def get_latest(self, security_id: str) -> Optional[RatingRecord]:
        matches = [r for r in self.records if r.security_id == security_id]
        return matches[-1] if matches else None

    def get_history(self, security_id: str, from_utc: datetime, to_utc: datetime) -> list[RatingRecord]:
        return []

    def get_latest_by_asset_class(self, asset_class: AssetClass) -> list[RatingRecord]:
        return []


class _RecordingAlertSink(AlertSink):
    """AlertSink that records all high-severity alerts."""

    def __init__(self) -> None:
        self.alerts: list[tuple[str, str]] = []

    def send_high_severity(self, title: str, body: str) -> None:
        self.alerts.append((title, body))


def _make_engine(
    securities: list[Security],
    provider: Optional[DataProvider] = None,
    alert_sink: Optional[AlertSink] = None,
) -> RatingEngine:
    registry = SecurityRegistry()
    for sec in securities:
        registry.add(sec)

    if provider is None:
        provider = MockDataProvider()
    if alert_sink is None:
        alert_sink = _RecordingAlertSink()

    return RatingEngine(
        security_registry=registry,
        weight_registry=WeightProfileRegistry(),
        data_manager=DataManager(providers=[provider]),
        sentiment_scorer=SentimentScorer(),
        orderflow_scorer=OrderFlowScorer(),
        economic_scorer=EconomicScorer(),
        aggregator=Aggregator(),
        store=_InMemoryStore(),
        alert_sink=alert_sink,
    )


# ---------------------------------------------------------------------------
# Test 1 — JsonStructuredLogger output is valid JSON with required fields
# ---------------------------------------------------------------------------

def test_structured_logger_output_is_valid_json() -> None:
    """Every log call from JsonStructuredLogger produces valid JSON with
    required fields: timestamp, level, event.

    Validates: Requirements 11.1
    """
    log, handler = _make_capturing_logger("test_json_logger_1")
    slogger = JsonStructuredLogger(logger=log)

    slogger.info("info_event", key1="value1")
    slogger.warning("warn_event", key2=42)
    slogger.error("error_event", key3=True)

    assert len(handler.records) == 3, "Expected 3 log records"

    for record in handler.records:
        raw = record.getMessage()
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            pytest.fail(f"Log output is not valid JSON: {raw!r} — {exc}")

        assert "timestamp" in data, f"Missing 'timestamp' in: {data}"
        assert "level" in data, f"Missing 'level' in: {data}"
        assert "event" in data, f"Missing 'event' in: {data}"

    # Verify level values
    levels = [json.loads(r.getMessage())["level"] for r in handler.records]
    assert levels == ["INFO", "WARNING", "ERROR"]

    # Verify event values
    events = [json.loads(r.getMessage())["event"] for r in handler.records]
    assert events == ["info_event", "warn_event", "error_event"]


# ---------------------------------------------------------------------------
# Test 2 — LogAlertSink logs at ERROR level
# ---------------------------------------------------------------------------

def test_log_alert_sink_logs_at_error_level() -> None:
    """LogAlertSink.send_high_severity() must emit a log record at ERROR level.

    Validates: Requirements 11.2, 11.3
    """
    log, handler = _make_capturing_logger("test_alert_sink_logger")
    sink = LogAlertSink(logger=log)

    sink.send_high_severity(title="Test Alert", body="Something went wrong")

    assert len(handler.records) == 1, "Expected exactly 1 log record"
    record = handler.records[0]
    assert record.levelno == logging.ERROR, (
        f"Expected ERROR level ({logging.ERROR}), got {record.levelno}"
    )
    # The message should contain both title and body
    msg = record.getMessage()
    assert "Test Alert" in msg
    assert "Something went wrong" in msg


# ---------------------------------------------------------------------------
# Test 3 — Consecutive provider failure detection triggers high-severity alert
# ---------------------------------------------------------------------------

def test_consecutive_provider_failure_detection() -> None:
    """When a provider always raises, >20% of securities are data-deficient
    (all fail), so the engine must emit at least one high-severity alert.

    Validates: Requirements 11.3
    """
    # Use 5 securities so that 100% failure rate (5/5) exceeds the 20% threshold
    securities = [
        Security(identifier=f"SEC{i}", asset_class=AssetClass.FX)
        for i in range(5)
    ]
    alert_sink = _RecordingAlertSink()
    engine = _make_engine(
        securities=securities,
        provider=_AlwaysFailingProvider(),
        alert_sink=alert_sink,
    )

    # Run two cycles
    engine.run_cycle()
    engine.run_cycle()

    assert len(alert_sink.alerts) >= 1, (
        "Expected at least one high-severity alert after provider failures, "
        f"got {len(alert_sink.alerts)}"
    )


# ---------------------------------------------------------------------------
# Test 4 — log_engine_start includes version field
# ---------------------------------------------------------------------------

def test_structured_logger_engine_start_includes_version() -> None:
    """log_engine_start() must emit a JSON log line containing the 'version' field.

    Validates: Requirements 11.5
    """
    log, handler = _make_capturing_logger("test_engine_start_logger")
    slogger = JsonStructuredLogger(logger=log, version="1.2.3")

    slogger.log_engine_start()

    assert len(handler.records) == 1, "Expected exactly 1 log record"
    raw = handler.records[0].getMessage()
    data = json.loads(raw)

    assert "version" in data, f"Missing 'version' in: {data}"
    assert data["version"] == "1.2.3", f"Expected version '1.2.3', got {data['version']!r}"
    assert data["event"] == "engine_start", f"Expected event 'engine_start', got {data['event']!r}"


# ---------------------------------------------------------------------------
# Test 5 — log_engine_stop includes version field
# ---------------------------------------------------------------------------

def test_structured_logger_engine_stop_includes_version() -> None:
    """log_engine_stop() must emit a JSON log line containing the 'version' field.

    Validates: Requirements 11.5
    """
    log, handler = _make_capturing_logger("test_engine_stop_logger")
    slogger = JsonStructuredLogger(logger=log, version="2.0.0")

    slogger.log_engine_stop()

    assert len(handler.records) == 1, "Expected exactly 1 log record"
    raw = handler.records[0].getMessage()
    data = json.loads(raw)

    assert "version" in data, f"Missing 'version' in: {data}"
    assert data["version"] == "2.0.0", f"Expected version '2.0.0', got {data['version']!r}"
    assert data["event"] == "engine_stop", f"Expected event 'engine_stop', got {data['event']!r}"
