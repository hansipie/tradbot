"""
Visualiseur des données historiques OHLCV + indicateurs + backtest.
Usage : uv run python scripts/visualize.py
Génère : data/historical/BTC_USDT_1d.png
"""

import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import matplotlib.gridspec as gridspec

from backtest.engine import run_backtest
from tradbot.config import Config
from tradbot.strategy.dual_ma import DualMACrossover


def main() -> None:
    cfg = Config()
    output_file = cfg.data_file.with_suffix(".png")
    df = pd.read_parquet(cfg.data_file)
    strategy = DualMACrossover(fast=50, slow=200)
    result = run_backtest(df, strategy, initial_capital=10_000.0, fee_rate=0.001)
    title = f"{cfg.symbol} — Dual MA Crossover 50/200"

    df["ma50"]  = df["close"].rolling(50).mean()
    df["ma200"] = df["close"].rolling(200).mean()

    buys  = [t for t in result.trades if t["type"] == "buy"]
    sells = [t for t in result.trades if t["type"] == "sell"]

    fig = plt.figure(figsize=(16, 12), facecolor="#0f1117")
    fig.suptitle(title, color="white", fontsize=14, y=0.98)

    gs = gridspec.GridSpec(3, 1, figure=fig, height_ratios=[4, 1.2, 1.8], hspace=0.08)

    # ── Panneau 1 : prix + MAs + signaux ──────────────────────────────────────
    ax1 = fig.add_subplot(gs[0])
    ax1.set_facecolor("#0f1117")
    ax1.plot(df.index, df["close"], color="#4fc3f7", linewidth=0.8, label="Close")
    ax1.plot(df.index, df["ma50"],  color="#ffb74d", linewidth=1.2, label="MA 50")
    ax1.plot(df.index, df["ma200"], color="#ef5350", linewidth=1.2, label="MA 200")
    ax1.scatter([t["timestamp"] for t in buys],  [t["price"] for t in buys],
                marker="^", color="#66bb6a", s=100, zorder=5, label="Achat")
    ax1.scatter([t["timestamp"] for t in sells], [t["price"] for t in sells],
                marker="v", color="#ef5350", s=100, zorder=5, label="Vente")
    ax1.set_ylabel("Prix (USDT)", color="white")
    ax1.legend(loc="upper left", framealpha=0.3, labelcolor="white", facecolor="#1e1e2e")
    ax1.tick_params(colors="white", labelbottom=False)
    ax1.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"{x:,.0f}"))
    for spine in ax1.spines.values():
        spine.set_edgecolor("#333")

    # ── Panneau 2 : volume ─────────────────────────────────────────────────────
    ax2 = fig.add_subplot(gs[1], sharex=ax1)
    ax2.set_facecolor("#0f1117")
    colors = ["#66bb6a" if df["close"].iloc[i] >= df["open"].iloc[i] else "#ef5350"
              for i in range(len(df))]
    ax2.bar(df.index, df["volume"], color=colors, width=0.8, alpha=0.7)
    ax2.set_ylabel("Volume", color="white")
    ax2.tick_params(colors="white", labelbottom=False)
    ax2.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"{x/1e3:.0f}k"))
    for spine in ax2.spines.values():
        spine.set_edgecolor("#333")

    # ── Panneau 3 : courbe d'équité ────────────────────────────────────────────
    ax3 = fig.add_subplot(gs[2], sharex=ax1)
    ax3.set_facecolor("#0f1117")
    ax3.plot(result.equity.index, result.equity.values, color="#ce93d8", linewidth=1.2)
    ax3.fill_between(result.equity.index, result.equity.values, 10_000,
                     where=(result.equity.values >= 10_000),
                     color="#66bb6a", alpha=0.15)
    ax3.fill_between(result.equity.index, result.equity.values, 10_000,
                     where=(result.equity.values < 10_000),
                     color="#ef5350", alpha=0.15)
    ax3.axhline(10_000, color="#555", linewidth=0.8, linestyle="--")
    ax3.set_ylabel("Équité ($)", color="white")
    ax3.tick_params(colors="white")
    ax3.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"{x/1e3:.0f}k$"))
    ax3.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    ax3.xaxis.set_major_locator(mdates.YearLocator())
    for spine in ax3.spines.values():
        spine.set_edgecolor("#333")

    # ── Annotation métriques ───────────────────────────────────────────────────
    calmar = result.cagr / abs(result.max_drawdown)
    stats = (f"CAGR {result.cagr:.1%}  |  DD max {result.max_drawdown:.1%}  |  "
             f"Sharpe {result.sharpe:.2f}  |  Calmar {calmar:.2f}  |  {len(result.trades)} trades")
    fig.text(0.5, 0.01, stats, ha="center", color="#aaa", fontsize=9)

    plt.savefig(output_file, dpi=150, bbox_inches="tight", facecolor=fig.get_facecolor())
    print(f"Graphique sauvegardé : {output_file}")


if __name__ == "__main__":
    main()
