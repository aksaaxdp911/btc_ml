"""
Fetcher: Mark Price Klines (1h)
Endpoint: GET /fapi/v1/markPriceKlines
Juga fetch Spot Klines untuk CVD spot.
"""
from loguru import logger
from sqlalchemy.dialects.postgresql import insert

from fetchers.base import BinanceFetcher
from database.connection import SessionLocal
from database.models import MarkPriceKline, SpotKline
from config import SYMBOL, HISTORICAL_DAYS

SPOT_BASE_URL = "https://api.binance.com"


class MarkPriceKlineFetcher(BinanceFetcher):

    def _fetch_klines_paginated(self, endpoint: str, start_ms: int, end_ms: int,
                                 base: str = None) -> list[list]:
        results = []
        while start_ms < end_ms:
            batch = self._get(endpoint, params={
                "symbol":    SYMBOL,
                "interval":  "1h",
                "startTime": start_ms,
                "endTime":   end_ms,
                "limit":     1500,
            }, base_override=base)
            if not batch:
                break
            results.extend(batch)
            last_open_time = int(batch[-1][0])
            logger.debug(f"{endpoint}: got {len(batch)} candles")
            start_ms = last_open_time + 3_600_000  # +1 jam
            if len(batch) < 1500:
                break
        return results

    # ── Mark Price Klines ──────────────────────────────────────────────
    def fetch_mark_price_history(self, start_ms: int = None, end_ms: int = None) -> list:
        start_ms = start_ms or self.days_ago_ms(HISTORICAL_DAYS)
        end_ms   = end_ms   or self.now_ms()
        rows = self._fetch_klines_paginated("/fapi/v1/markPriceKlines", start_ms, end_ms)
        logger.info(f"MarkPriceKline: total {len(rows)} candles fetched.")
        return rows

    def save_mark_price(self, rows: list):
        if not rows:
            return
        db = SessionLocal()
        try:
            records = [
                {
                    "symbol":    SYMBOL,
                    "open_time": int(r[0]),
                    "open":      float(r[1]),
                    "high":      float(r[2]),
                    "low":       float(r[3]),
                    "close":     float(r[4]),
                    "volume":    float(r[5]) if r[5] else None,
                    "close_time": int(r[6]) if len(r) > 6 else None,
                }
                for r in rows
            ]
            stmt = insert(MarkPriceKline).values(records)
            stmt = stmt.on_conflict_do_nothing(index_elements=["symbol", "open_time"])
            db.execute(stmt)
            db.commit()
            logger.info(f"MarkPriceKline: {len(records)} rows saved.")
        except Exception as e:
            db.rollback()
            logger.error(f"MarkPriceKline save error: {e}")
        finally:
            db.close()

    # ── Spot Klines (untuk CVD Spot) ────────────────────────────────────
    def fetch_spot_history(self, start_ms: int = None, end_ms: int = None) -> list:
        start_ms = start_ms or self.days_ago_ms(HISTORICAL_DAYS)
        end_ms   = end_ms   or self.now_ms()
        rows = self._fetch_klines_paginated("/api/v3/klines", start_ms, end_ms, base=SPOT_BASE_URL)
        logger.info(f"SpotKline: total {len(rows)} candles fetched.")
        return rows

    def save_spot(self, rows: list):
        if not rows:
            return
        db = SessionLocal()
        try:
            records = [
                {
                    "symbol":       SYMBOL,
                    "open_time":    int(r[0]),
                    "open":         float(r[1]),
                    "high":         float(r[2]),
                    "low":          float(r[3]),
                    "close":        float(r[4]),
                    "volume":       float(r[5]),
                    "taker_buy_vol": float(r[9]) if len(r) > 9 else None,
                    "close_time":   int(r[6]) if len(r) > 6 else None,
                }
                for r in rows
            ]
            stmt = insert(SpotKline).values(records)
            stmt = stmt.on_conflict_do_nothing(index_elements=["symbol", "open_time"])
            db.execute(stmt)
            db.commit()
            logger.info(f"SpotKline: {len(records)} rows saved.")
        except Exception as e:
            db.rollback()
            logger.error(f"SpotKline save error: {e}")
        finally:
            db.close()

    def run_initial(self):
        self.save_mark_price(self.fetch_mark_price_history())
        self.save_spot(self.fetch_spot_history())

    def run_update(self):
        start = self.now_ms() - 10 * 3_600_000  # 10 jam terakhir
        self.save_mark_price(self.fetch_mark_price_history(start_ms=start))
        self.save_spot(self.fetch_spot_history(start_ms=start))
