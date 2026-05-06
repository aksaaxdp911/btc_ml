"""
Model 3: LSTM — sequential pattern recognition
Input : sequence 24 jam terakhir dari fitur utama
Output: probabilitas 3 kelas
"""
import os
import pickle
import numpy as np
import pandas as pd
from loguru import logger

MODEL_PATH    = "model_artifacts/lstm_model.keras"
SCALER_PATH   = "model_artifacts/lstm_scaler.pkl"
SEQ_LENGTH    = 24   # pakai 24 jam history sebagai sequence

# Fitur yang dipakai LSTM (subset — yang paling sequential)
LSTM_FEATURES = [
    "returns_1h", "returns_4h",
    "funding_rate", "funding_rate_momentum",
    "open_interest_pct1", "oi_price_divergence",
    "buy_sell_ratio", "taker_vol_imbalance",
    "cvd_delta_fut", "cvd_delta_spot",
    "liq_net", "liq_spike",
    "price_vs_vwap", "atr_pct",
    "ls_divergence_retail_top",
    "hour_sin", "hour_cos",
]


def build_sequences(X: np.ndarray, y: np.ndarray, seq_len: int):
    Xs, ys = [], []
    for i in range(seq_len, len(X)):
        Xs.append(X[i - seq_len:i])
        ys.append(y[i])
    return np.array(Xs), np.array(ys)


def train_lstm(df: pd.DataFrame):
    try:
        import tensorflow as tf
        from tensorflow.keras.models import Sequential
        from tensorflow.keras.layers import LSTM, Dense, Dropout, BatchNormalization
        from tensorflow.keras.callbacks import EarlyStopping, ReduceLROnPlateau
        from sklearn.preprocessing import StandardScaler
    except ImportError:
        logger.error("tensorflow or sklearn not installed")
        return None

    # Pakai fitur yang tersedia saja
    available = [f for f in LSTM_FEATURES if f in df.columns]
    logger.info(f"LSTM using {len(available)} features")

    X_raw = df[available].values
    y_raw = df["label"].values.astype(int)

    # Scale
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X_raw)

    # Build sequences
    X_seq, y_seq = build_sequences(X_scaled, y_raw, SEQ_LENGTH)

    # Temporal split 80/20
    split = int(len(X_seq) * 0.8)
    X_train, X_test = X_seq[:split], X_seq[split:]
    y_train, y_test = y_seq[:split], y_seq[split:]

    # One-hot encode labels
    y_train_oh = tf.keras.utils.to_categorical(y_train, 3)
    y_test_oh  = tf.keras.utils.to_categorical(y_test,  3)

    # Model architecture
    model = Sequential([
        LSTM(128, return_sequences=True, input_shape=(SEQ_LENGTH, len(available))),
        BatchNormalization(),
        Dropout(0.3),
        LSTM(64, return_sequences=False),
        BatchNormalization(),
        Dropout(0.3),
        Dense(32, activation="relu"),
        Dropout(0.2),
        Dense(3, activation="softmax"),
    ])

    model.compile(
        optimizer=tf.keras.optimizers.Adam(learning_rate=0.001),
        loss="categorical_crossentropy",
        metrics=["accuracy"],
    )

    callbacks = [
        EarlyStopping(patience=10, restore_best_weights=True, monitor="val_loss"),
        ReduceLROnPlateau(patience=5, factor=0.5, min_lr=1e-5),
    ]

    logger.info("Training LSTM...")
    history = model.fit(
        X_train, y_train_oh,
        validation_data=(X_test, y_test_oh),
        epochs=100,
        batch_size=32,
        callbacks=callbacks,
        verbose=0,
    )

    # Evaluasi
    loss, acc = model.evaluate(X_test, y_test_oh, verbose=0)
    logger.info(f"LSTM Accuracy: {acc:.4f}, Loss: {loss:.4f}")

    # Simpan
    os.makedirs("model_artifacts", exist_ok=True)
    model.save(MODEL_PATH)
    with open(SCALER_PATH, "wb") as f:
        pickle.dump((scaler, available), f)

    logger.info(f"LSTM model saved to {MODEL_PATH}")
    return model, scaler, available, acc


def load_lstm():
    try:
        from tensorflow.keras.models import load_model
        if not os.path.exists(MODEL_PATH) or not os.path.exists(SCALER_PATH):
            return None, None, None
        model = load_model(MODEL_PATH)
        with open(SCALER_PATH, "rb") as f:
            scaler, features = pickle.load(f)
        return model, scaler, features
    except Exception as e:
        logger.error(f"LSTM load error: {e}")
        return None, None, None


def predict_lstm(df_recent: pd.DataFrame) -> np.ndarray:
    """
    Input: DataFrame minimal 24 baris terakhir.
    Output: probabilitas [P(turun), P(sideways), P(naik)] untuk baris terakhir.
    """
    model, scaler, features = load_lstm()
    if model is None:
        return np.array([1/3, 1/3, 1/3])  # fallback uniform

    available = [f for f in features if f in df_recent.columns]
    X = df_recent[available].values[-SEQ_LENGTH:]
    if len(X) < SEQ_LENGTH:
        return np.array([1/3, 1/3, 1/3])

    X_scaled = scaler.transform(X)
    X_seq = X_scaled.reshape(1, SEQ_LENGTH, len(available))
    return model.predict(X_seq, verbose=0)[0]
