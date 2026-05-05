"""
SQLAlchemy models — satu tabel per data source.
Semua tabel pakai timestamp UTC sebagai primary key composite dengan symbol.
"""
from sqlalchemy import Column, BigInteger, Float, String, Integer, DateTime, UniqueConstraint
from sqlalchemy.sql import func
from database.connection import Base


class FundingRate(Base):
    __tablename__ = "funding_rate"
    id               = Column(Integer, primary_key=True, autoincrement=True)
    symbol           = Column(String(20), nullable=False)
    funding_time     = Column(BigInteger, nullable=False)   # epoch ms
    funding_rate     = Column(Float, nullable=False)
    mark_price       = Column(Float)
    fetched_at       = Column(DateTime, server_default=func.now())
    __table_args__   = (UniqueConstraint("symbol", "funding_time"),)


class OpenInterest(Base):
    __tablename__ = "open_interest"
    id               = Column(Integer, primary_key=True, autoincrement=True)
    symbol           = Column(String(20), nullable=False)
    timestamp        = Column(BigInteger, nullable=False)
    open_interest    = Column(Float, nullable=False)   # dalam USD
    fetched_at       = Column(DateTime, server_default=func.now())
    __table_args__   = (UniqueConstraint("symbol", "timestamp"),)


class LongShortRatio(Base):
    __tablename__ = "long_short_ratio"
    id                   = Column(Integer, primary_key=True, autoincrement=True)
    symbol               = Column(String(20), nullable=False)
    timestamp            = Column(BigInteger, nullable=False)
    ratio_type           = Column(String(30), nullable=False)  # global_account | top_account | top_position
    long_short_ratio     = Column(Float)
    long_account         = Column(Float)
    short_account        = Column(Float)
    fetched_at           = Column(DateTime, server_default=func.now())
    __table_args__       = (UniqueConstraint("symbol", "timestamp", "ratio_type"),)


class TakerVolume(Base):
    __tablename__ = "taker_volume"
    id               = Column(Integer, primary_key=True, autoincrement=True)
    symbol           = Column(String(20), nullable=False)
    timestamp        = Column(BigInteger, nullable=False)
    buy_vol          = Column(Float, nullable=False)
    sell_vol         = Column(Float, nullable=False)
    buy_sell_ratio   = Column(Float)
    fetched_at       = Column(DateTime, server_default=func.now())
    __table_args__   = (UniqueConstraint("symbol", "timestamp"),)


class Liquidation(Base):
    __tablename__ = "liquidation"
    id               = Column(Integer, primary_key=True, autoincrement=True)
    symbol           = Column(String(20), nullable=False)
    timestamp        = Column(BigInteger, nullable=False)
    side             = Column(String(5), nullable=False)   # BUY / SELL
    price            = Column(Float, nullable=False)
    qty              = Column(Float, nullable=False)
    usd_value        = Column(Float)
    fetched_at       = Column(DateTime, server_default=func.now())


class MarkPriceKline(Base):
    __tablename__ = "mark_price_kline"
    id               = Column(Integer, primary_key=True, autoincrement=True)
    symbol           = Column(String(20), nullable=False)
    open_time        = Column(BigInteger, nullable=False)
    open             = Column(Float, nullable=False)
    high             = Column(Float, nullable=False)
    low              = Column(Float, nullable=False)
    close            = Column(Float, nullable=False)
    volume           = Column(Float)
    close_time       = Column(BigInteger)
    fetched_at       = Column(DateTime, server_default=func.now())
    __table_args__   = (UniqueConstraint("symbol", "open_time"),)


class CVD(Base):
    """Cumulative Volume Delta — dihitung dari taker volume, bukan diambil langsung dari API."""
    __tablename__ = "cvd"
    id               = Column(Integer, primary_key=True, autoincrement=True)
    symbol           = Column(String(20), nullable=False)
    timestamp        = Column(BigInteger, nullable=False)
    delta            = Column(Float, nullable=False)   # buy_vol - sell_vol per candle
    cvd_cumulative   = Column(Float, nullable=False)   # running sum
    source           = Column(String(10), nullable=False)   # futures / spot
    fetched_at       = Column(DateTime, server_default=func.now())
    __table_args__   = (UniqueConstraint("symbol", "timestamp", "source"),)


class SpotKline(Base):
    """Spot kline — untuk CVD spot."""
    __tablename__ = "spot_kline"
    id               = Column(Integer, primary_key=True, autoincrement=True)
    symbol           = Column(String(20), nullable=False)
    open_time        = Column(BigInteger, nullable=False)
    open             = Column(Float, nullable=False)
    high             = Column(Float, nullable=False)
    low              = Column(Float, nullable=False)
    close            = Column(Float, nullable=False)
    volume           = Column(Float)
    taker_buy_vol    = Column(Float)   # base asset taker buy volume
    close_time       = Column(BigInteger)
    fetched_at       = Column(DateTime, server_default=func.now())
    __table_args__   = (UniqueConstraint("symbol", "open_time"),)
