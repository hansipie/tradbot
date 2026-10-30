from dataclasses import dataclass
from typing import Callable, Protocol
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


def _raw_to_df(raw: list) -> pd.DataFrame:
    df = pd.DataFrame(raw, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
    df.set_index("timestamp", inplace=True)
    return df


def _cross_via_usdt(df_base: pd.DataFrame, df_quote: pd.DataFrame) -> pd.DataFrame:
    """Reconstruit A/B à partir de A/USDT et B/USDT (inner join sur les timestamps communs)."""
    a = df_base.add_suffix("_a")
    b = df_quote.add_suffix("_b")
    joined = a.join(b, how="inner")
    result = pd.DataFrame(index=joined.index)
    result["open"] = joined["open_a"] / joined["open_b"]
    result["high"] = joined["high_a"] / joined["low_b"]   # max ratio = A haut / B bas
    result["low"] = joined["low_a"] / joined["high_b"]    # min ratio = A bas / B haut
    result["close"] = joined["close_a"] / joined["close_b"]
    result["volume"] = joined["volume_a"]
    return result


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

    def _fetch_raw(self, symbol: str, timeframe: str, limit: int) -> pd.DataFrame:
        raw = self._exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
        return _raw_to_df(raw)

    def fetch_ohlcv(self, symbol: str, timeframe: str = "1h", limit: int = 500) -> pd.DataFrame:
        return _resolve(symbol, lambda s: self._fetch_raw(s, timeframe, limit))

    def _paginate(self, symbol: str, timeframe: str, since_ms: int, until_ms: int) -> pd.DataFrame:
        """Bougies de `symbol` entre since_ms et until_ms, par pages de 1000."""
        candles: list = []
        while since_ms < until_ms:
            batch = self._exchange.fetch_ohlcv(symbol, timeframe=timeframe, since=since_ms, limit=1000)
            if not batch:
                break
            candles.extend(c for c in batch if c[0] < until_ms)
            next_since = batch[-1][0] + 1
            if next_since <= since_ms:
                break
            since_ms = next_since
        return _raw_to_df(candles)

    def fetch_history(
        self, symbol: str, timeframe: str, since_ms: int, until_ms: int
    ) -> pd.DataFrame:
        """Historique complet [since_ms, until_ms[ avec la même résolution que fetch_ohlcv."""
        return _resolve(symbol, lambda s: self._paginate(s, timeframe, since_ms, until_ms))


def _resolve(symbol: str, fetch: Callable[[str], pd.DataFrame]) -> pd.DataFrame:
    """Résout une paire : directe, inverse, puis reconstruction via USDT."""
    # 1. Paire directe
    try:
        return fetch(symbol)
    except ccxt.BadSymbol:
        pass

    # 2. Paire inverse (B/A → inversion des prix)
    inv = _inverse_symbol(symbol)
    if inv is not None:
        try:
            return _invert_ohlcv(fetch(inv))
        except ccxt.BadSymbol:
            pass

    # 3. Reconstruction synthétique via USDT : A/USDT ÷ B/USDT
    parts = symbol.split("/")
    if len(parts) == 2:
        base, quote = parts
        if base != "USDT" and quote != "USDT":
            return _cross_via_usdt(fetch(f"{base}/USDT"), fetch(f"{quote}/USDT"))

    raise ccxt.BadSymbol(f"impossible de résoudre la paire {symbol}")
