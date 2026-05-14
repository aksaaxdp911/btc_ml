"""
Feature Engineering v3 — Regression + Dual Horizon (8h & 24h)
Label bukan lagi 0/1/2, tapi return persen aktual.
"""
import pandas as pd
import numpy as np
from loguru import logger
from sqlalchemy import text

from database.connection import engine
from config import SYMBOL, PREDICTION_HORIZONS

def load_table(query):
    with engine.connect() as conn:
        return pd.read_sql(text(query), conn)

def make_lag(df, col, lags):
    for l in lags:
        df[f"{col}_lag{l}"] = df[col].shift(l)
    return df

def make_rolling(df, col, windows):
    for w in windows:
        df[f"{col}_rmean{w}"] = df[col].rolling(w, min_periods=1).mean()
        df[f"{col}_rstd{w}"]  = df[col].rolling(w, min_periods=1).std().fillna(0)
    return df

def make_pct(df, col, periods):
    for p in periods:
        df[f"{col}_pct{p}"] = df[col].pct_change(p)
    return df

# ── Loaders ────────────────────────────────────────────────────────────────

def load_mark_price():
    df = load_table(f"""
        SELECT open_time as ts, open, high, low, close, volume
        FROM mark_price_kline WHERE symbol='{SYMBOL}' ORDER BY open_time ASC
    """)
    df["ts"] = pd.to_datetime(df["ts"], unit="ms", utc=True)
    return df.set_index("ts").sort_index()

def load_funding():
    df = load_table(f"""
        SELECT funding_time as ts, funding_rate
        FROM funding_rate WHERE symbol='{SYMBOL}' ORDER BY funding_time ASC
    """)
    if df.empty: return pd.DataFrame()
    df["ts"] = pd.to_datetime(df["ts"], unit="ms", utc=True)
    return df.set_index("ts").sort_index().resample("1h").last().ffill()

def load_oi():
    df = load_table(f"""
        SELECT timestamp as ts, open_interest
        FROM open_interest WHERE symbol='{SYMBOL}' ORDER BY timestamp ASC
    """)
    if df.empty: return pd.DataFrame()
    df["ts"] = pd.to_datetime(df["ts"], unit="ms", utc=True)
    return df.set_index("ts").sort_index().resample("1h").last().ffill()

def load_ls(ratio_type):
    df = load_table(f"""
        SELECT timestamp as ts, long_short_ratio, long_account, short_account
        FROM long_short_ratio WHERE symbol='{SYMBOL}' AND ratio_type='{ratio_type}'
        ORDER BY timestamp ASC
    """)
    if df.empty: return pd.DataFrame()
    df["ts"] = pd.to_datetime(df["ts"], unit="ms", utc=True)
    df = df.set_index("ts").sort_index()
    s = ratio_type.replace("_","")
    return df.rename(columns={
        "long_short_ratio": f"ls_{s}", "long_account": f"ls_long_{s}", "short_account": f"ls_short_{s}"
    }).resample("1h").last().ffill()

def load_taker():
    df = load_table(f"""
        SELECT timestamp as ts, buy_vol, sell_vol
        FROM taker_volume WHERE symbol='{SYMBOL}' ORDER BY timestamp ASC
    """)
    if df.empty: return pd.DataFrame()
    df["ts"] = pd.to_datetime(df["ts"], unit="ms", utc=True)
    return df.set_index("ts").sort_index().resample("1h").last().ffill()

def load_liq():
    df = load_table(f"""
        SELECT date_trunc('hour', to_timestamp(timestamp/1000)) as ts,
               SUM(CASE WHEN side='BUY' THEN usd_value ELSE 0 END) as liq_buy,
               SUM(CASE WHEN side='SELL' THEN usd_value ELSE 0 END) as liq_sell,
               COUNT(*) as liq_count
        FROM liquidation WHERE symbol='{SYMBOL}' GROUP BY 1 ORDER BY 1
    """)
    if df.empty: return pd.DataFrame()
    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    return df.set_index("ts").sort_index()

