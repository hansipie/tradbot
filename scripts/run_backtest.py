"""
Lance un backtest et compare les stratégies disponibles.
Usage : uv run python scripts/run_backtest.py
"""

import pandas as pd
from backtest.engine import run_backtest, BacktestResult
from tradbot.config import Config
from tradbot.strategy.dual_ma import DualMACrossover
from tradbot.strategy.rsi_mean_reversion import RSIMeanReversion

INITIAL_CAPITAL = 10_000.0
FEE_RATE = 0.001


def print_result(label: str, result: BacktestResult) -> None:
    calmar = result.cagr / abs(result.max_drawdown) if result.max_drawdown != 0 else 0
    print(f"\n══ {label} ══")
    print(f"  Capital final     : {result.equity.iloc[-1]:>12,.2f} $")
    print(f"  CAGR              : {result.cagr:>12.1%}")
    print(f"  Drawdown max      : {result.max_drawdown:>12.1%}")
    print(f"  Sharpe ratio      : {result.sharpe:>12.2f}")
    print(f"  Calmar ratio      : {calmar:>12.2f}")
    print(f"  Nombre de trades  : {len(result.trades):>12}")
    print()
    for t in result.trades:
        capital_str = f"  → capital : {t['capital']:,.2f} $" if "capital" in t else ""
        print(f"  {t['timestamp'].date()}  {t['type'].upper():4s}  {t['price']:>10.5f} ${capital_str}")


def main() -> None:
    cfg = Config()
    df = pd.read_parquet(cfg.data_file)
    print(f"Paire    : {cfg.symbol}")
    print(f"Données  : {df.index[0].date()} → {df.index[-1].date()}  ({len(df)} bougies)")
    print(f"Capital  : {INITIAL_CAPITAL:,.0f} $  |  Frais : {FEE_RATE:.1%}/trade")

    print_result("Dual MA Crossover 50/200",
                 run_backtest(df, DualMACrossover(fast=50, slow=200), INITIAL_CAPITAL, FEE_RATE))

    print_result("RSI Mean Reversion (14, 30/70)",
                 run_backtest(df, RSIMeanReversion(period=14, oversold=30, overbought=70), INITIAL_CAPITAL, FEE_RATE))


if __name__ == "__main__":
    main()
