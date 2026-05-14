"""
Visualiseur des données historiques OHLCV + indicateurs + backtest.
Usage :
  uv run python scripts/visualize.py           — vue globale (défaut)
  uv run python scripts/visualize.py --yearly  — grille année par année
  uv run python scripts/visualize.py --all     — les deux
Génère :
  data/historical/{symbol}_{tf}.png          — vue globale
  data/historical/{symbol}_{tf}_yearly.png   — grille année par année
"""

import argparse
from pathlib import Path

import matplotlib.dates as mdates
import matplotlib.gridspec as gridspec
import matplotlib.pyplot as plt
import pandas as pd

from backtest.engine import run_backtest
from tradbot.config import Config
from tradbot.strategy.dual_ma import DualMACrossover

BG = "#0f1117"
FG = "white"
GRID = "#333"


def _style(ax) -> None:
    ax.set_facecolor(BG)
    ax.tick_params(colors=FG, labelsize=7)
    for spine in ax.spines.values():
        spine.set_edgecolor(GRID)


def main() -> None:
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--yearly", action="store_true", help="grille année par année uniquement")
    group.add_argument("--all",    action="store_true", help="vue globale + grille annuelle")
    args = parser.parse_args()

    cfg = Config()
    for symbol in cfg.symbols:
        if not args.yearly:
            _visualize(cfg, symbol)
        if args.yearly or args.all:
            _visualize_yearly(cfg, symbol)


# ── Vue globale ────────────────────────────────────────────────────────────────

def _visualize(cfg, symbol: str) -> None:
    data_file = cfg.data_file(symbol)
    output_file = data_file.with_suffix(".png")
    df = pd.read_parquet(data_file)
    result = run_backtest(df, DualMACrossover(fast=50, slow=200), initial_capital=10_000.0, fee_rate=0.001)

    df["ma50"]  = df["close"].rolling(50).mean()
    df["ma200"] = df["close"].rolling(200).mean()

    buys  = [t for t in result.trades if t["type"] == "buy"]
    sells = [t for t in result.trades if t["type"] == "sell"]

    fig = plt.figure(figsize=(16, 12), facecolor=BG)
    fig.suptitle(f"{symbol} — Dual MA Crossover 50/200", color=FG, fontsize=14, y=0.98)
    gs = gridspec.GridSpec(3, 1, figure=fig, height_ratios=[4, 1.2, 1.8], hspace=0.08)

    ax1 = fig.add_subplot(gs[0])
    _style(ax1)
    ax1.plot(df.index, df["close"], color="#4fc3f7", linewidth=0.8, label="Close")
    ax1.plot(df.index, df["ma50"],  color="#ffb74d", linewidth=1.2, label="MA 50")
    ax1.plot(df.index, df["ma200"], color="#ef5350", linewidth=1.2, label="MA 200")
    ax1.scatter([t["timestamp"] for t in buys],  [t["price"] for t in buys],
                marker="^", color="#66bb6a", s=100, zorder=5, label="Achat")
    ax1.scatter([t["timestamp"] for t in sells], [t["price"] for t in sells],
                marker="v", color="#ef5350", s=100, zorder=5, label="Vente")
    ax1.set_ylabel("Prix", color=FG)
    ax1.legend(loc="upper left", framealpha=0.3, labelcolor=FG, facecolor="#1e1e2e")
    ax1.tick_params(labelbottom=False)
    ax1.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"{x:,.0f}"))

    ax2 = fig.add_subplot(gs[1], sharex=ax1)
    _style(ax2)
    colors = ["#66bb6a" if df["close"].iloc[i] >= df["open"].iloc[i] else "#ef5350"
              for i in range(len(df))]
    ax2.bar(df.index, df["volume"], color=colors, width=0.8, alpha=0.7)
    ax2.set_ylabel("Volume", color=FG)
    ax2.tick_params(labelbottom=False)
    ax2.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"{x/1e3:.0f}k"))

    ax3 = fig.add_subplot(gs[2], sharex=ax1)
    _style(ax3)
    eq = result.equity
    ax3.plot(eq.index, eq.values, color="#ce93d8", linewidth=1.2)
    ax3.fill_between(eq.index, eq.values, 10_000, where=(eq.values >= 10_000), color="#66bb6a", alpha=0.15)
    ax3.fill_between(eq.index, eq.values, 10_000, where=(eq.values <  10_000), color="#ef5350", alpha=0.15)
    ax3.axhline(10_000, color="#555", linewidth=0.8, linestyle="--")
    ax3.set_ylabel("Équité ($)", color=FG)
    ax3.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"{x/1e3:.0f}k$"))
    ax3.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    ax3.xaxis.set_major_locator(mdates.YearLocator())

    calmar = result.cagr / abs(result.max_drawdown) if result.max_drawdown else 0
    fig.text(0.5, 0.01,
             f"CAGR {result.cagr:.1%}  |  DD max {result.max_drawdown:.1%}  |  "
             f"Sharpe {result.sharpe:.2f}  |  Calmar {calmar:.2f}  |  {len(result.trades)} trades",
             ha="center", color="#aaa", fontsize=9)

    plt.savefig(output_file, dpi=150, bbox_inches="tight", facecolor=BG)
    plt.close(fig)
    print(f"Graphique global     : {output_file}")


# ── Vue année par année ────────────────────────────────────────────────────────

