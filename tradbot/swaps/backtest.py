"""Backtest de l'alerte « swap retour rentable » (logique pure, sans réseau ni base).

On rejoue l'historique des swaps : entre deux swaps consécutifs, l'ensemble des
positions ouvertes est fixe (`open_positions` sur les swaps déjà passés), et
chaque prix historique observé dans cet intervalle est évalué avec `evaluate`,
exactement comme le fait la boucle live (`main._check_swaps`), y compris la
logique de ré-armement de l'alerte.

Les prix sont fournis par paire (`OpenPosition.symbol`, ex. "ETH/BTC") sous forme
de `pd.Series` : index = instant d'observation en secondes Unix (fin de bougie),
valeur = token_from reçus pour 1 token_to (cours de clôture).

La règle de sortie (`ExitRule`) décide quand une alerte se déclenche : seuil de gain
seul (baseline), ou couplé à un croisement de moyennes mobiles du cours de la paire.
"""
from collections.abc import Mapping
from dataclasses import dataclass, field
from statistics import mean, median

import pandas as pd

from .evaluator import OpenPosition, Swap, evaluate, open_positions


MODES = ("threshold", "cross_and", "trail", "cross")


@dataclass(frozen=True)
class ExitRule:
    """Règle de déclenchement de l'alerte.

    threshold : gain >= seuil (baseline).
    cross_and : gain >= seuil ET MA rapide sous la MA lente (tendance essoufflée).
    trail     : une fois le seuil atteint, on attend que la MA rapide passe sous la
                MA lente, même si le gain est retombé entre-temps.
    cross     : croisement baissier MA rapide/lente seul, tant que le gain est > 0.
    """

    mode: str = "threshold"
    fast: int = 10
    slow: int = 30

    def __post_init__(self) -> None:
        if self.mode not in MODES:
            raise ValueError(f"mode inconnu : {self.mode!r} (attendu : {', '.join(MODES)})")
        if self.uses_ma and not 0 < self.fast < self.slow:
            raise ValueError("il faut 0 < MA rapide < MA lente")

    @property
    def uses_ma(self) -> bool:
        return self.mode != "threshold"

    @property
    def label(self) -> str:
        return f"{self.mode} {self.fast}/{self.slow}" if self.uses_ma else self.mode


def ma_flags(series: pd.Series, fast: int, slow: int) -> pd.DataFrame:
    """Colonnes booléennes `down` (MA rapide < MA lente) et `cross_down` (vient de passer sous).

    Causal : la valeur à l'instant t n'utilise que les clôtures <= t. Faux tant que la
    MA lente n'a pas `slow` points.
    """
    f = series.rolling(fast).mean()
    sl = series.rolling(slow).mean()
    down = (f < sl).fillna(False)
    prev_up = (~down).shift(1, fill_value=False) & sl.shift(1).notna()
    return pd.DataFrame({"down": down, "cross_down": down & prev_up})


@dataclass(frozen=True)
class Signal:
    """Une alerte qui se serait déclenchée."""

    swap_id: int
    ts: int
    rate: float
    gain: float        # gain relatif après frais
    units_back: float  # token_from récupérés après frais
    cost_from: float   # token_from engagés dans la part encore détenue

    @property
    def units_gain(self) -> float:
        """Gain en unités du token d'origine (après frais)."""
        return self.units_back - self.cost_from


@dataclass
class PositionReport:
    swap: Swap
    symbol: str
    n_obs: int = 0
    signals: list[Signal] = field(default_factory=list)
    max_gain: float | None = None
    max_gain_ts: int | None = None
    last_gain: float | None = None
    closed_ts: int | None = None
    closed_by: int | None = None       # id du swap qui a refermé la position
    realized_gain: float | None = None  # gain réel si fermée par un swap retour direct

    @property
    def has_data(self) -> bool:
        return self.n_obs > 0

    @property
    def first_signal(self) -> Signal | None:
        return self.signals[0] if self.signals else None

    @property
    def delay_s(self) -> int | None:
        """Délai entre le swap et la première alerte."""
        first = self.first_signal
        return first.ts - self.swap.timestamp if first else None


