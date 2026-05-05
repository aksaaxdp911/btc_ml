"""
Fetcher: Long/Short Ratio — 3 versi sekaligus
1. Global Account  : /futures/data/globalLongShortAccountRatio
2. Top Account     : /futures/data/topLongShortAccountRatio
3. Top Position    : /futures/data/topLongShortPositionRatio
"""
from loguru import logger
from sqlalchemy.dialects.postgresql import insert

from fetchers.base import BinanceFetcher
from database.connection import SessionLocal
from database.models import LongShortRatio
from config import SYMBOL, HISTORICAL_DAYS

ENDPOINTS = {
    "global_account": "/futures/data/globalLongShortAccountRatio",
    "top_account":    "/futures/data/topLongShortAccountRatio",
    "top_position":   "/futures/data/topLongShortPositionRatio",
}


class LongShortRatioFetcher(BinanceFetcher):

    def fetch_history(self, ratio_type: str, start_ms: int = None, end_ms: int = None) -> list[dict]:
        endpoint = ENDPOINTS[ratio_type]
        start_ms = start_ms or self.days_ago_ms(HISTORICAL_DAYS)
        end_ms   = end_ms   or self.now_ms()
        results  = []

        while start_ms < end_ms:
            batch = self._get(endpoint, params={
                "symbol":    SYMBOL,
                "period":    "1h",
                "limit":     500,
                "startTime": start_ms,
                "endTime":   end_ms,
            })
            if not batch:
                break
            results.extend(batch)
            last_ts = int(batch[-1]["timestamp"])
            logger.debug(f"L/S {ratio_type}: got {len(batch)} rows, last={last_ts}")
            start_ms = last_ts + 1
            if len(batch) < 500:
                break

        logger.info(f"LongShort ({ratio_type}): total {len(results)} rows.")
        return results

    def save(self, rows: list[dict], ratio_type: str):
        if not rows:
            return
        db = SessionLocal()
        try:
            records = []
            for r in rows:
                records.append({
                    "symbol":           SYMBOL,
                    "timestamp":        int(r["timestamp"]),
                    "ratio_type":       ratio_type,
                    "long_short_ratio": float(r.get("longShortRatio") or 0) or None,
                    "long_account":     float(r.get("longAccount") or 0) or None,
                    "short_account":    float(r.get("shortAccount") or 0) or None,
                })
            stmt = insert(LongShortRatio).values(records)
            stmt = stmt.on_conflict_do_nothing(index_elements=["symbol", "timestamp", "ratio_type"])
            db.execute(stmt)
            db.commit()
            logger.info(f"LongShort ({ratio_type}): {len(records)} rows saved.")
        except Exception as e:
            db.rollback()
            logger.error(f"LongShort save error: {e}")
        finally:
            db.close()

    def run_initial(self):
        for rtype in ENDPOINTS:
            rows = self.fetch_history(rtype)
            self.save(rows, rtype)

    def run_update(self):
        for rtype, endpoint in ENDPOINTS.items():
            rows = self._get(endpoint, params={"symbol": SYMBOL, "period": "1h", "limit": 5})
            self.save(rows, rtype)
