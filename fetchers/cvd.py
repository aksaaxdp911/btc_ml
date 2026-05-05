"""
CVD (Cumulative Volume Delta) — dihitung dari data yang sudah tersimpan di DB.
Tidak memanggil API langsung, tapi memproses TakerVolume dan SpotKline.

Formula:
  delta per candle = buy_vol - sell_vol
  CVD = running cumulative sum of delta
"""
import pandas as pd
from loguru import logger
from sqlalchemy.dialects.postgresql import insert

from database.connection import SessionLocal
from database.models import TakerVolume, SpotKline, CVD
from config import SYMBOL


class CVDCalculator:

    def calculate_futures_cvd(self):
        """Hitung CVD dari futures taker volume."""
        db = SessionLocal()
        try:
            rows = db.query(TakerVolume)\
                     .filter(TakerVolume.symbol == SYMBOL)\
                     .order_by(TakerVolume.timestamp.asc())\
                     .all()
            if not rows:
                logger.warning("CVD futures: no taker volume data found.")
                return

            df = pd.DataFrame([{
                "timestamp": r.timestamp,
                "buy_vol":   r.buy_vol,
                "sell_vol":  r.sell_vol,
            } for r in rows])

            df["delta"]          = df["buy_vol"] - df["sell_vol"]
            df["cvd_cumulative"] = df["delta"].cumsum()

            records = [
                {
                    "symbol":        SYMBOL,
                    "timestamp":     int(row["timestamp"]),
                    "delta":         float(row["delta"]),
                    "cvd_cumulative": float(row["cvd_cumulative"]),
                    "source":        "futures",
                }
                for _, row in df.iterrows()
            ]

            stmt = insert(CVD).values(records)
            stmt = stmt.on_conflict_do_update(
                index_elements=["symbol", "timestamp", "source"],
                set_={"delta": stmt.excluded.delta, "cvd_cumulative": stmt.excluded.cvd_cumulative}
            )
            db.execute(stmt)
            db.commit()
            logger.info(f"CVD futures: {len(records)} rows saved.")

        except Exception as e:
            db.rollback()
            logger.error(f"CVD futures error: {e}")
        finally:
            db.close()

    def calculate_spot_cvd(self):
        """Hitung CVD dari spot kline (taker_buy_vol)."""
        db = SessionLocal()
        try:
            rows = db.query(SpotKline)\
                     .filter(SpotKline.symbol == SYMBOL)\
                     .order_by(SpotKline.open_time.asc())\
                     .all()
            if not rows:
                logger.warning("CVD spot: no spot kline data found.")
                return

            df = pd.DataFrame([{
                "timestamp":    r.open_time,
                "taker_buy":    r.taker_buy_vol or 0,
                "volume":       r.volume or 0,
            } for r in rows])

            df["sell_vol"]       = df["volume"] - df["taker_buy"]
            df["delta"]          = df["taker_buy"] - df["sell_vol"]
            df["cvd_cumulative"] = df["delta"].cumsum()

            records = [
                {
                    "symbol":        SYMBOL,
                    "timestamp":     int(row["timestamp"]),
                    "delta":         float(row["delta"]),
                    "cvd_cumulative": float(row["cvd_cumulative"]),
                    "source":        "spot",
                }
                for _, row in df.iterrows()
            ]

            stmt = insert(CVD).values(records)
            stmt = stmt.on_conflict_do_update(
                index_elements=["symbol", "timestamp", "source"],
                set_={"delta": stmt.excluded.delta, "cvd_cumulative": stmt.excluded.cvd_cumulative}
            )
            db.execute(stmt)
            db.commit()
            logger.info(f"CVD spot: {len(records)} rows saved.")

        except Exception as e:
            db.rollback()
            logger.error(f"CVD spot error: {e}")
        finally:
            db.close()

    def run(self):
        self.calculate_futures_cvd()
        self.calculate_spot_cvd()
