"""Backtest de l'alerte « swap retour rentable » sur l'historique des swaps.

uv run python scripts/backtest_swaps.py                      # swaps depuis PostgreSQL
uv run python scripts/backtest_swaps.py --sqlite ../CryptoUpdate/data/db.sqlite3
uv run python scripts/backtest_swaps.py --min-gain 1 2 5 --fee 0.5 --details
uv run python scripts/backtest_swaps.py --min-gain 5 --rules threshold cross_and trail cross --ma 10/30 20/50

Règles de sortie (--rules) : threshold (baseline), cross_and (seuil ET MA rapide < MA lente),
trail (seuil atteint, puis sortie au croisement baissier), cross (croisement seul, gain > 0).
Les MA portent sur le cours de la paire, au pas de --timeframe.

Les prix historiques (OHLCV ccxt, données publiques) sont mis en cache dans data/ohlcv/.
"""
import argparse
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import ccxt

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))  # le paquet tradbot n'est pas installé dans le venv

from tradbot.config import Config  # noqa: E402
from tradbot.data.feed import CcxtFeed
from tradbot.data.history import HistoryCache, close_series, timeframe_ms
from tradbot.storage import SwapStore
from tradbot.swaps import Swap
from tradbot.swaps.backtest import MODES, BacktestResult, ExitRule, needed_ranges, run_backtest  # noqa: E402


def _date(ts: int | None) -> str:
    return datetime.fromtimestamp(ts, timezone.utc).strftime("%d/%m/%Y %H:%M") if ts else "-"


def _pct(x: float | None) -> str:
    return f"{x:+.2%}" if x is not None else "-"


def load_swaps(args, cfg: Config) -> list[Swap]:
    if args.sqlite:
        from sync_swaps import read_swaps  # lecture seule (mode=ro)

        path = Path(args.sqlite)
        if not path.is_file():
            sys.exit(f"Base introuvable : {path}")
        return read_swaps(path)
    return SwapStore(cfg.postgres_url).load_all()


def parse_ma(text: str) -> tuple[int, int]:
    try:
        fast, slow = (int(x) for x in text.split("/"))
    except ValueError:
        raise argparse.ArgumentTypeError(f"format attendu RAPIDE/LENTE (ex. 10/30), reçu {text!r}")
    if not 0 < fast < slow:
        raise argparse.ArgumentTypeError(f"il faut 0 < rapide < lente, reçu {text!r}")
    return fast, slow


def load_prices(swaps: list[Swap], end_s: int, args, cfg: Config, warmup_s: int = 0) -> dict:
    feed = CcxtFeed(cfg.exchange.id, sandbox=False)  # données publiques, pas de clé
    cache = HistoryCache(feed, Path(args.cache_dir), args.timeframe)
    prices = {}
    for symbol, (start_s, stop_s) in sorted(needed_ranges(swaps, end_s, warmup_s).items()):
        try:
            df = cache.get(symbol, start_s * 1000, stop_s * 1000)
        except (ccxt.BadSymbol, ccxt.NetworkError, ccxt.ExchangeError) as exc:
            print(f"  ! {symbol} : prix indisponibles ({exc})", file=sys.stderr)
            continue
        print(f"  {symbol:<12} {len(df):>6} bougies {args.timeframe}", file=sys.stderr)
        prices[symbol] = close_series(df, args.timeframe)
    return prices


def print_details(result: BacktestResult) -> None:
    s = result.summary
    print(f"\nDétail par position ({s.rule}, seuil {s.min_gain:.1%}, frais {s.fee:.2%})")
    header = (f"{'id':>5} {'paire':<11} {'swap':<16} {'1re alerte':<16} {'délai j':>7} "
              f"{'gain':>8} {'gain unités':>16} {'alertes':>7} {'max':>8} {'réel':>8} {'fermé':<16}")
    print(header)
    print("-" * len(header))
    for r in result.reports:
        sig = r.first_signal
        units = f"{sig.units_gain:+.6g} {r.swap.token_from}" if sig else "-"
        delay = f"{r.delay_s / 86400:.1f}" if sig else "-"
        if not r.has_data:
            units = "pas de prix"
        print(f"{r.swap.id:>5} {r.symbol:<11} {_date(r.swap.timestamp):<16} "
              f"{_date(sig.ts if sig else None):<16} {delay:>7} {_pct(sig.gain if sig else None):>8} "
              f"{units:>16} {len(r.signals):>7} {_pct(r.max_gain):>8} {_pct(r.realized_gain):>8} "
              f"{_date(r.closed_ts):<16}")


