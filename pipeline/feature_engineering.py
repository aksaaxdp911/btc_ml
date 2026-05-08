"""
Phase 2 — Feature Engineering
Ambil semua raw data dari PostgreSQL, buat fitur ML, simpan ke tabel features.
"""
import pandas as pd
import numpy as np
from loguru import logger
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert

from database.connection import SessionLocal, engine
from database.models import Base
from config import SYMBOL, PREDICTION_HORIZON, PREDICTION_THRESHOLD


# ── Helper ─────────────────────────────────────────────────────────────────

def load_table(query: str) -> pd.DataFrame:
    with engine.connect() as conn:
        df = pd.read_sql(text(query), conn)
    return df


def make_lag_features(df: pd.DataFrame, col: str, lags: list[int]) -> pd.DataFrame:
    for lag in lags:
        df[f"{col}_lag{lag}"] = df[col].shift(lag)
    return df


def make_rolling_features(df: pd.DataFrame, col: str, windows: list[int]) -> pd.DataFrame:
    for w in windows:
        df[f"{col}_roll_mean{w}"] = df[col].rolling(w).mean()
        df[f"{col}_roll_std{w}"]  = df[col].rolling(w).std()
    return df


def make_pct_change(df: pd.DataFrame, col: str, periods: list[int]) -> pd.DataFrame:
    for p in periods:
        df[f"{col}_pct{p}"] = df[col].pct_change(p)
    return df


# ── Load raw data ───────────────────────────────────────────────────────────

def load_mark_price() -> pd.DataFrame:
    df = load_table(f"""
        SELECT open_time as ts, open, high, low, close, volume
        FROM mark_price_kline
        WHERE symbol = '{SYMBOL}'
        ORDER BY open_time ASC
    """)
    df["ts"] = pd.to_datetime(df["ts"], unit="ms", utc=True)
    df = df.set_index("ts").sort_index()
    return df


def load_funding_rate() -> pd.DataFrame:
    df = load_table(f"""
        SELECT funding_time as ts, funding_rate
        FROM funding_rate
        WHERE symbol = '{SYMBOL}'
        ORDER BY funding_time ASC
    """)
    df["ts"] = pd.to_datetime(df["ts"], unit="ms", utc=True)
    df = df.set_index("ts").sort_index()
    # Funding rate update tiap 8 jam — resample ke 1H dengan forward fill
    df = df.resample("1h").last().ffill()
    return df


def load_open_interest() -> pd.DataFrame:
    df = load_table(f"""
        SELECT timestamp as ts, open_interest
        FROM open_interest
        WHERE symbol = '{SYMBOL}'
        ORDER BY timestamp ASC
    """)
    df["ts"] = pd.to_datetime(df["ts"], unit="ms", utc=True)
    df = df.set_index("ts").sort_index()
    df = df.resample("1h").last().ffill()
    return df


def load_long_short(ratio_type: str) -> pd.DataFrame:
    df = load_table(f"""
        SELECT timestamp as ts, long_short_ratio, long_account, short_account
        FROM long_short_ratio
        WHERE symbol = '{SYMBOL}' AND ratio_type = '{ratio_type}'
        ORDER BY timestamp ASC
    """)
    df["ts"] = pd.to_datetime(df["ts"], unit="ms", utc=True)
    df = df.set_index("ts").sort_index()
    suffix = ratio_type.replace("_", "")
    df = df.rename(columns={
        "long_short_ratio": f"ls_ratio_{suffix}",
        "long_account":     f"ls_long_{suffix}",
        "short_account":    f"ls_short_{suffix}",
    })
    df = df.resample("1h").last().ffill()
    return df


def load_taker_volume() -> pd.DataFrame:
    df = load_table(f"""
        SELECT timestamp as ts, buy_vol, sell_vol, buy_sell_ratio
        FROM taker_volume
        WHERE symbol = '{SYMBOL}'
        ORDER BY timestamp ASC
    """)
    df["ts"] = pd.to_datetime(df["ts"], unit="ms", utc=True)
    df = df.set_index("ts").sort_index()
    df = df.resample("1h").last().ffill()
    return df


def load_liquidations() -> pd.DataFrame:
    df = load_table(f"""
        SELECT
            date_trunc('hour', to_timestamp(timestamp/1000)) as ts,
            SUM(CASE WHEN side = 'BUY'  THEN usd_value ELSE 0 END) as liq_buy_usd,
            SUM(CASE WHEN side = 'SELL' THEN usd_value ELSE 0 END) as liq_sell_usd,
            COUNT(*) as liq_count
        FROM liquidation
        WHERE symbol = '{SYMBOL}'
        GROUP BY 1
        ORDER BY 1 ASC
    """)
    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    df = df.set_index("ts").sort_index()
    return df


