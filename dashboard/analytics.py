"""
Analytics endpoint — breakdown akurasi prediksi.
"""
import pandas as pd
from sqlalchemy import text
from database.connection import engine
from config import SYMBOL


def get_analytics_data() -> dict:
    try:
        # Ambil semua prediksi
        preds = pd.read_sql(text(f"""
            SELECT id, created_at, label as predicted, confidence, regime
            FROM predictions WHERE symbol='{SYMBOL}'
            ORDER BY created_at ASC
        """), engine.connect())

        if preds.empty:
            return {"error": "No predictions yet", "total": 0}

        # Ambil features untuk label aktual
        feats = pd.read_sql(text(f"""
            SELECT ts, label as actual FROM features
            WHERE symbol='{SYMBOL}' ORDER BY ts ASC
        """), engine.connect())

        if feats.empty:
            return {"error": "No features data", "total": 0}

        preds["created_at"] = pd.to_datetime(preds["created_at"], utc=True)
        feats["ts"] = pd.to_datetime(feats["ts"], utc=True)

        # Match prediksi dengan label aktual 4 jam kemudian
        results = []
        for _, p in preds.iterrows():
            target = p["created_at"] + pd.Timedelta(hours=4)
            diff = (feats["ts"] - target).abs()
            idx = diff.idxmin()
            if diff[idx] > pd.Timedelta(hours=2):
                continue
            results.append({
                "predicted":  int(p["predicted"]),
                "actual":     int(feats.loc[idx, "actual"]),
                "confidence": float(p["confidence"]),
                "regime":     p["regime"],
                "correct":    int(p["predicted"]) == int(feats.loc[idx, "actual"]),
                "created_at": str(p["created_at"]),
            })

        if not results:
            return {"error": "Not enough evaluated predictions yet", "total": 0}

        df = pd.DataFrame(results)
        total = len(df)
        overall = round(df["correct"].mean() * 100, 1)

        LABEL_MAP = {0: "Turun", 1: "Sideways", 2: "Naik"}

        # 1. Akurasi per label
        by_label = []
        for lbl in [2, 1, 0]:
            sub = df[df["predicted"] == lbl]
            if sub.empty:
                continue
            by_label.append({
                "label":    LABEL_MAP[lbl],
                "total":    len(sub),
                "correct":  int(sub["correct"].sum()),
                "accuracy": round(sub["correct"].mean() * 100, 1),
            })

        # 2. Akurasi per confidence range
        bins = [(70, 100, ">70%"), (50, 70, "50–70%"), (0, 50, "<50%")]
        by_conf = []
        for lo, hi, label in bins:
            sub = df[(df["confidence"] >= lo) & (df["confidence"] < hi)]
            if sub.empty:
                continue
            by_conf.append({
                "range":    label,
                "total":    len(sub),
                "correct":  int(sub["correct"].sum()),
                "accuracy": round(sub["correct"].mean() * 100, 1),
            })

        # 3. Akurasi per regime
        by_regime = []
        for regime in df["regime"].dropna().unique():
            sub = df[df["regime"] == regime]
            if sub.empty:
                continue
            by_regime.append({
                "regime":   regime,
                "total":    len(sub),
                "correct":  int(sub["correct"].sum()),
                "accuracy": round(sub["correct"].mean() * 100, 1),
            })

        # 4. Akurasi per jam (UTC)
        df["hour"] = pd.to_datetime(df["created_at"], utc=True).dt.hour
        by_hour = []
        for h in sorted(df["hour"].unique()):
            sub = df[df["hour"] == h]
            by_hour.append({
                "hour":     int(h),
                "label":    f"{h:02d}:00",
                "total":    len(sub),
                "correct":  int(sub["correct"].sum()),
                "accuracy": round(sub["correct"].mean() * 100, 1),
            })

        # 5. Trend akurasi (rolling 10 prediksi)
        df["rolling_acc"] = df["correct"].rolling(10, min_periods=1).mean() * 100
        trend = [{"x": i, "y": round(v, 1)} for i, v in enumerate(df["rolling_acc"])]

        return {
            "total":      total,
            "overall":    overall,
            "by_label":   by_label,
            "by_conf":    by_conf,
            "by_regime":  by_regime,
            "by_hour":    by_hour,
            "trend":      trend,
        }

    except Exception as e:
        return {"error": str(e), "total": 0}
