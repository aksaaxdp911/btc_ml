"""
Model 2: Hidden Markov Model — deteksi regime pasar
Regime: 0=bearish/volatile, 1=sideways/low-vol, 2=bullish/trending

Output regime dipakai sebagai fitur tambahan untuk XGBoost dan LSTM,
sehingga model tahu "konteks" kondisi pasar saat ini.
"""
import os
import pickle
import numpy as np
import pandas as pd
from loguru import logger

MODEL_PATH = "model_artifacts/hmm_model.pkl"


def build_hmm_features(df: pd.DataFrame) -> np.ndarray:
    """Buat feature matrix untuk HMM dari price data."""
    feats = pd.DataFrame(index=df.index)
    feats["returns"] = df["close"].pct_change().fillna(0)
    feats["vol"]     = feats["returns"].rolling(8).std().fillna(0)
    if "atr_pct" in df.columns:
        atr = df["atr_pct"]
        # Pastikan Series, bukan DataFrame (kalau ada duplicate columns)
        if isinstance(atr, pd.DataFrame):
            atr = atr.iloc[:, 0]
        feats["atr_pct"] = atr.fillna(0)
    else:
        feats["atr_pct"] = 0.0
    return feats.values


def train_hmm(df: pd.DataFrame):
    try:
        from hmmlearn.hmm import GaussianHMM
    except ImportError:
        logger.error("hmmlearn not installed")
        return None

    X = build_hmm_features(df)

    model = GaussianHMM(
        n_components=3,      # 3 regime: bearish, sideways, bullish
        covariance_type="full",
        n_iter=200,
        random_state=42,
    )
    model.fit(X)

    os.makedirs("model_artifacts", exist_ok=True)
    with open(MODEL_PATH, "wb") as f:
        pickle.dump(model, f)

    logger.info(f"HMM trained. Model saved to {MODEL_PATH}")
    return model


def load_hmm():
    if not os.path.exists(MODEL_PATH):
        return None
    with open(MODEL_PATH, "rb") as f:
        return pickle.load(f)


def predict_regime(df: pd.DataFrame) -> np.ndarray:
    """Return array regime (0/1/2) untuk setiap baris."""
    model = load_hmm()
    if model is None:
        logger.warning("HMM model belum ada — semua regime = 1 (default)")
        return np.ones(len(df), dtype=int)

    X = build_hmm_features(df)
    regimes = model.predict(X)

    # Normalize: pastikan regime 2 = bullish (mean return tertinggi)
    ret = df["close"].pct_change().fillna(0).values
    means = []
    for r in range(3):
        mask = regimes == r
        if mask.sum() > 0:
            means.append((r, ret[mask].mean()))
        else:
            means.append((r, 0.0))  # default jika regime kosong

    means.sort(key=lambda x: x[1])

    # Pastikan semua 3 regime ada di remap
    remap = {}
    for rank, (regime_id, _) in enumerate(means):
        remap[regime_id] = rank
    regimes = np.array([remap[r] for r in regimes])

    logger.info(f"Regime distribution: {np.unique(regimes, return_counts=True)}")
    return regimes
