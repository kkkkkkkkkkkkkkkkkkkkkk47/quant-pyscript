"""AlertSink abstraction for the Quant Ratings engine.

Defines the :class:`AlertSink` ABC used by the :class:`RatingEngine` to emit
high-severity alerts (e.g. to PagerDuty, Slack, or a logging channel).
The concrete :class:`LogAlertSink` implementation routes alerts to the
standard Python ``logging`` module at ERROR level.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Optional


class AlertSink(ABC):
    """Abstract base class for alerting channel integrations.

    Implementations must be non-blocking (or at least not raise exceptions
    that would abort a computation cycle).
    """

    @abstractmethod
    def send_high_severity(self, title: str, body: str) -> None:
        """Emit a high-severity alert.

        Args:
            title: Short, human-readable summary of the alert condition.
            body: Detailed description including relevant metrics or context.
        """


class LogAlertSink(AlertSink):
    """AlertSink implementation that routes alerts to the Python logging module.

    High-severity alerts are emitted at ERROR level so they surface in any
    standard logging configuration.

    Requirements: 11.2, 11.3

    Args:
        logger: Optional :class:`logging.Logger` to use.  Defaults to
            ``logging.getLogger("quant_ratings.alerts")``.
    """

    def __init__(self, logger: Optional[logging.Logger] = None) -> None:
        self._logger = logger if logger is not None else logging.getLogger(
            "quant_ratings.alerts"
        )

    def send_high_severity(self, title: str, body: str) -> None:
        """Log a high-severity alert at ERROR level.

        Args:
            title: Short, human-readable summary of the alert condition.
            body: Detailed description including relevant metrics or context.
        """
        self._logger.error("HIGH-SEVERITY ALERT | title=%r | body=%r", title, body)
