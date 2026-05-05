"""
Scheduler — jalankan semua fetcher secara berkala menggunakan APScheduler.
Initial run: ambil 90 hari history semua data source.
Hourly run:  fetch data terbaru saja (incremental).
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
    logger.info("INITIAL FETCH — mengambil 90 hari history...")
    logger.info("=" * 60)

    steps = [
        ("MarkPriceKlines + SpotKlines", MarkPriceKlineFetcher().run_initial),
        ("FundingRate",                  FundingRateFetcher().run_initial),
        ("OpenInterest",                 OpenInterestFetcher().run_initial),
        ("LongShortRatio (3 types)",     LongShortRatioFetcher().run_initial),
        ("TakerVolume",                  TakerVolumeFetcher().run_initial),
        ("Liquidations",                 LiquidationFetcher().run_initial),
        ("CVD Calculation",              CVDCalculator().run),
        ("Feature Engineering",          run_feature_engineering),
    ]

    for name, fn in steps:
        logger.info(f"▶ {name}")
        try:
            fn()
        except Exception as e:
            logger.error(f"  ✗ {name} failed: {e}")
        else:
            logger.info(f"  ✓ {name} done")
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
    ]

    for name, fn in steps:
        try:
            fn()
        except Exception as e:
            logger.error(f"  ✗ {name} update failed: {e}")

    logger.info("HOURLY UPDATE selesai.")


def start_scheduler():
    init_db()
    run_initial_fetch()

    scheduler = BlockingScheduler(timezone="UTC")
    scheduler.add_job(
        run_hourly_update,
        trigger=CronTrigger(minute=5),
        id="hourly_update",
        max_instances=1,
        coalesce=True,
    )

    logger.info("Scheduler aktif — update tiap jam (HH:05 UTC)")
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Scheduler dihentikan.")
