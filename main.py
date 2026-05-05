"""
Entry point — dijalankan oleh Railway.
"""
import sys
from loguru import logger
from config import LOG_LEVEL
from pipeline.scheduler import start_scheduler

# Setup logging
logger.remove()
logger.add(
    sys.stdout,
    level=LOG_LEVEL,
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | {message}",
    colorize=True,
)
logger.add(
    "logs/pipeline.log",
    rotation="100 MB",
    retention="30 days",
    level="DEBUG",
)

if __name__ == "__main__":
    logger.info("BTC-ML Pipeline starting...")
    start_scheduler()
