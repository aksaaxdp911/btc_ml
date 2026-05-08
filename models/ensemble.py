"""
Ensemble — gabungkan XGBoost + LSTM + HMM regime
Strategi: weighted average probabilitas dari XGBoost dan LSTM,
          dengan bobot yang disesuaikan berdasarkan regime HMM.
"""
import numpy as np
import pandas as pd
from loguru import logger

from models.xgboost_model import predict_xgboost, load_xgboost
from models.lstm_model    import predict_lstm, load_lstm
from models.hmm_model     import predict_regime, load_hmm


# Bobot default per regime
# Format: {regime: (xgb_weight, lstm_weight)}
REGIME_WEIGHTS = {
    0: (0.7, 0.3),   # bearish/volatile — XGBoost lebih andal
    1: (0.5, 0.5),   # sideways — 50/50
    2: (0.4, 0.6),   # bullish/trending — LSTM lebih andal (pola sequential)
}

LABEL_MAP = {0: "TURUN ↓", 1: "SIDEWAYS →", 2: "NAIK ↑"}


def ensemble_predict(df: pd.DataFrame) -> dict:
    """
    Input : DataFrame features (minimal 24 baris, baris terakhir = prediksi)
    Output: dict hasil prediksi lengkap
    """
    if len(df) < 24:
        return {"error": "Data kurang dari 24 baris"}

    # 1. Deteksi regime pasar (HMM)
    regimes = predict_regime(df)
    current_regime = int(regimes[-1])
    regime_names = {0: "Bearish/Volatile", 1: "Sideways", 2: "Bullish/Trending"}
    logger.info(f"Current regime: {current_regime} ({regime_names[current_regime]})")

    # 2. XGBoost prediction
    xgb_model, feature_cols = load_xgboost()
    xgb_proba = np.array([1/3, 1/3, 1/3])  # fallback
    if xgb_model is not None:
        available_cols = [c for c in feature_cols if c in df.columns]
        X_xgb = df[available_cols].iloc[[-1]].values
        xgb_proba = xgb_model.predict_proba(X_xgb)[0]
        logger.info(f"XGBoost: Turun={xgb_proba[0]:.3f} Sideways={xgb_proba[1]:.3f} Naik={xgb_proba[2]:.3f}")

    # 3. LSTM prediction
    lstm_proba = predict_lstm(df)
    logger.info(f"LSTM:    Turun={lstm_proba[0]:.3f} Sideways={lstm_proba[1]:.3f} Naik={lstm_proba[2]:.3f}")

    # 4. Weighted ensemble berdasarkan regime
    xgb_w, lstm_w = REGIME_WEIGHTS.get(current_regime, (0.6, 0.4))
    ensemble_proba = xgb_w * xgb_proba + lstm_w * lstm_proba

    final_label = int(np.argmax(ensemble_proba))
    confidence  = float(ensemble_proba[final_label])

    result = {
        "prediction":    LABEL_MAP[final_label],
        "label":         final_label,
        "confidence":    round(confidence * 100, 1),
        "regime":        regime_names[current_regime],
        "probabilities": {
            "turun":    round(float(ensemble_proba[0]) * 100, 1),
            "sideways": round(float(ensemble_proba[1]) * 100, 1),
            "naik":     round(float(ensemble_proba[2]) * 100, 1),
        },
        "model_weights": {"xgboost": xgb_w, "lstm": lstm_w},
        "component_proba": {
            "xgboost": xgb_proba.tolist(),
            "lstm":    lstm_proba.tolist(),
        }
    }

    logger.info(f"ENSEMBLE → {result['prediction']} ({result['confidence']}% confidence)")
    return result
