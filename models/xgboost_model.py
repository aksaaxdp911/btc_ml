"""
Model 1: XGBoost — base classifier
Input : tabel features dari PostgreSQL
Output: probabilitas 3 kelas (turun/sideways/naik)
"""
import os
import pickle
import numpy as np
import pandas as pd
from loguru import logger
from sqlalchemy import text

from database.connection import engine
from config import SYMBOL

MODEL_PATH = "model_artifacts/xgboost_model.pkl"
FEATURE_PATH = "model_artifacts/feature_columns.pkl"


def load_features() -> pd.DataFrame:
    with engine.connect() as conn:
        df = pd.read_sql(text(f"SELECT * FROM features WHERE symbol = '{SYMBOL}'"), conn)
    df = df.sort_values("ts").reset_index(drop=True)
    return df


def get_feature_cols(df: pd.DataFrame) -> list[str]:
    exclude = {"ts", "symbol", "label", "close"}
    return [c for c in df.columns if c not in exclude]


def train_xgboost(df: pd.DataFrame = None):
    try:
        from xgboost import XGBClassifier
    except ImportError:
        logger.error("xgboost not installed")
        return None

    if df is None:
        df = load_features()

    if len(df) < 200:
        logger.warning(f"Not enough data to train: {len(df)} rows")
        return None

    feature_cols = get_feature_cols(df)
    X = df[feature_cols].values
    y = df["label"].values.astype(int)

    # Walk-forward split: 80% train, 20% test (temporal)
    split = int(len(X) * 0.8)
    X_train, X_test = X[:split], X[split:]
    y_train, y_test = y[:split], y[split:]

    model = XGBClassifier(
        n_estimators=300,
        max_depth=6,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        use_label_encoder=False,
        eval_metric="mlogloss",
        num_class=3,
        objective="multi:softprob",
        random_state=42,
        n_jobs=-1,
    )

    model.fit(
        X_train, y_train,
        eval_set=[(X_test, y_test)],
        verbose=False,
    )

    # Evaluasi
    from sklearn.metrics import classification_report, accuracy_score
    y_pred = model.predict(X_test)
    acc = accuracy_score(y_test, y_pred)
    report = classification_report(y_test, y_pred, target_names=["Turun", "Sideways", "Naik"])
    logger.info(f"XGBoost Accuracy: {acc:.4f}")
    logger.info(f"\n{report}")

    # Simpan model
    os.makedirs("model_artifacts", exist_ok=True)
    with open(MODEL_PATH, "wb") as f:
        pickle.dump(model, f)
    with open(FEATURE_PATH, "wb") as f:
        pickle.dump(feature_cols, f)

    logger.info(f"XGBoost model saved to {MODEL_PATH}")
    return model, feature_cols, acc


def load_xgboost():
    if not os.path.exists(MODEL_PATH):
        return None, None
    with open(MODEL_PATH, "rb") as f:
        model = pickle.load(f)
    with open(FEATURE_PATH, "rb") as f:
        feature_cols = pickle.load(f)
    return model, feature_cols


def predict_xgboost(X: np.ndarray) -> np.ndarray:
    """Return probabilitas [P(turun), P(sideways), P(naik)]."""
    model, _ = load_xgboost()
    if model is None:
        raise RuntimeError("XGBoost model belum ditraining")
    return model.predict_proba(X)
