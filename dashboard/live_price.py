"""
Live price endpoint — langsung dari Binance API, bypass DB.
"""
import requests
from flask import jsonify
from config import SYMBOL

BINANCE_TICKER = "https://fapi.binance.com/fapi/v1/ticker/24hr"
BINANCE_PRICE  = "https://fapi.binance.com/fapi/v1/ticker/price"

def get_live_price():
    try:
        r = requests.get(BINANCE_TICKER, params={"symbol": SYMBOL}, timeout=5)
        d = r.json()
        return {
            "price":        float(d["lastPrice"]),
            "change_pct":   float(d["priceChangePercent"]),
            "change_abs":   float(d["priceChange"]),
            "high_24h":     float(d["highPrice"]),
            "low_24h":      float(d["lowPrice"]),
            "volume_24h":   float(d["volume"]),
            "mark_price":   float(d["lastPrice"]),
        }
    except Exception as e:
        return {"error": str(e)}
