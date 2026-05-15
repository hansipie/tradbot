"""
Télécharge l'historique OHLCV d'un symbole depuis Binance et le sauvegarde en Parquet.
Usage : uv run python scripts/download_data.py
"""

import time
import pandas as pd
import ccxt
from tradbot.config import Config
from tradbot.data.feed import _inverse_symbol, _invert_ohlcv

cfg = Config()


def fetch_full_history(exchange: ccxt.Exchange, symbol: str, timeframe: str, since_iso: str) -> pd.DataFrame:
    since_ms = exchange.parse8601(since_iso + "T00:00:00Z")
    all_candles = []
    inverted = False

    # Détecter dès la première page si la paire doit être inversée
    fetch_symbol = symbol
    try:
        first = exchange.fetch_ohlcv(fetch_symbol, timeframe=timeframe, since=since_ms, limit=1000)
    except ccxt.BadSymbol:
        inv = _inverse_symbol(symbol)
        if inv is None:
            raise
        print(f"  {symbol} introuvable, utilisation de la paire inverse {inv} avec inversion des prix")
        fetch_symbol = inv
        inverted = True
        first = exchange.fetch_ohlcv(fetch_symbol, timeframe=timeframe, since=since_ms, limit=1000)

    if first:
        all_candles.extend(first)
        since_ms = first[-1][0] + 1

    while len(first) >= 1000:
        time.sleep(exchange.rateLimit / 1000)
        first = exchange.fetch_ohlcv(fetch_symbol, timeframe=timeframe, since=since_ms, limit=1000)
        if not first:
            break
        all_candles.extend(first)
        since_ms = first[-1][0] + 1
        print(f"  {len(all_candles)} bougies récupérées…", end="\r")

    print()
    df = pd.DataFrame(all_candles, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
    df.set_index("timestamp", inplace=True)

    if inverted:
        df = _invert_ohlcv(df)

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
