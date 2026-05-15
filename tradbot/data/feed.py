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


def _inverse_symbol(symbol: str) -> str | None:
    parts = symbol.split("/")
    if len(parts) == 2:
        return f"{parts[1]}/{parts[0]}"
    return None


def _invert_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    inv = df.copy()
    inv["open"] = 1.0 / df["open"]
    # high/low s'inversent : quand la paire inverse est au plus bas, la nôtre est au plus haut
    inv["high"] = 1.0 / df["low"]
    inv["low"] = 1.0 / df["high"]
    inv["close"] = 1.0 / df["close"]
    return inv


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
        try:
            raw = self._exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
            inverted = False
        except ccxt.BadSymbol:
            inv_symbol = _inverse_symbol(symbol)
            if inv_symbol is None:
                raise
            raw = self._exchange.fetch_ohlcv(inv_symbol, timeframe=timeframe, limit=limit)
            inverted = True

        df = pd.DataFrame(raw, columns=["timestamp", "open", "high", "low", "close", "volume"])
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
        df.set_index("timestamp", inplace=True)

        if inverted:
            df = _invert_ohlcv(df)

        return df
