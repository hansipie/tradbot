from dataclasses import dataclass
from typing import Protocol
import pandas as pd
import ccxt


@dataclass
class OHLCV:
    timestamp: pd.Timestamp
    open: float
    high: float
    low: float
    close: float
    volume: float


class DataFeed(Protocol):
    def fetch_ohlcv(self, symbol: str, timeframe: str, limit: int) -> pd.DataFrame: ...


class CcxtFeed:
    def __init__(self, exchange_id: str, api_key: str = "", api_secret: str = "", sandbox: bool = True):
        exchange_class = getattr(ccxt, exchange_id)
        self._exchange: ccxt.Exchange = exchange_class({
            "apiKey": api_key,
            "secret": api_secret,
            "enableRateLimit": True,
        })
        if sandbox and self._exchange.has.get("sandbox"):
            self._exchange.set_sandbox_mode(True)

    def fetch_ohlcv(self, symbol: str, timeframe: str = "1h", limit: int = 500) -> pd.DataFrame:
        raw = self._exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
        df = pd.DataFrame(raw, columns=["timestamp", "open", "high", "low", "close", "volume"])
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
        df.set_index("timestamp", inplace=True)
        return df
