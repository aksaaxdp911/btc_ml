from database.connection import engine
from sqlalchemy import text

with engine.connect() as conn:
    conn.execute(text("DROP TABLE IF EXISTS predictions"))
    conn.commit()
print("predictions table dropped OK")
