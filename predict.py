"""
Phase 4 — Live Prediction
Ambil data terbaru dari DB, jalankan ensemble, return prediksi.
"""
import json
import pandas as pd
from loguru import logger
from sqlalchemy import text

from database.connection import engine, init_db
from pipeline.feature_engineering import build_features
from models.ensemble import ensemble_predict
from config import SYMBOL


def get_latest_prediction() -> dict:
    """Ambil prediksi terbaru — gunakan 24 jam terakhir data."""
    try:
        # Load features dari DB
        with engine.connect() as conn:
            df = pd.read_sql(text(f"""
                SELECT * FROM features
                WHERE symbol = '{SYMBOL}'
                ORDER BY ts DESC
                LIMIT 100
            """), conn)

        if df.empty or len(df) < 24:
            return {"error": f"Data tidak cukup: {len(df)} rows (butuh min 24)"}

        # Sort ascending untuk LSTM sequence
        df = df.sort_values("ts").reset_index(drop=True)

        # Drop kolom non-fitur
        exclude = {"ts", "symbol", "label", "close"}
        feature_cols = [c for c in df.columns if c not in exclude]
        df_feat = df[feature_cols + ["close"]].copy()

        result = ensemble_predict(df_feat)
        result["timestamp"] = str(df["ts"].iloc[-1])
        result["data_points"] = len(df)
        return result

    except Exception as e:
        logger.error(f"Prediction error: {e}")
        return {"error": str(e)}


def save_prediction(result: dict):
    """Simpan hasil prediksi ke tabel predictions."""
    if "error" in result:
        return
    try:
        with engine.connect() as conn:
            conn.execute(text("""
                INSERT INTO predictions
                (symbol, ts, prediction, label, confidence,
                 regime, prob_turun, prob_sideways, prob_naik)
                VALUES
                (:symbol, :ts, :prediction, :label, :confidence,
                 :regime, :prob_turun, :prob_sideways, :prob_naik)
                ON CONFLICT (symbol, ts) DO NOTHING
            """), {
                "symbol":       SYMBOL,
                "ts":           result["timestamp"],
                "prediction":   result["prediction"],
                "label":        result["label"],
                "confidence":   result["confidence"],
                "regime":       result["regime"],
                "prob_turun":   result["probabilities"]["turun"],
                "prob_sideways": result["probabilities"]["sideways"],
                "prob_naik":    result["probabilities"]["naik"],
            })
            conn.commit()
    except Exception as e:
        logger.error(f"Save prediction error: {e}")


def create_predictions_table():
    """Buat tabel predictions kalau belum ada."""
    with engine.connect() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS predictions (
                id          SERIAL PRIMARY KEY,
                symbol      VARCHAR(20),
                ts          VARCHAR(50),
                prediction  VARCHAR(20),
                label       INTEGER,
                confidence  FLOAT,
                regime      VARCHAR(30),
                prob_turun  FLOAT,
                prob_sideways FLOAT,
                prob_naik   FLOAT,
                created_at  TIMESTAMP DEFAULT NOW(),
                UNIQUE(symbol, ts)
            )
        """))
        conn.commit()
    logger.info("Predictions table ready.")


def run_prediction():
    """Entry point — jalankan prediksi dan print hasilnya."""
    create_predictions_table()
    result = get_latest_prediction()
    save_prediction(result)

    print("\n" + "="*50)
    print("BTC PREDICTION RESULT")
    print("="*50)
    print(json.dumps(result, indent=2))
    print("="*50 + "\n")
    return result


if __name__ == "__main__":
    run_prediction()
