"""
Live Prediction — Regression + Dual Horizon
"""
import json
import pandas as pd
from loguru import logger
from sqlalchemy import text

from database.connection import engine
from models.ensemble import ensemble_predict
from config import SYMBOL, PREDICTION_HORIZONS


def create_predictions_table():
    with engine.connect() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS predictions (
                id           SERIAL PRIMARY KEY,
                symbol       VARCHAR(20),
                ts           VARCHAR(50),
                horizon_h    INTEGER,
                predicted_pct FLOAT,
                signal       VARCHAR(20),
                direction    VARCHAR(10),
                regime       VARCHAR(30),
                xgb_pred     FLOAT,
                lstm_pred    FLOAT,
                created_at   TIMESTAMP DEFAULT NOW(),
                UNIQUE(symbol, ts, horizon_h)
            )
        """))
        conn.commit()


def get_latest_prediction() -> dict:
    try:
        with engine.connect() as conn:
            df = pd.read_sql(text(f"""
                SELECT * FROM features
                WHERE symbol='{SYMBOL}'
                ORDER BY ts DESC LIMIT 100
            """), conn)

        if df.empty or len(df) < 24:
            return {"error": f"Data tidak cukup: {len(df)} rows"}

        df = df.sort_values("ts").reset_index(drop=True)
        exclude = {"ts","symbol"} | {f"target_{h}h" for h in PREDICTION_HORIZONS}
        feat_cols = [c for c in df.columns if c not in exclude]
        # Pastikan close ada tapi tidak duplikat
        if "close" not in feat_cols:
            feat_cols = feat_cols + ["close"]
        df_feat = df[feat_cols].copy()

        result = ensemble_predict(df_feat)
        result["timestamp"] = str(df["ts"].iloc[-1])
        result["current_price"] = float(df["close"].iloc[-1])
        return result

    except Exception as e:
        logger.error(f"Prediction error: {e}")
        return {"error": str(e)}


def save_prediction(result: dict):
    if "error" in result or "horizons" not in result:
        return
    try:
        with engine.connect() as conn:
            for h, hr in result["horizons"].items():
                conn.execute(text("""
                    INSERT INTO predictions
                    (symbol, ts, horizon_h, predicted_pct, signal, direction,
                     regime, xgb_pred, lstm_pred)
                    VALUES
                    (:symbol, :ts, :horizon_h, :predicted_pct, :signal, :direction,
                     :regime, :xgb_pred, :lstm_pred)
                    ON CONFLICT (symbol, ts, horizon_h) DO NOTHING
                """), {
                    "symbol":        SYMBOL,
                    "ts":            result["timestamp"],
                    "horizon_h":     int(h),
                    "predicted_pct": hr["predicted_pct"],
                    "signal":        hr["signal"],
                    "direction":     hr["direction"],
                    "regime":        result["regime"],
                    "xgb_pred":      hr["xgb_pred"],
                    "lstm_pred":     hr["lstm_pred"],
                })
            conn.commit()
        logger.info("Predictions saved.")
    except Exception as e:
        logger.error(f"Save error: {e}")


def run_prediction():
    create_predictions_table()
    result = get_latest_prediction()
    save_prediction(result)

    print("\n" + "="*50)
    if "error" in result:
        print(f"ERROR: {result['error']}")
    else:
        print(f"Regime: {result['regime']}")
        for h, hr in result["horizons"].items():
            print(f"\n{h}h Horizon:")
            print(f"  Prediksi: {hr['predicted_pct']:+.3f}%")
            print(f"  Signal:   {hr['signal']}")
            print(f"  XGBoost:  {hr['xgb_pred']:+.3f}%")
            print(f"  LSTM:     {hr['lstm_pred']:+.3f}%")
    print("="*50 + "\n")
    return result


if __name__ == "__main__":
    run_prediction()
