"""
Télécharge l'historique OHLCV d'un symbole depuis Binance et le sauvegarde en Parquet.
Usage : uv run python scripts/download_data.py
"""

import time
import pandas as pd
import ccxt
from tradbot.config import Config

cfg = Config()


def fetch_full_history(exchange: ccxt.Exchange, symbol: str, timeframe: str, since_iso: str) -> pd.DataFrame:
    since_ms = exchange.parse8601(since_iso + "T00:00:00Z")
    all_candles = []

    while True:
        candles = exchange.fetch_ohlcv(symbol, timeframe=timeframe, since=since_ms, limit=1000)
        if not candles:
            break
        all_candles.extend(candles)
        since_ms = candles[-1][0] + 1
        print(f"  {len(all_candles)} bougies récupérées…", end="\r")
        if len(candles) < 1000:
            break
        time.sleep(exchange.rateLimit / 1000)

    print()
    df = pd.DataFrame(all_candles, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
    df.set_index("timestamp", inplace=True)
    return df


def main() -> None:
    exchange = getattr(ccxt, cfg.exchange.id)({"enableRateLimit": True})

    for symbol in cfg.symbols:
        dest = cfg.data_file(symbol)
        dest.parent.mkdir(parents=True, exist_ok=True)
        print(f"Téléchargement {symbol} {cfg.timeframe} depuis {cfg.history_since}…")
        df = fetch_full_history(exchange, symbol, cfg.timeframe, cfg.history_since)
        df.to_parquet(dest)
        print(f"Sauvegardé : {dest}  ({len(df)} lignes)")
        print(df.tail(3))


if __name__ == "__main__":
    main()
