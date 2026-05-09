"""
Scheduler — data fetch + prediction tiap jam.
"""
import time
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from loguru import logger

from fetchers.funding_rate      import FundingRateFetcher
from fetchers.open_interest     import OpenInterestFetcher
from fetchers.long_short_ratio  import LongShortRatioFetcher
from fetchers.taker_volume      import TakerVolumeFetcher
from fetchers.liquidations      import LiquidationFetcher
from fetchers.mark_price_klines import MarkPriceKlineFetcher
from fetchers.cvd               import CVDCalculator
from pipeline.feature_engineering import run_feature_engineering
from database.connection        import init_db


def run_initial_fetch():
    logger.info("=" * 60)
    logger.info("INITIAL FETCH — mengambil history...")
    logger.info("=" * 60)

    steps = [
        ("MarkPriceKlines", MarkPriceKlineFetcher().run_initial),
        ("FundingRate",     FundingRateFetcher().run_initial),
        ("OpenInterest",    OpenInterestFetcher().run_initial),
        ("LongShortRatio",  LongShortRatioFetcher().run_initial),
        ("TakerVolume",     TakerVolumeFetcher().run_initial),
        ("Liquidations",    LiquidationFetcher().run_initial),
        ("CVD",             CVDCalculator().run),
        ("Features",        run_feature_engineering),
    ]

    for name, fn in steps:
        logger.info(f"▶ {name}")
        try:
            fn()
            logger.info(f"  ✓ {name} done")
        except Exception as e:
            logger.error(f"  ✗ {name} failed: {e}")
        time.sleep(1)

    logger.info("INITIAL FETCH selesai.")


def run_hourly_update():
    logger.info("-" * 40)
    logger.info("HOURLY UPDATE...")

    steps = [
        ("MarkPriceKlines", MarkPriceKlineFetcher().run_update),
        ("FundingRate",     FundingRateFetcher().run_update),
        ("OpenInterest",    OpenInterestFetcher().run_update),
        ("LongShortRatio",  LongShortRatioFetcher().run_update),
        ("TakerVolume",     TakerVolumeFetcher().run_update),
        ("Liquidations",    LiquidationFetcher().run_update),
        ("CVD",             CVDCalculator().run),
        ("Features",        run_feature_engineering),
        ("Prediction",      run_prediction_job),
    ]

    for name, fn in steps:
        try:
            fn()
        except Exception as e:
            logger.error(f"  ✗ {name} failed: {e}")

    logger.info("HOURLY UPDATE selesai.")


def run_prediction_job():
    """Jalankan prediksi dan log hasilnya."""
    try:
        from predict import run_prediction
        result = run_prediction()
        if "error" not in result:
            logger.info(
                f"PREDIKSI → {result['prediction']} "
                f"({result['confidence']}% confidence) "
                f"| Regime: {result['regime']}"
            )
    except Exception as e:
        logger.error(f"Prediction job failed: {e}")


def run_weekly_training():
    """Retrain semua model tiap minggu."""
    try:
        from pipeline.trainer import run_training
        run_training()
    except Exception as e:
        logger.error(f"Weekly training failed: {e}")


def start_scheduler():
    init_db()
    run_initial_fetch()

    scheduler = BlockingScheduler(timezone="UTC")

    # Hourly update + prediction
    scheduler.add_job(
        run_hourly_update,
        trigger=CronTrigger(minute=5),
        id="hourly_update",
        max_instances=1,
        coalesce=True,
    )

    # Weekly retraining (Minggu 02:00 UTC)
    scheduler.add_job(
        run_weekly_training,
        trigger=CronTrigger(day_of_week="sun", hour=2, minute=0),
        id="weekly_training",
        max_instances=1,
        coalesce=True,
    )

    logger.info("Scheduler aktif:")
    logger.info("  - Hourly update + prediction (HH:05 UTC)")
    logger.info("  - Weekly retraining (Minggu 02:00 UTC)")

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Scheduler dihentikan.")
