from database.connection import engine
from sqlalchemy import text

tables = ['mark_price_kline','funding_rate','open_interest',
          'long_short_ratio','taker_volume','liquidation','cvd','spot_kline']

with engine.connect() as c:
    for t in tables:
        try:
            r = c.execute(text(f'SELECT COUNT(*) FROM {t}')).scalar()
            print(f'{t}: {r} rows')
        except Exception as e:
            print(f'{t}: ERROR - {e}')
