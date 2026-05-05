"""
Fetcher: Funding Rate
Endpoint: GET /fapi/v1/fundingRate
Limit: 1000 baris per request, loop untuk ambil history penuh.
"""
from loguru import logger
from sqlalchemy.dialects.postgresql import insert

from fetchers.base import BinanceFetcher
from database.connection import SessionLocal
from database.models import FundingRate
from config import SYMBOL, HISTORICAL_DAYS


class FundingRateFetcher(BinanceFetcher):

    def fetch_history(self, start_ms: int = None, end_ms: int = None) -> list[dict]:
        """Ambil seluruh history funding rate dalam rentang waktu."""
        start_ms = start_ms or self.days_ago_ms(HISTORICAL_DAYS)
        end_ms   = end_ms   or self.now_ms()
        results  = []

        while start_ms < end_ms:
            batch = self._get("/fapi/v1/fundingRate", params={
                "symbol": SYMBOL,
                "startTime": start_ms,
                "endTime": end_ms,
                "limit": 1000,
            })
            if not batch:
                break
            results.extend(batch)
            logger.debug(f"FundingRate: got {len(batch)} rows, last={batch[-1]['fundingTime']}")
            start_ms = batch[-1]["fundingTime"] + 1
            if len(batch) < 1000:
                break

        logger.info(f"FundingRate: total {len(results)} rows fetched.")
        return results

    def fetch_latest(self) -> dict:
        """Ambil 1 data terbaru saja (untuk update berkala)."""
        data = self._get("/fapi/v1/fundingRate", params={"symbol": SYMBOL, "limit": 1})
        return data[0] if data else {}

    def save(self, rows: list[dict]):
        if not rows:
            return
        db = SessionLocal()
        try:
            records = [
                {
                    "symbol":       SYMBOL,
                    "funding_time": int(r["fundingTime"]),
                    "funding_rate": float(r["fundingRate"]),
                    "mark_price":   float(r.get("markPrice") or 0) or None,
                }
                for r in rows
            ]
            stmt = insert(FundingRate).values(records)
            stmt = stmt.on_conflict_do_nothing(index_elements=["symbol", "funding_time"])
            db.execute(stmt)
            db.commit()
            logger.info(f"FundingRate: {len(records)} rows saved.")
        except Exception as e:
            db.rollback()
            logger.error(f"FundingRate save error: {e}")
        finally:
            db.close()

    def run_initial(self):
        rows = self.fetch_history()
        self.save(rows)

    def run_update(self):
        row = self.fetch_latest()
        self.save([row] if row else [])