def print_summary(results: list[BacktestResult]) -> None:
    print("\nSynthèse")
    header = (f"{'règle':<16} {'seuil':>6} {'positions':>9} {'sans prix':>9} {'signalées':>9} {'taux':>6} "
              f"{'alertes':>7} {'délai méd j':>11} {'délai max j':>11} {'gain moy':>8} "
              f"{'gain/j':>7} {'> réel':>7}  gain en unités à la 1re alerte")
    print(header)
    print("-" * len(header))
    for res in results:
        s = res.summary
        units = ", ".join(f"{v:+.6g} {k}" for k, v in sorted(s.units_gain_by_token.items())) or "-"
        med = f"{s.delay_days_median:.1f}" if s.delay_days_median is not None else "-"
        mx = f"{s.delay_days_max:.1f}" if s.delay_days_max is not None else "-"
        beats = f"{s.n_signal_beats_realized}/{s.n_with_realized}"
        print(f"{s.rule:<16} {s.min_gain:>6.1%} {s.n_positions:>9} {s.n_without_data:>9} {s.n_with_signal:>9} "
              f"{s.hit_rate:>6.0%} {s.n_signals:>7} {med:>11} {mx:>11} "
              f"{_pct(s.gain_first_signal_mean):>8} {_pct(s.gain_per_day):>7} {beats:>7}  {units}")
    print("\n'> réel' : positions dont la 1re alerte battait le swap retour réellement effectué"
          " / positions signalées fermées par un swap retour direct.")


def main() -> None:
    cfg = Config()
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--sqlite", help="lire les swaps depuis la base CryptoUpdate (lecture seule) au lieu de PostgreSQL")
    p.add_argument("--min-gain", type=float, nargs="+", default=[cfg.swaps.min_gain * 100],
                   help="seuil(s) d'alerte en %% (défaut : SWAP_MIN_GAIN_PCT)")
    p.add_argument("--fee", type=float, default=cfg.swaps.fee * 100, help="frais en %% (défaut : SWAP_FEE_PCT)")
    p.add_argument("--timeframe", default="1h", help="granularité des prix (défaut 1h)")
    p.add_argument("--cache-dir", default=str(_ROOT / "data" / "ohlcv" / cfg.exchange.id))
    p.add_argument("--rules", nargs="+", choices=MODES, default=["threshold"],
                   help="règle(s) de sortie à comparer (défaut : threshold)")
    p.add_argument("--ma", type=parse_ma, nargs="+", default=[(10, 30)], metavar="RAPIDE/LENTE",
                   help="périodes de MA en bougies, ex. 10/30 20/50 (défaut 10/30)")
    p.add_argument("--details", action="store_true", help="afficher le détail par position")
    args = p.parse_args()

    swaps = load_swaps(args, cfg)
    if not swaps:
        sys.exit("Aucun swap à rejouer.")
    end_s = int(time.time())
    print(f"{len(swaps)} swaps, du {_date(min(s.timestamp for s in swaps))} au {_date(end_s)}",
          file=sys.stderr)

    rules = [
        ExitRule(mode, fast, slow)
        for mode in args.rules
        for fast, slow in (args.ma if mode != "threshold" else [(10, 30)])
    ]
    warmup_s = max((r.slow for r in rules if r.uses_ma), default=0) * timeframe_ms(args.timeframe) // 1000
    prices = load_prices(swaps, end_s, args, cfg, warmup_s)
    results = [
        run_backtest(swaps, prices, fee=args.fee / 100, min_gain=g / 100,
                     rearm_margin=cfg.swaps.rearm_margin, end_ts=end_s, rule=rule)
        for rule in rules
        for g in args.min_gain
    ]
    if args.details:
        for res in results:
            print_details(res)
    print_summary(results)


if __name__ == "__main__":
    main()