def _visualize_yearly(cfg, symbol: str) -> None:
    data_file = cfg.data_file(symbol)
    slug = symbol.replace("/", "_")
    output_file = Path("data/historical") / f"{slug}_{cfg.timeframe}_yearly.png"

    df = pd.read_parquet(data_file)
    result = run_backtest(df, DualMACrossover(fast=50, slow=200), initial_capital=10_000.0, fee_rate=0.001)

    df["ma50"]  = df["close"].rolling(50).mean()
    df["ma200"] = df["close"].rolling(200).mean()

    buys  = {t["timestamp"]: t["price"] for t in result.trades if t["type"] == "buy"}
    sells = {t["timestamp"]: t["price"] for t in result.trades if t["type"] == "sell"}

    years = sorted(df.index.year.unique())
    n = len(years)

    fig, axes = plt.subplots(2, n, figsize=(max(4 * n, 12), 8), facecolor=BG,
                             gridspec_kw={"height_ratios": [3, 1.5], "hspace": 0.06, "wspace": 0.05})
    # Normalise axes en tableau 2D même pour n==1
    if n == 1:
        axes = [[axes[0]], [axes[1]]]

    fig.suptitle(f"{symbol} — Dual MA Crossover 50/200  (année par année)", color=FG, fontsize=13, y=1.01)

    eq = result.equity

    for col, year in enumerate(years):
        mask_df = df.index.year == year
        mask_eq = eq.index.year == year

        df_y  = df[mask_df]
        eq_y  = eq[mask_eq]

        ax_p = axes[0][col]
        ax_e = axes[1][col]

        # ── Prix + MAs ──
        _style(ax_p)
        ax_p.plot(df_y.index, df_y["close"], color="#4fc3f7", linewidth=0.8)
        ax_p.plot(df_y.index, df_y["ma50"],  color="#ffb74d", linewidth=0.9)
        ax_p.plot(df_y.index, df_y["ma200"], color="#ef5350", linewidth=0.9)

        yr_buys  = [(ts, p) for ts, p in buys.items()  if ts.year == year]
        yr_sells = [(ts, p) for ts, p in sells.items() if ts.year == year]
        if yr_buys:
            bx, by = zip(*yr_buys)
            ax_p.scatter(bx, by, marker="^", color="#66bb6a", s=70, zorder=5)
        if yr_sells:
            sx, sy = zip(*yr_sells)
            ax_p.scatter(sx, sy, marker="v", color="#ef5350", s=70, zorder=5)

        ax_p.set_title(str(year), color=FG, fontsize=10, pad=4)
        ax_p.tick_params(labelbottom=False, colors=FG, labelsize=6)
        ax_p.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"{x:,.0f}"))
        ax_p.yaxis.set_tick_params(labelsize=6)
        if col > 0:
            ax_p.tick_params(labelleft=False)

        # ── Rendement annuel en titre ──
        prev_eq = eq[eq.index.year < year]
        start_val = prev_eq.iloc[-1] if len(prev_eq) else (eq_y.iloc[0] if len(eq_y) else 10_000)
        if len(eq_y):
            ret = (eq_y.iloc[-1] - start_val) / start_val
            sign = "+" if ret >= 0 else ""
            color_ret = "#66bb6a" if ret >= 0 else "#ef5350"
            ax_p.set_title(f"{year}\n{sign}{ret:.1%}", color=FG, fontsize=9, pad=4)
            # couleur du % uniquement via text annoté
            ax_p.set_title(str(year), color=FG, fontsize=9, pad=4)
            ax_p.text(0.5, 1.01, f"{sign}{ret:.1%}", transform=ax_p.transAxes,
                      ha="center", va="bottom", color=color_ret, fontsize=8, fontweight="bold")

        # ── Équité ──
        _style(ax_e)
        if len(eq_y):
            ax_e.plot(eq_y.index, eq_y.values, color="#ce93d8", linewidth=1.0)
            ax_e.fill_between(eq_y.index, eq_y.values, start_val,
                              where=(eq_y.values >= start_val), color="#66bb6a", alpha=0.2)
            ax_e.fill_between(eq_y.index, eq_y.values, start_val,
                              where=(eq_y.values <  start_val), color="#ef5350", alpha=0.2)
            ax_e.axhline(start_val, color="#555", linewidth=0.7, linestyle="--")
        ax_e.xaxis.set_major_formatter(mdates.DateFormatter("%b"))
        ax_e.xaxis.set_major_locator(mdates.MonthLocator(bymonth=[1, 4, 7, 10]))
        ax_e.tick_params(axis="x", colors=FG, labelsize=6, rotation=45)
        ax_e.tick_params(axis="y", colors=FG, labelsize=6)
        ax_e.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"{x/1e3:.0f}k"))
        if col > 0:
            ax_e.tick_params(labelleft=False)

    # Légende commune
    handles = [
        plt.Line2D([0], [0], color="#4fc3f7", linewidth=1,   label="Close"),
        plt.Line2D([0], [0], color="#ffb74d", linewidth=1,   label="MA 50"),
        plt.Line2D([0], [0], color="#ef5350", linewidth=1,   label="MA 200"),
        plt.scatter([], [], marker="^", color="#66bb6a", s=40, label="Achat"),
        plt.scatter([], [], marker="v", color="#ef5350", s=40, label="Vente"),
    ]
    fig.legend(handles=handles, loc="lower center", ncol=5, framealpha=0.2,
               labelcolor=FG, facecolor="#1e1e2e", fontsize=8, bbox_to_anchor=(0.5, -0.04))

    plt.savefig(output_file, dpi=150, bbox_inches="tight", facecolor=BG)
    plt.close(fig)
    print(f"Graphique annuel     : {output_file}")


if __name__ == "__main__":
    main()