def load_cvd() -> pd.DataFrame:
    df = load_table(f"""
        SELECT timestamp as ts, delta, cvd_cumulative, source
        FROM cvd
        WHERE symbol = '{SYMBOL}'
        ORDER BY timestamp ASC
    """)
    df["ts"] = pd.to_datetime(df["ts"], unit="ms", utc=True)
    futures = df[df["source"] == "futures"].set_index("ts").sort_index()\
                .rename(columns={"delta": "cvd_delta_fut", "cvd_cumulative": "cvd_cum_fut"})\
                .drop(columns=["source"]).resample("1h").last().ffill()
    spot    = df[df["source"] == "spot"].set_index("ts").sort_index()\
                .rename(columns={"delta": "cvd_delta_spot", "cvd_cumulative": "cvd_cum_spot"})\
                .drop(columns=["source"]).resample("1h").last().ffill()
    return futures.join(spot, how="outer")


# ── Feature Construction ────────────────────────────────────────────────────

def build_features() -> pd.DataFrame:
    logger.info("Loading raw data...")
    price = load_mark_price()
    fr    = load_funding_rate()
    oi    = load_open_interest()
    ls_ga = load_long_short("global_account")
    ls_ta = load_long_short("top_account")
    ls_tp = load_long_short("top_position")
    tv    = load_taker_volume()
    liq   = load_liquidations()
    cvd   = load_cvd()

    logger.info("Merging data sources...")
    df = price.copy()
    for src in [fr, oi, ls_ga, ls_ta, ls_tp, tv, liq, cvd]:
        df = df.join(src, how="left")

    df = df.ffill().bfill()

    logger.info("Engineering features...")

    # ── 1. Price features ──────────────────────────────────────────────
    df["returns_1h"]  = df["close"].pct_change(1)
    df["returns_4h"]  = df["close"].pct_change(4)
    df["returns_8h"]  = df["close"].pct_change(8)
    df["returns_24h"] = df["close"].pct_change(24)

    # ATR (Average True Range) — proxy volatilitas
    df["tr"] = np.maximum(
        df["high"] - df["low"],
        np.maximum(
            abs(df["high"] - df["close"].shift(1)),
            abs(df["low"]  - df["close"].shift(1))
        )
    )
    df["atr_14"] = df["tr"].rolling(14).mean()
    df["atr_pct"] = df["atr_14"] / df["close"]   # normalize

    # VWAP (rolling 24h)
    df["vwap_24h"] = (df["close"] * df["volume"]).rolling(24).sum() / df["volume"].rolling(24).sum()
    df["price_vs_vwap"] = (df["close"] - df["vwap_24h"]) / df["vwap_24h"]

    # ── 2. Funding Rate features ───────────────────────────────────────
    df = make_lag_features(df, "funding_rate", [1, 4, 8, 16, 24])
    df = make_rolling_features(df, "funding_rate", [8, 24, 72])
    df["funding_rate_momentum"] = df["funding_rate"] - df["funding_rate_lag8"]
    df["funding_rate_extreme"]  = (df["funding_rate"].abs() > 0.001).astype(int)

    # ── 3. Open Interest features ──────────────────────────────────────
    df = make_pct_change(df, "open_interest", [1, 4, 8, 24])
    df = make_rolling_features(df, "open_interest", [8, 24])
    df["oi_price_divergence"] = df["open_interest_pct1"] - df["returns_1h"]

    # ── 4. Long/Short Ratio features ──────────────────────────────────
    for col in ["ls_ratio_globalaccount", "ls_ratio_topaccount", "ls_ratio_topposition"]:
        if col in df.columns:
            df = make_lag_features(df, col, [1, 4, 8])
            df = make_rolling_features(df, col, [8, 24])

    # Divergence: retail vs top trader
    if "ls_ratio_globalaccount" in df.columns and "ls_ratio_topaccount" in df.columns:
        df["ls_divergence_retail_top"] = df["ls_ratio_globalaccount"] - df["ls_ratio_topaccount"]

    if "ls_ratio_topaccount" in df.columns and "ls_ratio_topposition" in df.columns:
        df["ls_divergence_acct_pos"] = df["ls_ratio_topaccount"] - df["ls_ratio_topposition"]

    # ── 5. Taker Volume features ───────────────────────────────────────
    df["buy_sell_ratio"] = df["buy_sell_ratio"].fillna(df["buy_vol"] / (df["sell_vol"] + 1e-9))
    df = make_lag_features(df, "buy_sell_ratio", [1, 4, 8])
    df = make_rolling_features(df, "buy_sell_ratio", [8, 24])
    df["taker_vol_total"]    = df["buy_vol"] + df["sell_vol"]
    df["taker_vol_imbalance"] = (df["buy_vol"] - df["sell_vol"]) / (df["taker_vol_total"] + 1e-9)

    # ── 6. Liquidation features ────────────────────────────────────────
    df["liq_buy_usd"]  = df["liq_buy_usd"].fillna(0)
    df["liq_sell_usd"] = df["liq_sell_usd"].fillna(0)
    df["liq_count"]    = df["liq_count"].fillna(0)
    df["liq_net"]      = df["liq_buy_usd"] - df["liq_sell_usd"]
    df["liq_total"]    = df["liq_buy_usd"] + df["liq_sell_usd"]
    df["liq_roll4h"]   = df["liq_total"].rolling(4).sum()
    df["liq_roll8h"]   = df["liq_total"].rolling(8).sum()

    # Spike detector — liquidation > 2x rolling mean
    liq_mean = df["liq_total"].rolling(24).mean()
    df["liq_spike"] = (df["liq_total"] > liq_mean * 2).astype(int)

    # ── 7. CVD features ────────────────────────────────────────────────
    for col in ["cvd_delta_fut", "cvd_delta_spot"]:
        if col in df.columns:
            df = make_lag_features(df, col, [1, 4])
            df = make_rolling_features(df, col, [8, 24])

    if "cvd_cum_fut" in df.columns and "cvd_cum_spot" in df.columns:
        df["cvd_fut_spot_divergence"] = df["cvd_cum_fut"] - df["cvd_cum_spot"]

    # ── 8. Time features ───────────────────────────────────────────────
    df["hour_of_day"]   = df.index.hour
    df["day_of_week"]   = df.index.dayofweek
    df["is_weekend"]    = (df.index.dayofweek >= 5).astype(int)
    # Encode hour cyclically
    df["hour_sin"]      = np.sin(2 * np.pi * df["hour_of_day"] / 24)
    df["hour_cos"]      = np.cos(2 * np.pi * df["hour_of_day"] / 24)
    df["dow_sin"]       = np.sin(2 * np.pi * df["day_of_week"] / 7)
    df["dow_cos"]       = np.cos(2 * np.pi * df["day_of_week"] / 7)

    # ── 9. Target Label ────────────────────────────────────────────────
    future_return = df["close"].shift(-PREDICTION_HORIZON) / df["close"] - 1

    df["label"] = 1  # default: sideways
    df.loc[future_return >  PREDICTION_THRESHOLD, "label"] = 2   # naik
    df.loc[future_return < -PREDICTION_THRESHOLD, "label"] = 0   # turun

    # Drop kolom raw yang tidak dipakai model
    drop_cols = ["open", "high", "low", "volume", "tr"]
    df = df.drop(columns=[c for c in drop_cols if c in df.columns])

    # Drop baris yang masih ada NaN setelah engineering
    before = len(df)
    df = df.dropna()
    logger.info(f"Dropped {before - len(df)} rows with NaN. Remaining: {len(df)}")

    return df


# ── Save to PostgreSQL ──────────────────────────────────────────────────────

def save_features(df: pd.DataFrame):
    df_save = df.reset_index()
    df_save.columns = [c.lower().replace(" ", "_") for c in df_save.columns]
    df_save["symbol"] = SYMBOL
    df_save["ts"] = df_save["ts"].astype(str)

    df_save.to_sql(
        "features",
        engine,
        if_exists="replace",   # replace setiap kali feature engineering dijalankan ulang
        index=False,
        method="multi",
        chunksize=500,
    )
    logger.info(f"Features saved: {len(df_save)} rows, {len(df_save.columns)} columns.")


def run_feature_engineering():
    logger.info("=" * 60)
    logger.info("PHASE 2 — Feature Engineering")
    logger.info("=" * 60)
    df = build_features()

    # Log distribusi label
    label_counts = df["label"].value_counts().sort_index()
    logger.info(f"Label distribution:\n  0=Turun: {label_counts.get(0,0)}\n  1=Sideways: {label_counts.get(1,0)}\n  2=Naik: {label_counts.get(2,0)}")

    save_features(df)
    logger.info("Phase 2 selesai.")
    return df


if __name__ == "__main__":
    run_feature_engineering()
