"""Historique OHLCV avec cache CSV local (un fichier par paire et timeframe)."""
from pathlib import Path
from typing import Protocol

import ccxt
import pandas as pd


class HistoryFeed(Protocol):
    def fetch_history(self, symbol: str, timeframe: str, since_ms: int, until_ms: int) -> pd.DataFrame: ...


def timeframe_ms(timeframe: str) -> int:
    return int(ccxt.Exchange.parse_timeframe(timeframe) * 1000)


class HistoryCache:
    """Complète le cache uniquement avec les bougies manquantes (début ou fin).

    Seules les bougies terminées (fin <= until) sont conservées, pour ne jamais
    figer en cache une bougie encore en cours.
    """

    def __init__(self, feed: HistoryFeed, cache_dir: Path, timeframe: str = "1h"):
        self._feed = feed
        self._dir = Path(cache_dir)
        self._tf = timeframe
        self._tf_ms = timeframe_ms(timeframe)

    def _path(self, symbol: str) -> Path:
        return self._dir / f"{symbol.replace('/', '-')}_{self._tf}.csv"

    def _load(self, path: Path) -> pd.DataFrame | None:
        if not path.is_file():
            return None
        df = pd.read_csv(path, index_col="timestamp")
        df.index = pd.to_datetime(df.index, utc=True)
        return df

    def get(self, symbol: str, since_ms: int, until_ms: int) -> pd.DataFrame:
        path = self._path(symbol)
        cached = self._load(path)
        parts = [] if cached is None else [cached]

        if cached is None or cached.empty:
            parts.append(self._feed.fetch_history(symbol, self._tf, since_ms, until_ms))
        else:
            first_ms = int(cached.index[0].timestamp() * 1000)
            last_ms = int(cached.index[-1].timestamp() * 1000)
            # la 1re bougie renvoyée démarre au plus une période après since_ms
            if since_ms <= first_ms - self._tf_ms:
                parts.append(self._feed.fetch_history(symbol, self._tf, since_ms, first_ms))
            if last_ms + 2 * self._tf_ms <= until_ms:
                parts.append(self._feed.fetch_history(symbol, self._tf, last_ms + 1, until_ms))

        frames = [p for p in parts if not p.empty]
        df = pd.concat(frames) if frames else parts[0]
        df = df[~df.index.duplicated(keep="last")].sort_index()
        until = pd.Timestamp(until_ms, unit="ms", tz="UTC")
        df = df[df.index + pd.Timedelta(milliseconds=self._tf_ms) <= until]

        self._dir.mkdir(parents=True, exist_ok=True)
        df.to_csv(path, index_label="timestamp")
        lo = pd.Timestamp(since_ms, unit="ms", tz="UTC")
        return df[df.index >= lo]


def close_series(df: pd.DataFrame, timeframe: str) -> pd.Series:
    """Cours de clôture indexés par l'instant d'observation (fin de bougie, secondes Unix)."""
    if df.empty:
        return pd.Series(dtype=float)
    obs_s = df.index.as_unit("s").asi8 + timeframe_ms(timeframe) // 1000
    return pd.Series(df["close"].to_numpy(dtype=float), index=obs_s)
