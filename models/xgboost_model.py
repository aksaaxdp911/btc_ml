"""
XGBoost Regression — prediksi return % untuk 2 horizon (8h & 24h)
"""
import os, pickle
import numpy as np
import pandas as pd
from loguru import logger
from sqlalchemy import text
from database.connection import engine
from config import SYMBOL, PREDICTION_HORIZONS

MODEL_DIR   = "model_artifacts"
FEAT_PATH   = f"{MODEL_DIR}/feature_cols.pkl"

def model_path(h): return f"{MODEL_DIR}/xgb_{h}h.pkl"

def load_features():
    with engine.connect() as conn:
        df = pd.read_sql(text(f"SELECT * FROM features WHERE symbol='{SYMBOL}'"), conn)
    return df.sort_values("ts").reset_index(drop=True)

def get_feature_cols(df):
    exclude = {"ts","symbol","close"} | {f"target_{h}h" for h in PREDICTION_HORIZONS}
    return [c for c in df.columns if c not in exclude]

def train_xgboost(df=None):
    try:
        from xgboost import XGBRegressor
        from sklearn.metrics import mean_absolute_error, r2_score
    except ImportError:
        logger.error("xgboost/sklearn not installed")
        return None

    if df is None:
        df = load_features()
    if len(df) < 200:
        logger.warning(f"Not enough data: {len(df)} rows")
        return None

    feature_cols = get_feature_cols(df)
    X = df[feature_cols].values
    os.makedirs(MODEL_DIR, exist_ok=True)

    results = {}
    for h in PREDICTION_HORIZONS:
        target = f"target_{h}h"
        if target not in df.columns:
            continue
        y = df[target].values

        # Temporal split 80/20
        split   = int(len(X)*0.8)
        X_train, X_test = X[:split], X[split:]
        y_train, y_test = y[:split], y[split:]

        model = XGBRegressor(
            n_estimators=400,
            max_depth=6,
            learning_rate=0.04,
            subsample=0.8,
            colsample_bytree=0.8,
            random_state=42,
            n_jobs=-1,
            objective="reg:squarederror",
        )
        model.fit(X_train, y_train,
                  eval_set=[(X_test, y_test)],
                  verbose=False)

        y_pred = model.predict(X_test)
        mae  = mean_absolute_error(y_test, y_pred)
        r2   = r2_score(y_test, y_pred)
        logger.info(f"XGBoost {h}h — MAE: {mae:.3f}%, R²: {r2:.4f}")

        with open(model_path(h), "wb") as f:
            pickle.dump(model, f)
        results[h] = {"mae": mae, "r2": r2}

    with open(FEAT_PATH, "wb") as f:
        pickle.dump(feature_cols, f)

    logger.info(f"XGBoost models saved.")
    return results

def load_xgboost(h):
    p = model_path(h)
    if not os.path.exists(p) or not os.path.exists(FEAT_PATH):
        return None, None
    with open(p,"rb") as f: model = pickle.load(f)
    with open(FEAT_PATH,"rb") as f: cols = pickle.load(f)
    return model, cols

def predict_xgboost(X, h):
    """Return prediksi return % untuk horizon h."""
    model, _ = load_xgboost(h)
    if model is None:
        return np.array([0.0])
    return model.predict(X)
