"""
Phase 2 — Feature Engineering (v2)
Fix: handle missing data dari sumber yang punya history terbatas.
"""
import pandas as pd
import numpy as np
from loguru import logger
from sqlalchemy import text

from database.connection import engine
from config import SYMBOL, PREDICTION_HORIZON, PREDICTION_THRESHOLD


def load_table(query: str) -> pd.DataFrame:
    with engine.connect() as conn:
        df = pd.read_sql(text(query), conn)
    return df


def make_lag_features(df, col, lags):
    for lag in lags:
        df[f"{col}_lag{lag}"] = df[col].shift(lag)
    return df


def make_rolling_features(df, col, windows):
    for w in windows:
        df[f"{col}_roll_mean{w}"] = df[col].rolling(w, min_periods=1).mean()
        df[f"{col}_roll_std{w}"]  = df[col].rolling(w, min_periods=1).std().fillna(0)
    return df


def make_pct_change(df, col, periods):
    for p in periods:
        df[f"{col}_pct{p}"] = df[col].pct_change(p)
    return df


# ── Loaders ────────────────────────────────────────────────────────────────

def load_mark_price():
    df = load_table(f"""
        SELECT open_time as ts, open, high, low, close, volume
        FROM mark_price_kline WHERE symbol = '{SYMBOL}'
        ORDER BY open_time ASC
    """)
    df["ts"] = pd.to_datetime(df["ts"], unit="ms", utc=True)
    return df.set_index("ts").sort_index()


def load_funding_rate():
    df = load_table(f"""
        SELECT funding_time as ts, funding_rate
        FROM funding_rate WHERE symbol = '{SYMBOL}'
        ORDER BY funding_time ASC
    """)
    df["ts"] = pd.to_datetime(df["ts"], unit="ms", utc=True)
    df = df.set_index("ts").sort_index()
    return df.resample("1h").last().ffill()


def load_open_interest():
    df = load_table(f"""
        SELECT timestamp as ts, open_interest
        FROM open_interest WHERE symbol = '{SYMBOL}'
        ORDER BY timestamp ASC
    """)
    if df.empty:
        return pd.DataFrame()
    df["ts"] = pd.to_datetime(df["ts"], unit="ms", utc=True)
    df = df.set_index("ts").sort_index()
    return df.resample("1h").last().ffill()


def load_long_short(ratio_type):
    df = load_table(f"""
        SELECT timestamp as ts, long_short_ratio, long_account, short_account
        FROM long_short_ratio
        WHERE symbol = '{SYMBOL}' AND ratio_type = '{ratio_type}'
        ORDER BY timestamp ASC
    """)
    if df.empty:
        return pd.DataFrame()
    df["ts"] = pd.to_datetime(df["ts"], unit="ms", utc=True)
    df = df.set_index("ts").sort_index()
    suffix = ratio_type.replace("_", "")
    df = df.rename(columns={
        "long_short_ratio": f"ls_ratio_{suffix}",
        "long_account":     f"ls_long_{suffix}",
        "short_account":    f"ls_short_{suffix}",
    })
    return df.resample("1h").last().ffill()


def load_taker_volume():
    df = load_table(f"""
        SELECT timestamp as ts, buy_vol, sell_vol, buy_sell_ratio
        FROM taker_volume WHERE symbol = '{SYMBOL}'
        ORDER BY timestamp ASC
    """)
    if df.empty:
        return pd.DataFrame()
    df["ts"] = pd.to_datetime(df["ts"], unit="ms", utc=True)
    df = df.set_index("ts").sort_index()
    return df.resample("1h").last().ffill()


def load_liquidations():
    df = load_table(f"""
        SELECT
            date_trunc('hour', to_timestamp(timestamp/1000)) as ts,
            SUM(CASE WHEN side='BUY' THEN usd_value ELSE 0 END) as liq_buy_usd,
            SUM(CASE WHEN side='SELL' THEN usd_value ELSE 0 END) as liq_sell_usd,
            COUNT(*) as liq_count
        FROM liquidation WHERE symbol = '{SYMBOL}'
        GROUP BY 1 ORDER BY 1
    """)
    if df.empty:
        return pd.DataFrame()
    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    return df.set_index("ts").sort_index()


