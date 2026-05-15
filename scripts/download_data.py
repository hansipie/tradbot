"""
Télécharge l'historique OHLCV d'un symbole depuis Binance et le sauvegarde en Parquet.
Usage : uv run python scripts/download_data.py
"""

import time
import pandas as pd
import ccxt
from tradbot.config import Config
from tradbot.data.feed import _inverse_symbol, _invert_ohlcv, _raw_to_df, _cross_via_usdt

cfg = Config()


def _paginate(exchange: ccxt.Exchange, symbol: str, timeframe: str, since_ms: int) -> pd.DataFrame:
    """Télécharge l'historique complet d'une paire par pages de 1000 bougies."""
    all_candles: list = []
    batch = exchange.fetch_ohlcv(symbol, timeframe=timeframe, since=since_ms, limit=1000)
    if batch:
        all_candles.extend(batch)
        since_ms = batch[-1][0] + 1
    while len(batch) >= 1000:
        time.sleep(exchange.rateLimit / 1000)
        batch = exchange.fetch_ohlcv(symbol, timeframe=timeframe, since=since_ms, limit=1000)
        if not batch:
            break
        all_candles.extend(batch)
        since_ms = batch[-1][0] + 1
        print(f"  {len(all_candles)} bougies récupérées…", end="\r")
    print()
    return _raw_to_df(all_candles)


def fetch_full_history(exchange: ccxt.Exchange, symbol: str, timeframe: str, since_iso: str) -> pd.DataFrame:
    since_ms = exchange.parse8601(since_iso + "T00:00:00Z")

    # 1. Paire directe
    try:
        return _paginate(exchange, symbol, timeframe, since_ms)
    except ccxt.BadSymbol:
        pass

    # 2. Paire inverse
    inv = _inverse_symbol(symbol)
    if inv is not None:
        try:
            print(f"  {symbol} introuvable, utilisation de la paire inverse {inv}")
            return _invert_ohlcv(_paginate(exchange, inv, timeframe, since_ms))
        except ccxt.BadSymbol:
            pass

    # 3. Reconstruction synthétique via USDT
    parts = symbol.split("/")
    if len(parts) == 2:
        base, quote = parts
        if base != "USDT" and quote != "USDT":
            print(f"  {symbol} et {inv} introuvables, reconstruction via {base}/USDT ÷ {quote}/USDT")
            df_base = _paginate(exchange, f"{base}/USDT", timeframe, since_ms)
            df_quote = _paginate(exchange, f"{quote}/USDT", timeframe, since_ms)
            return _cross_via_usdt(df_base, df_quote)

    raise ccxt.BadSymbol(f"impossible de résoudre la paire {symbol}")


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
