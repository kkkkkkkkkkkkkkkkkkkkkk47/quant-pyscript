"""CycleSummary model for the Quant Ratings engine.

A CycleSummary captures the aggregate outcome of a single Rating_Engine
computation cycle, providing the counts and timing information required by
the Scheduler and observability layer (Requirements 7.3, 8.1).
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class CycleSummary:
    """Aggregate outcome of a single Rating_Engine computation cycle.

    Produced by :meth:`~quant_ratings.engine.RatingEngine.run_cycle` and
    returned to the Scheduler after each run.  The Scheduler logs the fields
    of this object as part of the structured cycle-end log entry.

    Attributes:
        started_at: UTC datetime at which the cycle began.
        completed_at: UTC datetime at which the cycle finished, or ``None``
            if the cycle is still in progress or was aborted (e.g. due to a
            timeout).
        securities_attempted: Total number of securities for which a rating
            computation was attempted during this cycle.
        records_produced: Number of RatingRecord instances successfully
            persisted during this cycle.
        failures: Number of securities that failed to produce a persisted
            rating record (after any retries).
        data_deficient_count: Number of successfully persisted records that
            were flagged as data-deficient (all three sub-scorers fell back to
            neutral).
        timed_out: ``True`` when the cycle was terminated because it exceeded
            the configured timeout period; partial results are not persisted in
            this case.
    """

    started_at: datetime
    completed_at: Optional[datetime] = field(default=None)
    securities_attempted: int = 0
    records_produced: int = 0
    failures: int = 0
    data_deficient_count: int = 0
    timed_out: bool = False