@dataclass(frozen=True)
class BacktestSummary:
    min_gain: float
    fee: float
    n_positions: int
    n_without_data: int
    n_with_signal: int
    n_signals: int
    hit_rate: float                   # positions avec signal / positions avec données
    delay_days_median: float | None
    delay_days_mean: float | None
    delay_days_max: float | None
    gain_first_signal_mean: float | None
    units_gain_by_token: dict[str, float]  # somme des gains en unités à la 1re alerte
    n_signal_beats_realized: int      # 1re alerte meilleure que le swap retour réel
    n_with_realized: int              # positions fermées par un swap retour direct ET signalées
    rule: str = "threshold"
    gain_per_day: float | None = None  # somme des gains / somme des jours de détention (positions signalées)


@dataclass(frozen=True)
class BacktestResult:
    reports: list[PositionReport]
    summary: BacktestSummary


def _is_direct_return(pos: OpenPosition, swap: Swap) -> bool:
    return (
        swap.wallet_from == pos.swap.wallet_to
        and swap.token_from == pos.swap.token_to
        and swap.token_to == pos.swap.token_from
    )


def _close(report: PositionReport, last: OpenPosition, ts: int, swaps_at_ts: list[Swap]) -> None:
    report.closed_ts = ts
    spenders = [
        s for s in swaps_at_ts
        if s.wallet_from == last.swap.wallet_to and s.token_from == last.swap.token_to
    ]
    if not spenders:
        return
    closing = spenders[0]
    report.closed_by = closing.id
    if _is_direct_return(last, closing) and closing.amount_from > 0:
        # Frais déjà inclus dans les montants réels du swap retour
        rate = closing.amount_to / closing.amount_from
        report.realized_gain = evaluate(last, rate, fee=0.0).gain


def _triggered(mode: str, gain: float, min_gain: float, down: bool, cross_down: bool, armed: bool) -> bool:
    if mode == "threshold":
        return gain >= min_gain
    if mode == "cross_and":
        return gain >= min_gain and down
    if mode == "trail":
        return armed and down
    return gain > 0 and cross_down  # cross


def run_backtest(
    swaps: list[Swap],
    prices: Mapping[str, pd.Series],
    fee: float,
    min_gain: float,
    rearm_margin: float = 0.005,
    end_ts: int | None = None,
    rule: ExitRule = ExitRule(),
) -> BacktestResult:
    swaps = sorted(swaps, key=lambda s: (s.timestamp, s.id))
    event_ts = sorted({s.timestamp for s in swaps})
    if end_ts is None:
        end_ts = max((int(p.index.max()) + 1 for p in prices.values() if len(p)), default=0)

    reports: dict[int, PositionReport] = {}
    open_now: dict[int, OpenPosition] = {}
    alerted: set[int] = set()
    armed: set[int] = set()  # mode trail : seuil atteint, on attend le croisement
    flags = (
        {sym: ma_flags(p, rule.fast, rule.slow) for sym, p in prices.items() if len(p)}
        if rule.uses_ma else {}
    )

    for k, t_start in enumerate(event_ts):
        if t_start >= end_ts:
            break
        t_end = min(event_ts[k + 1], end_ts) if k + 1 < len(event_ts) else end_ts
        swaps_at_t = [s for s in swaps if s.timestamp == t_start]
        positions = {p.swap.id: p for p in open_positions([s for s in swaps if s.timestamp <= t_start])}

        for swap_id in open_now.keys() - positions.keys():
            _close(reports[swap_id], open_now[swap_id], t_start, swaps_at_t)
            alerted.discard(swap_id)
            armed.discard(swap_id)
        open_now = positions

        for swap_id, pos in positions.items():
            report = reports.setdefault(swap_id, PositionReport(pos.swap, pos.symbol))
            series = prices.get(pos.symbol)
            if series is None or series.empty:
                continue
            window = series[(series.index >= t_start) & (series.index < t_end)]
            for ts, rate in window.items():
                opp = evaluate(pos, float(rate), fee)
                ts = int(ts)
                report.n_obs += 1
                report.last_gain = opp.gain
                if report.max_gain is None or opp.gain > report.max_gain:
                    report.max_gain, report.max_gain_ts = opp.gain, ts
                if rule.uses_ma:
                    row = flags[pos.symbol].loc[ts]
                    down, cross_down = bool(row["down"]), bool(row["cross_down"])
                else:
                    down = cross_down = False
                if rule.mode == "trail" and opp.gain >= min_gain:
                    armed.add(swap_id)
                if _triggered(rule.mode, opp.gain, min_gain, down, cross_down, swap_id in armed):
                    if swap_id not in alerted:
                        report.signals.append(
                            Signal(swap_id, ts, opp.rate, opp.gain, opp.units_back, pos.cost_from)
                        )
                        alerted.add(swap_id)
                        armed.discard(swap_id)
                elif opp.gain < min_gain - rearm_margin:
                    alerted.discard(swap_id)
                    armed.discard(swap_id)

    ordered = sorted(reports.values(), key=lambda r: (r.swap.timestamp, r.swap.id))
    return BacktestResult(ordered, summarize(ordered, fee, min_gain, rule))


