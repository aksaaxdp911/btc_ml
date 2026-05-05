"""
Fetcher: Liquidation Orders
Endpoint: GET /fapi/v1/allForceOrders (public, tidak butuh auth)
Note: Binance hanya menyimpan 24 jam terakhir untuk liquidation publik.
      Kita fetch setiap jam dan simpan secara incremental untuk bangun history.
"""
from loguru import logger
from sqlalchemy.dialects.postgresql import insert

from fetchers.base import BinanceFetcher
from database.connection import SessionLocal
from database.models import Liquidation
from config import SYMBOL


class LiquidationFetcher(BinanceFetcher):

    def fetch_recent(self, start_ms: int = None) -> list[dict]:
        """Ambil liquidation terbaru (max 24 jam terakhir dari API)."""
        params = {"symbol": SYMBOL, "limit": 1000}
        if start_ms:
            params["startTime"] = start_ms

        rows = self._get("/fapi/v1/allForceOrders", params=params)
        logger.info(f"Liquidation: fetched {len(rows)} rows.")
        return rows

    def save(self, rows: list[dict]):
        if not rows:
            return
        db = SessionLocal()
        try:
            records = [
                {
                    "symbol":    SYMBOL,
                    "timestamp": int(r["time"]),
                    "side":      r["side"],          # BUY = short liquidated, SELL = long liquidated
                    "price":     float(r["price"]),
                    "qty":       float(r["origQty"]),
                    "usd_value": float(r["price"]) * float(r["origQty"]),
                }
                for r in rows
            ]
            stmt = insert(Liquidation).values(records)
            stmt = stmt.on_conflict_do_nothing()   # tidak ada unique constraint — duplikat manual dicegah pakai startTime
            db.execute(stmt)
            db.commit()
            logger.info(f"Liquidation: {len(records)} rows saved.")
        except Exception as e:
            db.rollback()
            logger.error(f"Liquidation save error: {e}")
        finally:
            db.close()

    def get_latest_timestamp(self) -> int | None:
        """Cari timestamp terakhir di DB supaya fetch incremental."""
        db = SessionLocal()
        try:
            result = db.query(Liquidation.timestamp)\
                       .filter(Liquidation.symbol == SYMBOL)\
                       .order_by(Liquidation.timestamp.desc())\
                       .first()
            return result[0] if result else None
        finally:
            db.close()

    def run_initial(self):
        """Ambil 24 jam terakhir (limit API)."""
        rows = self.fetch_recent()
        self.save(rows)

    def run_update(self):
        """Fetch hanya sejak record terakhir."""
        last_ts = self.get_latest_timestamp()
        start   = (last_ts + 1) if last_ts else None
        rows    = self.fetch_recent(start_ms=start)
        self.save(rows)
