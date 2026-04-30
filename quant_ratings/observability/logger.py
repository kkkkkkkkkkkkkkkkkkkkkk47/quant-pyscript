"""StructuredLogger abstraction for the Quant Ratings engine.

Defines the :class:`StructuredLogger` ABC used by the :class:`RatingEngine`
to emit structured (JSON) log entries, and the concrete
:class:`JsonStructuredLogger` implementation.
"""

from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any, Optional


class StructuredLogger(ABC):
    """Abstract base class for structured (JSON) logging.

    Each method corresponds to a log severity level and accepts an arbitrary
    set of keyword arguments that will be serialised as JSON fields.
    """

    @abstractmethod
    def info(self, message: str, **fields: Any) -> None:
        """Emit an INFO-level structured log entry."""

    @abstractmethod
    def warning(self, message: str, **fields: Any) -> None:
        """Emit a WARNING-level structured log entry."""

    @abstractmethod
    def error(self, message: str, **fields: Any) -> None:
        """Emit an ERROR-level structured log entry."""


class JsonStructuredLogger(StructuredLogger):
    """Concrete :class:`StructuredLogger` that emits JSON-formatted log lines.

    Each log call produces a single JSON object on one line containing at
    minimum:

    * ``timestamp`` — UTC ISO-8601 string (e.g. ``"2025-01-15T14:00:00Z"``)
    * ``level`` — severity string (``"INFO"``, ``"WARNING"``, or ``"ERROR"``)
    * ``event`` — the *message* argument

    Any extra ``**fields`` are merged into the JSON object.

    Requirements: 11.1, 11.5

    Args:
        logger: Optional :class:`logging.Logger` to use.  Defaults to
            ``logging.getLogger("quant_ratings")``.
        version: Software version string included in engine start/stop events.
            Defaults to ``"unknown"``.
    """

    def __init__(
        self,
        logger: Optional[logging.Logger] = None,
        version: str = "unknown",
    ) -> None:
        self._logger = logger if logger is not None else logging.getLogger(
            "quant_ratings"
        )
        self._version = version

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _utc_now_iso() -> str:
        """Return the current UTC time as an ISO-8601 string ending in 'Z'."""
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    def _emit(self, level: str, message: str, **fields: Any) -> None:
        """Build and emit a JSON log line at the given *level*.

        Args:
            level: One of ``"INFO"``, ``"WARNING"``, or ``"ERROR"``.
            message: The event description (mapped to the ``event`` key).
            **fields: Additional key/value pairs merged into the JSON object.
        """
        payload: dict[str, Any] = {
            "timestamp": self._utc_now_iso(),
            "level": level,
            "event": message,
        }
        payload.update(fields)
        log_line = json.dumps(payload, default=str)

        level_map = {
            "INFO": logging.INFO,
            "WARNING": logging.WARNING,
            "ERROR": logging.ERROR,
        }
        self._logger.log(level_map.get(level, logging.INFO), log_line)

    # ------------------------------------------------------------------
    # StructuredLogger interface
    # ------------------------------------------------------------------

    def info(self, message: str, **fields: Any) -> None:
        """Emit an INFO-level JSON log entry."""
        self._emit("INFO", message, **fields)

    def warning(self, message: str, **fields: Any) -> None:
        """Emit a WARNING-level JSON log entry."""
        self._emit("WARNING", message, **fields)

    def error(self, message: str, **fields: Any) -> None:
        """Emit an ERROR-level JSON log entry."""
        self._emit("ERROR", message, **fields)

    # ------------------------------------------------------------------
    # Engine lifecycle events (Requirement 11.5)
    # ------------------------------------------------------------------

    def log_engine_start(self) -> None:
        """Emit an INFO-level JSON log entry for engine start.

        Includes the ``version`` field and a UTC ``timestamp``.
        """
        self._emit("INFO", "engine_start", version=self._version)

    def log_engine_stop(self) -> None:
        """Emit an INFO-level JSON log entry for engine stop.

        Includes the ``version`` field and a UTC ``timestamp``.
        """
        self._emit("INFO", "engine_stop", version=self._version)
