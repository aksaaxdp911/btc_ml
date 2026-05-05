"""
Fetcher: Taker Buy/Sell Volume
Endpoint: GET /futures/data/takerlongshortRatio
"""
from loguru import logger
from sqlalchemy.dialects.postgresql import insert

from fetchers.base import BinanceFetcher
from database.connection import SessionLocal
from database.models import TakerVolume
from config import SYMBOL, HISTORICAL_DAYS


class TakerVolumeFetcher(BinanceFetcher):

    def fetch_history(self, start_ms: int = None, end_ms: int = None) -> list[dict]:
        start_ms = start_ms or self.days_ago_ms(HISTORICAL_DAYS)
        end_ms   = end_ms   or self.now_ms()
        results  = []

        while start_ms < end_ms:
            batch = self._get("/futures/data/takerlongshortRatio", params={
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
            start_ms = last_ts + 1
            if len(batch) < 500:
                break

        logger.info(f"TakerVolume: total {len(results)} rows fetched.")
        return results

    def save(self, rows: list[dict]):
        if not rows:
            return
        db = SessionLocal()
        try:
            records = [
                {
                    "symbol":        SYMBOL,
                    "timestamp":     int(r["timestamp"]),
                    "buy_vol":       float(r["buyVol"]),
                    "sell_vol":      float(r["sellVol"]),
                    "buy_sell_ratio": float(r.get("buySellRatio") or 0) or None,
                }
                for r in rows
            ]
            stmt = insert(TakerVolume).values(records)
            stmt = stmt.on_conflict_do_nothing(index_elements=["symbol", "timestamp"])
            db.execute(stmt)
            db.commit()
            logger.info(f"TakerVolume: {len(records)} rows saved.")
        except Exception as e:
            db.rollback()
            logger.error(f"TakerVolume save error: {e}")
        finally:
            db.close()

    def run_initial(self):
        rows = self.fetch_history()
        self.save(rows)

    def run_update(self):
        rows = self._get("/futures/data/takerlongshortRatio", params={
            "symbol": SYMBOL, "period": "1h", "limit": 5
        })
        self.save(rows)
