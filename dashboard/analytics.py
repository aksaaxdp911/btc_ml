"""
Analytics — Regression version (dual horizon 8h & 24h)
Evaluasi prediksi vs actual return.
"""
import pandas as pd
import numpy as np
from sqlalchemy import text
from database.connection import engine
from config import SYMBOL, SIGNAL_THRESHOLD

THRESHOLD = SIGNAL_THRESHOLD * 100  # dalam %

def classify(pct):
    """Klasifikasi return aktual jadi sinyal."""
    if pct > THRESHOLD:   return "Naik"
    if pct < -THRESHOLD:  return "Turun"
    return "Sideways"

def get_analytics_data() -> dict:
    try:
        # Ambil prediksi
        preds = pd.read_sql(text(f"""
            SELECT id, created_at, horizon_h, predicted_pct, signal, direction, regime
            FROM predictions
            WHERE symbol='{SYMBOL}'
            ORDER BY created_at ASC
        """), engine.connect())

        if preds.empty:
            return {"error": "No predictions yet", "total": 0}

        # Ambil features untuk actual return
        feats = pd.read_sql(text(f"""
            SELECT ts, target_8h, target_24h, close
            FROM features
            WHERE symbol='{SYMBOL}'
            ORDER BY ts ASC
        """), engine.connect())

        if feats.empty:
            return {"error": "No features data", "total": 0}

        preds["created_at"] = pd.to_datetime(preds["created_at"], utc=True)
        feats["ts"] = pd.to_datetime(feats["ts"], utc=True)

        # Match prediksi dengan actual return
        results = []
        for _, p in preds.iterrows():
            h = int(p["horizon_h"])
            target_col = f"target_{h}h"
            if target_col not in feats.columns:
                continue

            target_time = p["created_at"] + pd.Timedelta(hours=h)
            diff = (feats["ts"] - target_time).abs()
            idx = diff.idxmin()
            if diff[idx] > pd.Timedelta(hours=2):
                continue

            actual_pct    = float(feats.loc[idx, target_col])
            actual_signal = classify(actual_pct)
            pred_signal   = classify(float(p["predicted_pct"]))
            correct       = pred_signal == actual_signal

            results.append({
                "horizon":       h,
                "predicted_pct": float(p["predicted_pct"]),
                "actual_pct":    actual_pct,
                "pred_signal":   pred_signal,
                "actual_signal": actual_signal,
                "correct":       correct,
                "regime":        p["regime"],
                "created_at":    str(p["created_at"]),
                "error_pct":     abs(float(p["predicted_pct"]) - actual_pct),
            })

        if not results:
            return {"error": "Not enough evaluated predictions yet", "total": 0}

        df = pd.DataFrame(results)
        total    = len(df)
        overall  = round(df["correct"].mean() * 100, 1)
        avg_mae  = round(df["error_pct"].mean(), 3)

        # Per horizon
        by_horizon = []
        for h in sorted(df["horizon"].unique()):
            sub = df[df["horizon"] == h]
            by_horizon.append({
                "horizon":  f"{h}h",
                "total":    len(sub),
                "correct":  int(sub["correct"].sum()),
                "accuracy": round(sub["correct"].mean() * 100, 1),
                "mae":      round(sub["error_pct"].mean(), 3),
            })

        # Per predicted signal
        by_signal = []
        for sig in ["Naik", "Sideways", "Turun"]:
            sub = df[df["pred_signal"] == sig]
            if sub.empty: continue
            by_signal.append({
                "label":    sig,
                "total":    len(sub),
                "correct":  int(sub["correct"].sum()),
                "accuracy": round(sub["correct"].mean() * 100, 1),
            })

        # Per magnitude prediksi
        bins = [(2, 999, ">2%"), (1.5, 2, "1.5–2%"), (0, 1.5, "<1.5%")]
        by_magnitude = []
        for lo, hi, label in bins:
            sub = df[df["predicted_pct"].abs().between(lo, hi)]
            if sub.empty: continue
            by_magnitude.append({
                "range":    label,
                "total":    len(sub),
                "correct":  int(sub["correct"].sum()),
                "accuracy": round(sub["correct"].mean() * 100, 1),
            })

        # Per regime
        by_regime = []
        for regime in df["regime"].dropna().unique():
            sub = df[df["regime"] == regime]
            if sub.empty: continue
            by_regime.append({
                "regime":   regime,
                "total":    len(sub),
                "correct":  int(sub["correct"].sum()),
                "accuracy": round(sub["correct"].mean() * 100, 1),
            })

        # Trend rolling accuracy
        df["rolling_acc"] = df["correct"].rolling(10, min_periods=1).mean() * 100
        trend = [{"x": i, "y": round(v, 1)} for i, v in enumerate(df["rolling_acc"])]

        # Recent predictions table
        recent = df.sort_values("created_at", ascending=False).head(20)
        recent_list = recent[[
            "created_at","horizon","predicted_pct","actual_pct",
            "pred_signal","actual_signal","correct","regime"
        ]].to_dict(orient="records")

        return {
            "total":        total,
            "overall":      overall,
            "avg_mae":      avg_mae,
            "by_horizon":   by_horizon,
            "by_signal":    by_signal,
            "by_magnitude": by_magnitude,
            "by_regime":    by_regime,
            "trend":        trend,
            "recent":       recent_list,
        }

    except Exception as e:
        return {"error": str(e), "total": 0}
