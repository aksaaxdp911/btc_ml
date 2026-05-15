"""
Entry point — Railway.
Startup: restore model dari DB, lalu jalankan pipeline normal.
"""
import sys
import os
import threading
from loguru import logger
from config import LOG_LEVEL

logger.remove()
logger.add(
    sys.stdout,
    level=LOG_LEVEL,
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | {message}",
    colorize=True,
)

if __name__ == "__main__":
    logger.info("BTC-ML Pipeline starting...")

    from database.connection import init_db
    init_db()

    # Restore model artifacts dari PostgreSQL
    logger.info("Restoring model artifacts from DB...")
    try:
        from models.model_store import restore_all_models
        count = restore_all_models()
        if count == 0:
            logger.warning("No models found in DB — prediksi akan 0.00% sampai training selesai")
        else:
            logger.info(f"✓ {count} model files restored")
    except Exception as e:
        logger.error(f"Model restore failed: {e}")

    # Start dashboard
    from dashboard.app import run_dashboard
    dash_thread = threading.Thread(target=run_dashboard, daemon=True)
    dash_thread.start()
    logger.info("Dashboard running on port 8080")

    # Start scheduler
    from pipeline.scheduler import start_scheduler
    start_scheduler()
