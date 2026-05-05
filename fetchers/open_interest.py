"""
Fetcher: Open Interest (Historical)
Endpoint: GET /futures/data/openInterestHist
"""
from loguru import logger
from sqlalchemy.dialects.postgresql import insert

from fetchers.base import BinanceFetcher
from database.connection import SessionLocal
from database.models import OpenInterest
from config import SYMBOL, HISTORICAL_DAYS


class OpenInterestFetcher(BinanceFetcher):

    def fetch_history(self, start_ms: int = None, end_ms: int = None) -> list[dict]:
        start_ms = start_ms or self.days_ago_ms(HISTORICAL_DAYS)
        end_ms   = end_ms   or self.now_ms()
        results  = []

        while start_ms < end_ms:
            batch = self._get("/futures/data/openInterestHist", params={
                "symbol":    SYMBOL,
                "period":    "1h",
                "limit":     500,
                "startTime": start_ms,
                "endTime":   end_ms,
            })
            if not batch:
                break
            results.extend(batch)
            logger.debug(f"OI: got {len(batch)} rows")
            start_ms = batch[-1]["timestamp"] + 1
            if len(batch) < 500:
                break

        logger.info(f"OpenInterest: total {len(results)} rows fetched.")
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
                    "open_interest": float(r["sumOpenInterestValue"]),
                }
                for r in rows
            ]
            stmt = insert(OpenInterest).values(records)
            stmt = stmt.on_conflict_do_nothing(index_elements=["symbol", "timestamp"])
            db.execute(stmt)
            db.commit()
            logger.info(f"OpenInterest: {len(records)} rows saved.")
        except Exception as e:
            db.rollback()
            logger.error(f"OpenInterest save error: {e}")
        finally:
            db.close()

    def run_initial(self):
        rows = self.fetch_history()
        self.save(rows)

    def run_update(self):
        rows = self._get("/futures/data/openInterestHist", params={
            "symbol": SYMBOL, "period": "1h", "limit": 5
        })
        self.save(rows)