def load_cvd():
    df = load_table(f"""
        SELECT timestamp as ts, delta, cvd_cumulative, source
        FROM cvd WHERE symbol = '{SYMBOL}'
        ORDER BY timestamp ASC
    """)
    if df.empty:
        return pd.DataFrame()
    df["ts"] = pd.to_datetime(df["ts"], unit="ms", utc=True)
    futures = df[df["source"]=="futures"].set_index("ts").sort_index()\
                .rename(columns={"delta":"cvd_delta_fut","cvd_cumulative":"cvd_cum_fut"})\
                .drop(columns=["source"]).resample("1h").last().ffill()
    spot = df[df["source"]=="spot"].set_index("ts").sort_index()\
                .rename(columns={"delta":"cvd_delta_spot","cvd_cumulative":"cvd_cum_spot"})\
                .drop(columns=["source"]).resample("1h").last().ffill()
    return futures.join(spot, how="outer")


# ── Feature Builder ─────────────────────────────────────────────────────────

def build_features():
    logger.info("Loading raw data...")
    price = load_mark_price()
    logger.info(f"Price: {len(price)} rows ({price.index[0]} to {price.index[-1]})")

    # Mulai dari price sebagai base
    df = price.copy()

    # Join semua sumber — pakai left join supaya price jadi anchor
    sources = {
        "funding_rate": load_funding_rate(),
        "open_interest": load_open_interest(),
        "ls_global": load_long_short("global_account"),
        "ls_top_acct": load_long_short("top_account"),
        "ls_top_pos": load_long_short("top_position"),
        "taker_vol": load_taker_volume(),
        "liquidation": load_liquidations(),
        "cvd": load_cvd(),
    }

    for name, src in sources.items():
        if src.empty:
            logger.warning(f"{name}: empty, skipping")
            continue
        df = df.join(src, how="left")
        logger.info(f"Joined {name}: {len(src)} rows")

    # Forward fill + backward fill per kolom
    df = df.ffill().bfill()
    logger.info(f"After join + fill: {len(df)} rows, {len(df.columns)} cols")

    # ── Price features ──────────────────────────────────────────────────
    df["returns_1h"]  = df["close"].pct_change(1)
    df["returns_4h"]  = df["close"].pct_change(4)
    df["returns_8h"]  = df["close"].pct_change(8)
    df["returns_24h"] = df["close"].pct_change(24)

    df["tr"] = np.maximum(
        df["high"] - df["low"],
        np.maximum(abs(df["high"] - df["close"].shift(1)),
                   abs(df["low"]  - df["close"].shift(1)))
    )
    df["atr_14"]  = df["tr"].rolling(14, min_periods=1).mean()
    df["atr_pct"] = df["atr_14"] / df["close"]

    df["vwap_24h"]     = (df["close"] * df["volume"]).rolling(24, min_periods=1).sum() / \
                          df["volume"].rolling(24, min_periods=1).sum()
    df["price_vs_vwap"] = (df["close"] - df["vwap_24h"]) / df["vwap_24h"]

    # ── Funding Rate features ────────────────────────────────────────────
    if "funding_rate" in df.columns:
        df = make_lag_features(df, "funding_rate", [1, 4, 8, 24])
        df = make_rolling_features(df, "funding_rate", [8, 24])
        df["funding_rate_momentum"] = df["funding_rate"] - df["funding_rate_lag8"]
        df["funding_extreme"] = (df["funding_rate"].abs() > 0.001).astype(int)

    # ── Open Interest features ────────────────────────────────────────────
    if "open_interest" in df.columns:
        df = make_pct_change(df, "open_interest", [1, 4, 8])
        df = make_rolling_features(df, "open_interest", [8, 24])
        df["oi_price_div"] = df.get("open_interest_pct1", 0) - df["returns_1h"]

    # ── Long/Short features ───────────────────────────────────────────────
    for col in [c for c in df.columns if c.startswith("ls_ratio_")]:
        df = make_lag_features(df, col, [1, 4, 8])
        df = make_rolling_features(df, col, [8, 24])

    ls_ga = "ls_ratio_globalaccount"
    ls_ta = "ls_ratio_topaccount"
    ls_tp = "ls_ratio_topposition"
    if ls_ga in df.columns and ls_ta in df.columns:
        df["ls_div_retail_top"] = df[ls_ga] - df[ls_ta]
    if ls_ta in df.columns and ls_tp in df.columns:
        df["ls_div_acct_pos"] = df[ls_ta] - df[ls_tp]

    # ── Taker Volume features ─────────────────────────────────────────────
    if "buy_vol" in df.columns:
        df["buy_sell_ratio"]   = df["buy_vol"] / (df["sell_vol"] + 1e-9)
        df["taker_imbalance"]  = (df["buy_vol"] - df["sell_vol"]) / \
                                  (df["buy_vol"] + df["sell_vol"] + 1e-9)
        df = make_lag_features(df, "buy_sell_ratio", [1, 4, 8])
        df = make_rolling_features(df, "buy_sell_ratio", [8, 24])

    # ── Liquidation features ──────────────────────────────────────────────
    for col in ["liq_buy_usd", "liq_sell_usd", "liq_count"]:
        if col not in df.columns:
            df[col] = 0
    df["liq_buy_usd"]  = df["liq_buy_usd"].fillna(0)
    df["liq_sell_usd"] = df["liq_sell_usd"].fillna(0)
    df["liq_count"]    = df["liq_count"].fillna(0)
    df["liq_net"]      = df["liq_buy_usd"] - df["liq_sell_usd"]
    df["liq_total"]    = df["liq_buy_usd"] + df["liq_sell_usd"]
    df["liq_roll4h"]   = df["liq_total"].rolling(4, min_periods=1).sum()
    df["liq_roll8h"]   = df["liq_total"].rolling(8, min_periods=1).sum()
    liq_mean = df["liq_total"].rolling(24, min_periods=1).mean()
    df["liq_spike"]    = (df["liq_total"] > liq_mean * 2).astype(int)

    # ── CVD features ──────────────────────────────────────────────────────
    for col in ["cvd_delta_fut", "cvd_delta_spot"]:
        if col in df.columns:
            df = make_lag_features(df, col, [1, 4])
            df = make_rolling_features(df, col, [8, 24])
    if "cvd_cum_fut" in df.columns and "cvd_cum_spot" in df.columns:
        df["cvd_div_fut_spot"] = df["cvd_cum_fut"] - df["cvd_cum_spot"]

    # ── Time features ─────────────────────────────────────────────────────
    df["hour_sin"] = np.sin(2 * np.pi * df.index.hour / 24)
    df["hour_cos"] = np.cos(2 * np.pi * df.index.hour / 24)
    df["dow_sin"]  = np.sin(2 * np.pi * df.index.dayofweek / 7)
    df["dow_cos"]  = np.cos(2 * np.pi * df.index.dayofweek / 7)
    df["is_weekend"] = (df.index.dayofweek >= 5).astype(int)

    # ── Target Label ──────────────────────────────────────────────────────
    future_return = df["close"].shift(-PREDICTION_HORIZON) / df["close"] - 1
    df["label"] = 1
    df.loc[future_return >  PREDICTION_THRESHOLD, "label"] = 2
    df.loc[future_return < -PREDICTION_THRESHOLD, "label"] = 0

    # Drop kolom raw
    df = df.drop(columns=[c for c in ["open","high","low","volume","tr"] if c in df.columns])

    # Drop NaN hanya dari kolom price-based (kolom penting)
    critical_cols = ["close", "returns_1h", "returns_4h", "label"]
    before = len(df)
    df = df.dropna(subset=critical_cols)
    
    # Isi sisa NaN dengan 0
    df = df.fillna(0)
    
    logger.info(f"Dropped {before - len(df)} rows. Final: {len(df)} rows, {len(df.columns)} cols")
    return df


def save_features(df):
    df_save = df.reset_index()
    df_save.columns = [c.lower().replace(" ", "_") for c in df_save.columns]
    df_save["symbol"] = SYMBOL
    df_save["ts"] = df_save["ts"].astype(str)

    df_save.to_sql("features", engine, if_exists="replace",
                   index=False, method="multi", chunksize=500)
    logger.info(f"Features saved: {len(df_save)} rows, {len(df_save.columns)} columns.")


def run_feature_engineering():
    logger.info("=" * 60)
    logger.info("PHASE 2 — Feature Engineering v2")
    logger.info("=" * 60)
    df = build_features()

    counts = df["label"].value_counts().sort_index()
    logger.info(f"Labels: 0=Turun:{counts.get(0,0)} 1=Sideways:{counts.get(1,0)} 2=Naik:{counts.get(2,0)}")

    save_features(df)
    logger.info("Phase 2 selesai.")
    return df


if __name__ == "__main__":
    run_feature_engineering()
