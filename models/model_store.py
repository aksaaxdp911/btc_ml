"""
Model Store — simpan dan load model artifacts ke/dari PostgreSQL.
Solusi untuk Railway yang tidak persist filesystem antar deployment.
"""
import pickle
import os
from loguru import logger
from sqlalchemy import text
from database.connection import engine

MODEL_DIR = "model_artifacts"


def save_model_to_db(name: str, obj: object):
    """Simpan model/scaler/feature_cols ke PostgreSQL sebagai binary."""
    data = pickle.dumps(obj)
    with engine.connect() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS model_artifacts (
                name       VARCHAR(100) PRIMARY KEY,
                data       BYTEA NOT NULL,
                updated_at TIMESTAMP DEFAULT NOW()
            )
        """))
        conn.execute(text("""
            INSERT INTO model_artifacts (name, data, updated_at)
            VALUES (:name, :data, NOW())
            ON CONFLICT (name) DO UPDATE
            SET data=:data, updated_at=NOW()
        """), {"name": name, "data": data})
        conn.commit()
    logger.info(f"Model '{name}' saved to DB ({len(data)/1024:.1f} KB)")


def load_model_from_db(name: str):
    """Load model dari PostgreSQL."""
    try:
        with engine.connect() as conn:
            result = conn.execute(
                text("SELECT data FROM model_artifacts WHERE name=:name"),
                {"name": name}
            ).fetchone()
        if result is None:
            return None
        obj = pickle.loads(result[0])
        logger.info(f"Model '{name}' loaded from DB")
        return obj
    except Exception as e:
        logger.error(f"Load model '{name}' failed: {e}")
        return None


def save_all_models():
    """Scan model_artifacts folder dan upload semua ke DB."""
    if not os.path.exists(MODEL_DIR):
        logger.warning(f"{MODEL_DIR} not found")
        return
    count = 0
    for fname in os.listdir(MODEL_DIR):
        fpath = os.path.join(MODEL_DIR, fname)
        try:
            with open(fpath, "rb") as f:
                data = f.read()
            with engine.connect() as conn:
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS model_artifacts (
                        name VARCHAR(100) PRIMARY KEY,
                        data BYTEA NOT NULL,
                        updated_at TIMESTAMP DEFAULT NOW()
                    )
                """))
                conn.execute(text("""
                    INSERT INTO model_artifacts (name, data, updated_at)
                    VALUES (:name, :data, NOW())
                    ON CONFLICT (name) DO UPDATE
                    SET data=:data, updated_at=NOW()
                """), {"name": fname, "data": data})
                conn.commit()
            count += 1
            logger.info(f"Uploaded: {fname} ({len(data)/1024:.1f} KB)")
        except Exception as e:
            logger.error(f"Failed to upload {fname}: {e}")
    logger.info(f"Total {count} model files saved to DB.")


def restore_all_models():
    """Download semua model dari DB ke filesystem lokal."""
    os.makedirs(MODEL_DIR, exist_ok=True)
    try:
        with engine.connect() as conn:
            # Cek apakah tabel ada
            exists = conn.execute(text("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables
                    WHERE table_name='model_artifacts'
                )
            """)).scalar()
            if not exists:
                logger.warning("model_artifacts table not found in DB")
                return 0
            rows = conn.execute(
                text("SELECT name, data FROM model_artifacts")
            ).fetchall()
        count = 0
        for name, data in rows:
            fpath = os.path.join(MODEL_DIR, name)
            with open(fpath, "wb") as f:
                f.write(bytes(data))
            count += 1
            logger.info(f"Restored: {name} ({len(data)/1024:.1f} KB)")
        logger.info(f"Total {count} model files restored from DB.")
        return count
    except Exception as e:
        logger.error(f"Restore failed: {e}")
        return 0
