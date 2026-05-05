"""
Base fetcher — semua fetcher turunan dari kelas ini.
Handle: retry otomatis, rate limit, logging, dan upsert ke DB.
"""
import time
import hashlib
import hmac
from urllib.parse import urlencode

import requests
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from loguru import logger

from config import BINANCE_API_KEY, BINANCE_API_SECRET, BINANCE_BASE_URL


class BinanceFetcher:
    BASE_URL = BINANCE_BASE_URL
    MAX_RETRIES = 5

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "X-MBX-APIKEY": BINANCE_API_KEY,
            "Content-Type": "application/json",
        })

    @retry(
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        retry=retry_if_exception_type((requests.exceptions.ConnectionError,
                                       requests.exceptions.Timeout,
                                       requests.exceptions.HTTPError)),
        reraise=True,
    )
    def _get(self, endpoint: str, params: dict = None, signed: bool = False, base_override: str = None) -> dict | list:
        url = (base_override or self.BASE_URL) + endpoint
        params = params or {}

        if signed:
            params["timestamp"] = int(time.time() * 1000)
            query = urlencode(params)
            params["signature"] = hmac.new(
                BINANCE_API_SECRET.encode(), query.encode(), hashlib.sha256
            ).hexdigest()

        resp = self.session.get(url, params=params, timeout=15)

        if resp.status_code == 429:
            retry_after = int(resp.headers.get("Retry-After", 10))
            logger.warning(f"Rate limited. Sleeping {retry_after}s...")
            time.sleep(retry_after)
            resp.raise_for_status()

        if resp.status_code == 418:  # IP banned
            logger.error("IP banned by Binance (418). Sleeping 60s...")
            time.sleep(60)
            resp.raise_for_status()

        resp.raise_for_status()
        return resp.json()

    @staticmethod
    def ms_to_epoch(dt_str: str) -> int:
        """Convert '2024-01-01' string ke epoch ms."""
        import datetime
        dt = datetime.datetime.strptime(dt_str, "%Y-%m-%d")
        return int(dt.timestamp() * 1000)

    @staticmethod
    def now_ms() -> int:
        return int(time.time() * 1000)

    @staticmethod
    def days_ago_ms(days: int) -> int:
        return int((time.time() - days * 86400) * 1000)
