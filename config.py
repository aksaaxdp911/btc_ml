import os
from dotenv import load_dotenv

load_dotenv()

# Database
DATABASE_URL = os.getenv("DATABASE_URL", "")

# Binance
BINANCE_API_KEY    = os.getenv("BINANCE_API_KEY", "")
BINANCE_API_SECRET = os.getenv("BINANCE_API_SECRET", "")
BINANCE_BASE_URL   = "https://fapi.binance.com"

# Target symbol
SYMBOL = os.getenv("SYMBOL", "BTCUSDT")

# Prediction settings — REGRESSION
PREDICTION_HORIZONS = [8, 24]   # jam — dua horizon sekaligus
CANDLE_INTERVAL     = "1h"

# Threshold untuk interpretasi output regression
# Prediksi di luar range ini dianggap sinyal
SIGNAL_THRESHOLD = 0.015   # 1.5%

# Fetch settings
FETCH_INTERVAL_MINUTES = int(os.getenv("FETCH_INTERVAL_MINUTES", "60"))
HISTORICAL_DAYS        = 90

# Logging
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
