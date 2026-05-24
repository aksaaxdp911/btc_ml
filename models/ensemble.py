"""
Ensemble Regression — gabungkan XGBoost + LSTM per horizon.
Output: prediksi return % beserta interpretasi sinyal.
"""
import numpy as np
import pandas as pd
from loguru import logger

from models.xgboost_model import load_xgboost, predict_xgboost
from models.lstm_model    import predict_lstm
from models.hmm_model     import predict_regime, load_hmm
from config import PREDICTION_HORIZONS, SIGNAL_THRESHOLD

# Bobot per regime {regime: (xgb_w, lstm_w)}
REGIME_WEIGHTS = {
    0: (0.7, 0.3),  # Bearish/Volatile — XGBoost lebih stabil
    1: (0.5, 0.5),  # Sideways
    2: (0.4, 0.6),  # Bullish/Trending — LSTM lebih baik tangkap momentum
}

def interpret(ret_pct, threshold=SIGNAL_THRESHOLD*100):
    """Interpretasi angka return jadi sinyal."""
    if ret_pct > threshold:
        return "NAIK ↑", "up"
    elif ret_pct < -threshold:
        return "TURUN ↓", "down"
    else:
        return "SIDEWAYS →", "side"

def ensemble_predict(df: pd.DataFrame) -> dict:
    if len(df) < 24:
        return {"error": "Data kurang dari 24 baris"}

    # Deteksi regime
    regimes = predict_regime(df)
    current_regime = int(regimes[-1])
    regime_names = {0:"Bearish/Volatile", 1:"Sideways", 2:"Bullish/Trending"}
    xgb_w, lstm_w = REGIME_WEIGHTS.get(current_regime, (0.5, 0.5))

    # Load feature cols
    _, feature_cols = load_xgboost(PREDICTION_HORIZONS[0])

    # Cek apakah model sudah ada
    models_ready = feature_cols is not None
    if not models_ready:
        logger.warning("Model belum ada — prediksi akan 0.000%. Jalankan training dulu.")

    results = {}
    for h in PREDICTION_HORIZONS:
        # XGBoost prediction
        xgb_pred = 0.0
        if models_ready:
            avail = [c for c in feature_cols if c in df.columns]
            if avail:
                X = df[avail].iloc[[-1]].values
                xgb_pred = float(predict_xgboost(X, h)[0])
            else:
                logger.warning(f"XGBoost {h}h: tidak ada feature yang cocok di DataFrame")

        # LSTM prediction
        lstm_pred = predict_lstm(df, h)

        # Weighted ensemble
        ensemble = xgb_w * xgb_pred + lstm_w * lstm_pred

        signal, direction = interpret(ensemble)

        results[h] = {
            "horizon_h":     h,
            "predicted_pct": round(ensemble, 3),
            "signal":        signal,
            "direction":     direction,
            "xgb_pred":      round(xgb_pred, 3),
            "lstm_pred":     round(lstm_pred, 3),
        }

        logger.info(
            f"Ensemble {h}h → {ensemble:+.3f}% ({signal}) "
            f"[XGB:{xgb_pred:+.3f}% LSTM:{lstm_pred:+.3f}%]"
        )

    return {
        "horizons":      results,
        "regime":        regime_names[current_regime],
        "regime_id":     current_regime,
        "model_weights": {"xgboost": xgb_w, "lstm": lstm_w},
        "threshold_pct": SIGNAL_THRESHOLD * 100,
        "model_trained": models_ready,
    }
