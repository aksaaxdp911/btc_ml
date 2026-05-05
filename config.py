import os
from dotenv import load_dotenv

load_dotenv()

# Database
DATABASE_URL = os.getenv("DATABASE_URL", "")

# Binance
BINANCE_API_KEY    = os.getenv("BINANCE_API_KEY", "")
BINANCE_API_SECRET = os.getenv("BINANCE_API_SECRET", "")
BINANCE_BASE_URL   = "https://fapi.binance.com"
BINANCE_DATA_URL   = "https://fapi.binance.com"

# Target symbol
SYMBOL = os.getenv("SYMBOL", "BTCUSDT")

# Prediction settings
PREDICTION_THRESHOLD = 0.005   # 0.5%  → naik/turun
PREDICTION_HORIZON   = 4       # 4 jam ke depan
CANDLE_INTERVAL      = "1h"    # resolusi kline

# Fetch settings
FETCH_INTERVAL_MINUTES = int(os.getenv("FETCH_INTERVAL_MINUTES", "60"))
HISTORICAL_DAYS        = 90    # ambil 90 hari history saat pertama kali jalan

# Logging
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