def summarize(
    reports: list[PositionReport], fee: float, min_gain: float, rule: ExitRule = ExitRule()
) -> BacktestSummary:
    with_data = [r for r in reports if r.has_data]
    signaled = [r for r in with_data if r.first_signal]
    delays = [r.delay_s / 86400 for r in signaled]
    units: dict[str, float] = {}
    for r in signaled:
        units[r.swap.token_from] = units.get(r.swap.token_from, 0.0) + r.first_signal.units_gain
    realized = [r for r in signaled if r.realized_gain is not None]
    held_days = sum(delays)
    return BacktestSummary(
        min_gain=min_gain,
        fee=fee,
        n_positions=len(reports),
        n_without_data=len(reports) - len(with_data),
        n_with_signal=len(signaled),
        n_signals=sum(len(r.signals) for r in with_data),
        hit_rate=len(signaled) / len(with_data) if with_data else 0.0,
        delay_days_median=median(delays) if delays else None,
        delay_days_mean=mean(delays) if delays else None,
        delay_days_max=max(delays) if delays else None,
        gain_first_signal_mean=mean(r.first_signal.gain for r in signaled) if signaled else None,
        units_gain_by_token=units,
        n_signal_beats_realized=sum(1 for r in realized if r.first_signal.gain > r.realized_gain),
        n_with_realized=len(realized),
        rule=rule.label,
        gain_per_day=(
            sum(r.first_signal.gain for r in signaled) / held_days if held_days > 0 else None
        ),
    )


def needed_ranges(swaps: list[Swap], end_ts: int, warmup_s: int = 0) -> dict[str, tuple[int, int]]:
    """Paires à télécharger et plage [début, fin[ nécessaire pour chacune.

    `warmup_s` recule le début pour que les moyennes mobiles soient déjà chaudes au swap.
    """
    swaps = sorted(swaps, key=lambda s: (s.timestamp, s.id))
    ranges: dict[str, tuple[int, int]] = {}
    for t in sorted({s.timestamp for s in swaps}):
        for pos in open_positions([s for s in swaps if s.timestamp <= t]):
            start = ranges.get(pos.symbol, (pos.swap.timestamp, end_ts))[0]
            ranges[pos.symbol] = (min(start, pos.swap.timestamp), end_ts)
    return {sym: (max(0, start - warmup_s), stop) for sym, (start, stop) in ranges.items()}
