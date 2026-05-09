"""
Entry point — Railway.
Jalankan scheduler + dashboard web server secara bersamaan.
"""
import sys
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

    # Start dashboard di background thread
    from dashboard.app import run_dashboard
    dash_thread = threading.Thread(target=run_dashboard, daemon=True)
    dash_thread.start()
    logger.info("Dashboard running on port 8080")

    # Start scheduler (blocking — jalan di main thread)
    from pipeline.scheduler import start_scheduler
    start_scheduler()
