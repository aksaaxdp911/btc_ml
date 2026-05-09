"""
Entry point — Railway.
Urutan startup:
1. Init DB
2. Cek model — kalau belum ada, training dulu
3. Jalankan initial fetch + feature engineering
4. Start scheduler (hourly update + prediction)
"""
import sys
import os
from loguru import logger
from config import LOG_LEVEL

# Setup logging
logger.remove()
logger.add(
    sys.stdout,
    level=LOG_LEVEL,
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | {message}",
    colorize=True,
)

def model_exists() -> bool:
    return os.path.exists("model_artifacts/xgboost_model.pkl")

if __name__ == "__main__":
    logger.info("BTC-ML Pipeline starting...")

    from database.connection import init_db
    init_db()

    from pipeline.scheduler import start_scheduler
    start_scheduler()
