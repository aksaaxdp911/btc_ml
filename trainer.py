"""
Trainer — jalankan training semua model secara berurutan.
Dipanggil manual atau dijadwalkan setelah data cukup.
"""
from loguru import logger
from models.xgboost_model import train_xgboost, load_features
from models.hmm_model     import train_hmm
from models.lstm_model    import train_lstm


def run_training():
    logger.info("=" * 60)
    logger.info("PHASE 3 — Model Training")
    logger.info("=" * 60)

    df = load_features()
    logger.info(f"Loaded {len(df)} rows of features")

    if len(df) < 500:
        logger.warning(f"Data masih sedikit ({len(df)} rows). Training ditunda.")
        logger.info("Tunggu sampai minimal 500 jam data terkumpul (~21 hari).")
        return

    # 1. Train HMM dulu (regime dipakai oleh ensemble)
    logger.info("▶ Training HMM...")
    try:
        train_hmm(df)
        logger.info("✓ HMM selesai")
    except Exception as e:
        logger.error(f"✗ HMM failed: {e}")

    # 2. Train XGBoost
    logger.info("▶ Training XGBoost...")
    try:
        result = train_xgboost(df)
        if result:
            _, _, acc = result
            logger.info(f"✓ XGBoost selesai — accuracy: {acc:.4f}")
    except Exception as e:
        logger.error(f"✗ XGBoost failed: {e}")

    # 3. Train LSTM
    logger.info("▶ Training LSTM...")
    try:
        result = train_lstm(df)
        if result:
            _, _, _, acc = result
            logger.info(f"✓ LSTM selesai — accuracy: {acc:.4f}")
    except Exception as e:
        logger.error(f"✗ LSTM failed: {e}")

    logger.info("Phase 3 selesai. Semua model siap digunakan.")


if __name__ == "__main__":
    run_training()