def load_cvd():
    df = load_table(f"""
        SELECT timestamp as ts, delta, cvd_cumulative, source
        FROM cvd WHERE symbol='{SYMBOL}' ORDER BY timestamp ASC
    """)
    if df.empty: return pd.DataFrame()
    df["ts"] = pd.to_datetime(df["ts"], unit="ms", utc=True)
    fut = df[df["source"]=="futures"].set_index("ts").sort_index()\
            .rename(columns={"delta":"cvd_delta_fut","cvd_cumulative":"cvd_cum_fut"})\
            .drop(columns=["source"]).resample("1h").last().ffill()
    spt = df[df["source"]=="spot"].set_index("ts").sort_index()\
            .rename(columns={"delta":"cvd_delta_spot","cvd_cumulative":"cvd_cum_spot"})\
            .drop(columns=["source"]).resample("1h").last().ffill()
    return fut.join(spt, how="outer")

# ── Build ──────────────────────────────────────────────────────────────────

def build_features():
    logger.info("Loading data...")
    price = load_mark_price()
    logger.info(f"Price: {len(price)} rows")

    df = price.copy()
    for name, src in [
        ("funding", load_funding()),
        ("oi", load_oi()),
        ("ls_ga", load_ls("global_account")),
        ("ls_ta", load_ls("top_account")),
        ("ls_tp", load_ls("top_position")),
        ("taker", load_taker()),
        ("liq", load_liq()),
        ("cvd", load_cvd()),
    ]:
        if not isinstance(src, pd.DataFrame) or src.empty:
            logger.warning(f"{name}: empty, skip")
            continue
        df = df.join(src, how="left")
        logger.info(f"Joined {name}: {len(src)} rows")

    df = df.ffill().bfill()

    # ── Price features ──────────────────────────────────────────────────
    for h in [1, 4, 8, 12, 24]:
        df[f"ret_{h}h"] = df["close"].pct_change(h)

    df["tr"] = np.maximum(
        df["high"] - df["low"],
        np.maximum(abs(df["high"] - df["close"].shift(1)),
                   abs(df["low"]  - df["close"].shift(1)))
    )
    df["atr14"]  = df["tr"].rolling(14, min_periods=1).mean()
    df["atr_pct"] = df["atr14"] / df["close"]
    df["vwap24"]  = (df["close"]*df["volume"]).rolling(24,min_periods=1).sum() / \
                     df["volume"].rolling(24,min_periods=1).sum()
    df["vs_vwap"] = (df["close"] - df["vwap24"]) / df["vwap24"]

    # Bollinger bands
    df["bb_mid"]   = df["close"].rolling(20,min_periods=1).mean()
    df["bb_std"]   = df["close"].rolling(20,min_periods=1).std().fillna(0)
    df["bb_upper"] = df["bb_mid"] + 2*df["bb_std"]
    df["bb_lower"] = df["bb_mid"] - 2*df["bb_std"]
    df["bb_pos"]   = (df["close"] - df["bb_lower"]) / (df["bb_upper"] - df["bb_lower"] + 1e-9)

    # RSI
    delta = df["close"].diff()
    gain  = delta.clip(lower=0).rolling(14,min_periods=1).mean()
    loss  = (-delta.clip(upper=0)).rolling(14,min_periods=1).mean()
    df["rsi14"] = 100 - (100 / (1 + gain / (loss + 1e-9)))

    # ── Funding features ────────────────────────────────────────────────
    if "funding_rate" in df.columns:
        df = make_lag(df, "funding_rate", [1,4,8,16,24])
        df = make_rolling(df, "funding_rate", [8,24,72])
        df["fr_momentum"] = df["funding_rate"] - df["funding_rate_lag8"]
        df["fr_extreme"]  = (df["funding_rate"].abs() > 0.001).astype(int)
        df["fr_sign"]     = np.sign(df["funding_rate"])

    # ── OI features ─────────────────────────────────────────────────────
    if "open_interest" in df.columns:
        df = make_pct(df, "open_interest", [1,4,8,24])
        df = make_rolling(df, "open_interest", [8,24])
        df["oi_price_div"] = df.get("open_interest_pct1", 0) - df["ret_1h"]

    # ── L/S features ────────────────────────────────────────────────────
    for col in [c for c in df.columns if c.startswith("ls_") and "ratio" not in c and "long" not in c and "short" not in c]:
        df = make_lag(df, col, [1,4,8])
        df = make_rolling(df, col, [8,24])

    ls_ga = "ls_globalaccount"
    ls_ta = "ls_topaccount"
    ls_tp = "ls_topposition"
    if ls_ga in df.columns and ls_ta in df.columns:
        df["ls_div_retail_top"] = df[ls_ga] - df[ls_ta]
    if ls_ta in df.columns and ls_tp in df.columns:
        df["ls_div_acct_pos"]   = df[ls_ta] - df[ls_tp]

    # ── Taker features ───────────────────────────────────────────────────
    if "buy_vol" in df.columns:
        df["taker_ratio"]     = df["buy_vol"] / (df["sell_vol"] + 1e-9)
        df["taker_imbalance"] = (df["buy_vol"]-df["sell_vol"]) / (df["buy_vol"]+df["sell_vol"]+1e-9)
        df = make_lag(df, "taker_ratio", [1,4,8])
        df = make_rolling(df, "taker_ratio", [8,24])

    # ── Liquidation features ─────────────────────────────────────────────
    for col in ["liq_buy","liq_sell","liq_count"]:
        if col not in df.columns:
            df[col] = 0
    df["liq_buy"]   = df["liq_buy"].fillna(0)
    df["liq_sell"]  = df["liq_sell"].fillna(0)
    df["liq_count"] = df["liq_count"].fillna(0)
    df["liq_net"]   = df["liq_buy"] - df["liq_sell"]
    df["liq_total"] = df["liq_buy"] + df["liq_sell"]
    df["liq_roll4"]  = df["liq_total"].rolling(4,min_periods=1).sum()
    df["liq_roll8"]  = df["liq_total"].rolling(8,min_periods=1).sum()
    df["liq_spike"]  = (df["liq_total"] > df["liq_total"].rolling(24,min_periods=1).mean()*2).astype(int)

    # ── CVD features ─────────────────────────────────────────────────────
    for col in ["cvd_delta_fut","cvd_delta_spot"]:
        if col in df.columns:
            df = make_lag(df, col, [1,4])
            df = make_rolling(df, col, [8,24])
    if "cvd_cum_fut" in df.columns and "cvd_cum_spot" in df.columns:
        df["cvd_div"] = df["cvd_cum_fut"] - df["cvd_cum_spot"]

    # ── Time features ────────────────────────────────────────────────────
    df["hour_sin"] = np.sin(2*np.pi*df.index.hour/24)
    df["hour_cos"] = np.cos(2*np.pi*df.index.hour/24)
    df["dow_sin"]  = np.sin(2*np.pi*df.index.dayofweek/7)
    df["dow_cos"]  = np.cos(2*np.pi*df.index.dayofweek/7)
    df["is_weekend"] = (df.index.dayofweek >= 5).astype(int)

    # ── Target Labels — REGRESSION ───────────────────────────────────────
    # Dua horizon: return aktual dalam % (bukan kategori)
    for h in PREDICTION_HORIZONS:
        df[f"target_{h}h"] = (df["close"].shift(-h) / df["close"] - 1) * 100

    # Drop raw kolom
    df = df.drop(columns=[c for c in ["open","high","low","volume","tr","bb_std"] if c in df.columns])

    # Drop baris dengan NaN di kolom critical
    critical = ["close","ret_1h","ret_4h"] + [f"target_{h}h" for h in PREDICTION_HORIZONS]
    before = len(df)
    df = df.dropna(subset=critical)
    df = df.fillna(0)
    logger.info(f"Dropped {before-len(df)} rows. Final: {len(df)} rows, {len(df.columns)} cols")
    return df

def save_features(df):
    df_save = df.reset_index()
    df_save.columns = [c.lower().replace(" ","_") for c in df_save.columns]
    df_save["symbol"] = SYMBOL
    df_save["ts"] = df_save["ts"].astype(str)
    df_save.to_sql("features", engine, if_exists="replace", index=False, method="multi", chunksize=500)
    logger.info(f"Features saved: {len(df_save)} rows, {len(df_save.columns)} cols")

def run_feature_engineering():
    logger.info("="*60)
    logger.info("PHASE 2 v3 — Feature Engineering (Regression + Dual Horizon)")
    logger.info("="*60)
    df = build_features()

    for h in PREDICTION_HORIZONS:
        col = f"target_{h}h"
        logger.info(f"Target {h}h — mean: {df[col].mean():.3f}%, std: {df[col].std():.3f}%, range: [{df[col].min():.2f}%, {df[col].max():.2f}%]")

    save_features(df)
    logger.info("Phase 2 selesai.")
    return df

if __name__ == "__main__":
    run_feature_engineering()
