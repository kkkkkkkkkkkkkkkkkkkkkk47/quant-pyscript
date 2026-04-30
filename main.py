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
import os
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


def _seed_if_empty(store, registry) -> None:
    """Seed the database with realistic fallback data if it's completely empty.

    This ensures the UI shows something immediately on first deploy before
    the first live rating cycle completes.
    """
    import uuid
    from datetime import datetime, timezone, timedelta
    from quant_ratings.models.rating_record import RatingRecord
    from quant_ratings.models.weight_profile import WeightProfile

    # Check if any records exist
    try:
        securities = registry.all_securities()
        if not securities:
            return
        # Check first security
        existing = store.get_latest(securities[0].identifier)
        if existing is not None:
            logger.info("Database already has data — skipping seed.")
            return
    except Exception:
        return

    logger.info("Database is empty — seeding with fallback data...")
    now = datetime.now(timezone.utc)

    seed_data = [
        # FX Majors
        ("EUR/USD", "FX", 3.85, "Buy",        2.0, 4.0, 4.5, 20, 30, 50, "Major"),
        ("GBP/USD", "FX", 3.20, "Buy",        2.5, 3.5, 3.5, 20, 30, 50, "Major"),
        ("USD/JPY", "FX", 2.40, "Sell",       2.0, 2.5, 2.5, 20, 30, 50, "Major"),
        ("AUD/USD", "FX", 3.10, "Buy",        2.8, 3.2, 3.2, 20, 30, 50, "Major"),
        ("USD/CAD", "FX", 2.60, "Neutral",    2.5, 2.8, 2.5, 20, 30, 50, "Major"),
        # FX Volatile Crosses
        ("GBP/JPY", "FX", 4.60, "Strong Buy", 4.5, 4.8, 4.2, 40, 40, 20, "Volatile_Cross"),
        ("EUR/JPY", "FX", 3.70, "Buy",        3.5, 3.8, 3.6, 40, 40, 20, "Volatile_Cross"),
        # FX Emerging
        ("USD/ZAR", "FX", 1.20, "Strong Sell",1.0, 1.5, 1.0, 10, 10, 80, "Emerging"),
        ("USD/NGN", "FX", 1.50, "Sell",       1.5, 1.8, 1.4, 10, 10, 80, "Emerging"),
        # Equities
        ("AAPL",   "Equity", 3.55, "Buy",     3.2, 4.1, 3.2, 33.3, 33.3, 33.4, None),
        ("MSFT",   "Equity", 3.90, "Buy",     3.5, 4.2, 3.8, 33.3, 33.3, 33.4, None),
        ("GOOGL",  "Equity", 3.40, "Buy",     3.0, 3.8, 3.3, 33.3, 33.3, 33.4, None),
        ("AMZN",   "Equity", 3.65, "Buy",     3.3, 4.0, 3.5, 33.3, 33.3, 33.4, None),
        # Indices
        ("SPY",    "Index",  3.50, "Buy",     3.2, 3.8, 3.4, 33.3, 33.3, 33.4, None),
        ("QQQ",    "Index",  3.60, "Buy",     3.4, 3.9, 3.4, 33.3, 33.3, 33.4, None),
        # Commodity
        ("GLD",    "Commodity", 3.80, "Buy",  3.5, 3.8, 4.0, 33.3, 33.3, 33.4, None),
        # Crypto
        ("BTC/USD","Crypto", 2.50, "Neutral", 2.5, 2.5, 2.5, 33.3, 33.3, 33.4, None),
        ("ETH/USD","Crypto", 1.80, "Sell",    1.5, 2.0, 1.8, 33.3, 33.3, 33.4, None),
    ]

    for i, (sid, ac, comp, rating, s, o, e, sp, op, ep, sub) in enumerate(seed_data):
        try:
            wp = WeightProfile(asset_class=ac, sub_category=sub,
                               sentiment_pct=sp, orderflow_pct=op, economic_pct=ep)
            r = RatingRecord(
                record_id=str(uuid.uuid4()),
                security_id=sid, asset_class=ac,
                composite_score=comp, rating=rating,
                sentiment_score=s, orderflow_score=o, economic_score=e,
                weight_profile=wp,
                data_deficient=(s == 2.5 and o == 2.5 and e == 2.5),
                computed_at=now - timedelta(minutes=i * 2),
            )
            store.save(r)
        except Exception as exc:
            logger.warning("Seed skipped for %s: %s", sid, exc)

    logger.info("Seeded %d fallback records.", len(seed_data))


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
        default=int(os.environ.get("PORT", 8000)),
        help="API server port (default: $PORT env var or 8000)",
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

    # Seed the database with fallback data if it's empty
    _seed_if_empty(engine._store, engine._security_registry)

    # Start scheduler in background (unless disabled)
    scheduler = None
    if not args.no_scheduler:
        scheduler = _run_scheduler(engine, interval_seconds=args.interval)

        # Run the first live cycle immediately in background
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
