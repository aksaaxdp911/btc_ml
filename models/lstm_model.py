"""
LSTM Regression — prediksi return % untuk 2 horizon (8h & 24h)
"""
import os, pickle
import numpy as np
import pandas as pd
from loguru import logger
from config import PREDICTION_HORIZONS

MODEL_DIR  = "model_artifacts"
SEQ_LEN    = 24

LSTM_FEATS = [
    "ret_1h","ret_4h","ret_8h",
    "funding_rate","fr_momentum",
    "open_interest_pct1","oi_price_div",
    "taker_ratio","taker_imbalance",
    "cvd_delta_fut","cvd_delta_spot",
    "liq_net","liq_spike",
    "vs_vwap","atr_pct","rsi14","bb_pos",
    "ls_div_retail_top",
    "hour_sin","hour_cos",
]

def model_path(h):  return f"{MODEL_DIR}/lstm_{h}h.keras"
def scaler_path(h): return f"{MODEL_DIR}/lstm_scaler_{h}h.pkl"

def build_sequences(X, y, seq_len):
    Xs, ys = [], []
    for i in range(seq_len, len(X)):
        Xs.append(X[i-seq_len:i])
        ys.append(y[i])
    return np.array(Xs), np.array(ys)

def train_lstm(df):
    try:
        import tensorflow as tf
        from tensorflow.keras.models import Sequential
        from tensorflow.keras.layers import LSTM, Dense, Dropout, BatchNormalization
        from tensorflow.keras.callbacks import EarlyStopping, ReduceLROnPlateau
        from sklearn.preprocessing import StandardScaler
        from sklearn.metrics import mean_absolute_error, r2_score
    except ImportError:
        logger.error("tensorflow/sklearn not installed")
        return None

    os.makedirs(MODEL_DIR, exist_ok=True)
    available = [f for f in LSTM_FEATS if f in df.columns]
    logger.info(f"LSTM using {len(available)} features")

    X_raw = df[available].values
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X_raw)

    results = {}
    for h in PREDICTION_HORIZONS:
        target = f"target_{h}h"
        if target not in df.columns:
            continue

        y = df[target].values
        X_seq, y_seq = build_sequences(X_scaled, y, SEQ_LEN)

        split   = int(len(X_seq)*0.8)
        X_train, X_test = X_seq[:split], X_seq[split:]
        y_train, y_test = y_seq[:split], y_seq[split:]

        model = Sequential([
            LSTM(128, return_sequences=True, input_shape=(SEQ_LEN, len(available))),
            BatchNormalization(),
            Dropout(0.3),
            LSTM(64, return_sequences=False),
            BatchNormalization(),
            Dropout(0.3),
            Dense(32, activation="relu"),
            Dropout(0.2),
            Dense(1),   # Output: satu angka (return %)
        ])

        model.compile(
            optimizer=tf.keras.optimizers.Adam(0.001),
            loss="mse",
            metrics=["mae"],
        )

        model.fit(
            X_train, y_train,
            validation_data=(X_test, y_test),
            epochs=100, batch_size=32,
            callbacks=[
                EarlyStopping(patience=10, restore_best_weights=True),
                ReduceLROnPlateau(patience=5, factor=0.5, min_lr=1e-5),
            ],
            verbose=0,
        )

        y_pred = model.predict(X_test, verbose=0).flatten()
        mae = mean_absolute_error(y_test, y_pred)
        r2  = r2_score(y_test, y_pred)
        logger.info(f"LSTM {h}h — MAE: {mae:.3f}%, R²: {r2:.4f}")

        model.save(model_path(h))
        with open(scaler_path(h), "wb") as f:
            pickle.dump((scaler, available), f)

        results[h] = {"mae": mae, "r2": r2}

    return results

def load_lstm(h):
    try:
        from tensorflow.keras.models import load_model
        if not os.path.exists(model_path(h)):
            return None, None, None
        model = load_model(model_path(h))
        with open(scaler_path(h),"rb") as f:
            scaler, features = pickle.load(f)
        return model, scaler, features
    except Exception as e:
        logger.error(f"LSTM load error: {e}")
        return None, None, None

def predict_lstm(df_recent, h):
    """Return prediksi return % untuk horizon h."""
    model, scaler, features = load_lstm(h)
    if model is None:
        return 0.0
    avail = [f for f in features if f in df_recent.columns]
    X = df_recent[avail].values[-SEQ_LEN:]
    if len(X) < SEQ_LEN:
        return 0.0
    X_scaled = scaler.transform(X).reshape(1, SEQ_LEN, len(avail))
    return float(model.predict(X_scaled, verbose=0)[0][0])
