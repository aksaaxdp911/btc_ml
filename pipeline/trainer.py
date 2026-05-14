"""
Trainer — regression, dual horizon.
"""
from loguru import logger
from models.xgboost_model import train_xgboost, load_features
from models.hmm_model     import train_hmm
from models.lstm_model    import train_lstm


def run_training():
    logger.info("="*60)
    logger.info("PHASE 3 — Regression Training (8h + 24h)")
    logger.info("="*60)

    df = load_features()
    logger.info(f"Loaded {len(df)} rows")

    if len(df) < 500:
        logger.warning(f"Data kurang ({len(df)} rows). Butuh min 500.")
        return

    logger.info("▶ Training HMM...")
    try:
        train_hmm(df)
        logger.info("✓ HMM done")
    except Exception as e:
        logger.error(f"✗ HMM: {e}")

    logger.info("▶ Training XGBoost (8h + 24h)...")
    try:
        r = train_xgboost(df)
        if r:
            for h, m in r.items():
                logger.info(f"  ✓ XGB {h}h — MAE:{m['mae']:.3f}% R²:{m['r2']:.4f}")
    except Exception as e:
        logger.error(f"✗ XGBoost: {e}")

    logger.info("▶ Training LSTM (8h + 24h)...")
    try:
        r = train_lstm(df)
        if r:
            for h, m in r.items():
                logger.info(f"  ✓ LSTM {h}h — MAE:{m['mae']:.3f}% R²:{m['r2']:.4f}")
    except Exception as e:
        logger.error(f"✗ LSTM: {e}")

    logger.info("Training selesai. Semua model siap.")


if __name__ == "__main__":
    run_training()
