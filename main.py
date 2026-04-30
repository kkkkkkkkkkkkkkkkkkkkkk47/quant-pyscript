"""Quant Ratings — main entry point.

Starts the background rating scheduler and the FastAPI HTTP server together.

Usage::

    python main.py

Or to run only the API (scheduler disabled)::

    python main.py --no-scheduler

Or to run a single rating cycle and exit::

    python main.py --once
"""

from __future__ import annotations

import argparse
import logging
import sys
import threading

# Configure structured logging to stdout before any imports that use logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
    stream=sys.stdout,
)

logger = logging.getLogger("quant_ratings.main")


def _run_scheduler(engine, interval_seconds: int = 3600) -> None:
    """Start the background scheduler in a daemon thread."""
    from quant_ratings.scheduler.scheduler import Scheduler, SchedulerConfig
    from quant_ratings.observability.logger import JsonStructuredLogger

    config = SchedulerConfig(
        interval_seconds=interval_seconds,
        timeout_seconds=1800,
    )
    structured_logger = JsonStructuredLogger(version="0.1.0")
    scheduler = Scheduler(engine=engine, config=config, structured_logger=structured_logger)

    structured_logger.log_engine_start()
    logger.info("Starting scheduler with interval=%ds", interval_seconds)
    scheduler.start()
    return scheduler


def _run_once(engine) -> None:
    """Run a single rating cycle and print the summary."""
    from quant_ratings.observability.logger import JsonStructuredLogger

    structured_logger = JsonStructuredLogger(version="0.1.0")
    structured_logger.log_engine_start()

    logger.info("Running single rating cycle...")
    summary = engine.run_cycle()

    structured_logger.log_engine_stop()

    print("\n" + "=" * 60)
    print("CYCLE SUMMARY")
    print("=" * 60)
    print(f"  Started at:          {summary.started_at.isoformat()}")
    print(f"  Completed at:        {summary.completed_at.isoformat() if summary.completed_at else 'N/A'}")
    print(f"  Securities attempted: {summary.securities_attempted}")
    print(f"  Records produced:    {summary.records_produced}")
    print(f"  Failures:            {summary.failures}")
    print(f"  Data deficient:      {summary.data_deficient_count}")
    print(f"  Timed out:           {summary.timed_out}")
    print("=" * 60)

    # Print each persisted record
    if summary.records_produced > 0:
        print("\nRATING RESULTS")
        print("-" * 60)
        store = engine._store
        for sec in engine._security_registry.all_securities():
            record = store.get_latest(sec.identifier)
            if record:
                deficient_flag = " [DATA DEFICIENT]" if record.data_deficient else ""
                print(
                    f"  {record.security_id:<12} "
                    f"{record.rating:<12} "
                    f"composite={record.composite_score:.2f}  "
                    f"S={record.sentiment_score:.2f} "
                    f"O={record.orderflow_score:.2f} "
                    f"E={record.economic_score:.2f}"
                    f"{deficient_flag}"
                )
        print("-" * 60)


def _run_api(host: str = "0.0.0.0", port: int = 8000) -> None:
    """Start the FastAPI server (blocking)."""
    import uvicorn
    from quant_ratings.api.app import app

    logger.info("Starting API server on %s:%d", host, port)
    uvicorn.run(app, host=host, port=port, log_level="info")


def main() -> None:
    parser = argparse.ArgumentParser(description="Quant Ratings Engine")
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run a single rating cycle and exit (no API server)",
    )
    parser.add_argument(
        "--no-scheduler",
        action="store_true",
        help="Start the API server without the background scheduler",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=3600,
        help="Scheduler interval in seconds (default: 3600)",
    )
    parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="API server host (default: 0.0.0.0)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="API server port (default: 8000)",
    )
    parser.add_argument(
        "--db",
        default="sqlite:///quant_ratings.db",
        help="SQLAlchemy database URL (default: sqlite:///quant_ratings.db)",
    )
    args = parser.parse_args()

    # Build the live engine
    logger.info("Building live RatingEngine...")
    from quant_ratings.config.engine_factory import build_live_engine

    try:
        engine = build_live_engine(db_url=args.db)
        logger.info("RatingEngine ready.")
    except Exception as exc:
        logger.error("Failed to build RatingEngine: %s", exc)
        sys.exit(1)

    if args.once:
        # Single cycle mode — run and exit
        _run_once(engine)
        return

    # Start scheduler in background (unless disabled)
    scheduler = None
    if not args.no_scheduler:
        scheduler = _run_scheduler(engine, interval_seconds=args.interval)

        # Run the first cycle immediately so ratings are available before the
        # first scheduled interval fires
        logger.info("Running initial rating cycle...")
        t = threading.Thread(target=engine.run_cycle, daemon=True)
        t.start()

    # Start the API server (blocking — runs until Ctrl+C)
    try:
        _run_api(host=args.host, port=args.port)
    except KeyboardInterrupt:
        logger.info("Shutting down...")
    finally:
        if scheduler is not None:
            scheduler.stop()
            from quant_ratings.observability.logger import JsonStructuredLogger
            JsonStructuredLogger(version="0.1.0").log_engine_stop()
            logger.info("Scheduler stopped.")


if __name__ == "__main__":
    main()
