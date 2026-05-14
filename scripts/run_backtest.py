"""
Lance un backtest et compare les stratégies disponibles.
Usage :
  uv run python scripts/run_backtest.py           — vue globale (défaut)
  uv run python scripts/run_backtest.py --yearly  — découpage année par année
  uv run python scripts/run_backtest.py --all     — les deux
"""

import argparse

import pandas as pd
from backtest.engine import run_backtest, BacktestResult
from tradbot.config import Config
from tradbot.strategy.dual_ma import DualMACrossover
from tradbot.strategy.rsi_mean_reversion import RSIMeanReversion
from visualize import _visualize, _visualize_yearly

INITIAL_CAPITAL = 10_000.0
FEE_RATE = 0.001
COL = 10


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


def _yearly_returns(equity: pd.Series) -> dict[int, float]:
    years = sorted(equity.index.year.unique())
    returns = {}
    for year in years:
        slice_ = equity[equity.index.year == year]
        if len(slice_) < 2:
            continue
        prev = equity[equity.index.year < year]
        start = prev.iloc[-1] if len(prev) else slice_.iloc[0]
        returns[year] = (slice_.iloc[-1] - start) / start
    return returns


def print_yearly(strategies: list[tuple[str, BacktestResult]]) -> None:
    all_years = sorted({y for _, r in strategies for y in _yearly_returns(r.equity)})
    header = f"  {'Année':<6}" + "".join(f"{lbl[:COL]:>{COL}}" for lbl, _ in strategies)
    print(f"\n{header}")
    print("  " + "─" * (6 + COL * len(strategies)))
    for year in all_years:
        row = f"  {year:<6}"
        for _, result in strategies:
            yr = _yearly_returns(result.equity)
            if year in yr:
                val = yr[year]
                row += f"{'+' if val >= 0 else ''}{val:.1%}".rjust(COL)
            else:
                row += f"{'—':>{COL}}"
        print(row)


def main() -> None:
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--yearly", action="store_true", help="découpage année par année uniquement")
    group.add_argument("--all",    action="store_true", help="vue globale + découpage annuel")
    args = parser.parse_args()

    cfg = Config()
    strategies_def = [
        ("DualMA 50/200", lambda: DualMACrossover(fast=50, slow=200)),
        ("RSI MR 30/70",  lambda: RSIMeanReversion(period=14, oversold=30, overbought=70)),
    ]

    for symbol in cfg.symbols:
        df = pd.read_parquet(cfg.data_file(symbol))
        print(f"\n{'═' * 60}")
        print(f"Paire    : {symbol}")
        print(f"Données  : {df.index[0].date()} → {df.index[-1].date()}  ({len(df)} bougies)")
        print(f"Capital  : {INITIAL_CAPITAL:,.0f} $  |  Frais : {FEE_RATE:.1%}/trade")

        results = [(lbl, run_backtest(df, factory(), INITIAL_CAPITAL, FEE_RATE))
                   for lbl, factory in strategies_def]

        if not args.yearly:
            for lbl, result in results:
                print_result(lbl, result)

        if args.yearly or args.all:
            print_yearly(results)

        if not args.yearly:
            _visualize(cfg, symbol)
        if args.yearly or args.all:
            _visualize_yearly(cfg, symbol)


if __name__ == "__main__":
    main()
