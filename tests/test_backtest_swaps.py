import pandas as pd
import pytest

from tradbot.data.feed import CcxtFeed, _raw_to_df
from tradbot.data.history import HistoryCache, close_series
from tradbot.swaps import Swap
from tradbot.swaps.backtest import ExitRule, ma_flags, needed_ranges, run_backtest

H = 3600


def _swap(id, ts, tf, af, tt, at, wallet="W"):
    return Swap(id, ts, tf, af, wallet, tt, at, wallet)


def _prices(points: dict[int, float]) -> pd.Series:
    return pd.Series(points, dtype=float)


# 0.1 BTC -> 2 ETH : le seuil de rentabilité (sans frais) est 0.05 BTC/ETH
BASE = _swap(1, 0, "BTC", 0.1, "ETH", 2.0)


def test_first_signal_delay_and_units_gain():
    prices = {"ETH/BTC": _prices({1 * H: 0.049, 2 * H: 0.051, 3 * H: 0.0525, 4 * H: 0.053})}
    res = run_backtest([BASE], prices, fee=0.0, min_gain=0.04)
    r = res.reports[0]
    assert r.n_obs == 4
    assert len(r.signals) == 1
    sig = r.first_signal
    assert sig.ts == 3 * H
    assert sig.gain == pytest.approx(0.05)
    assert sig.units_gain == pytest.approx(0.005)  # en BTC
    assert r.delay_s == 3 * H
    assert r.max_gain == pytest.approx(0.06)
    assert r.max_gain_ts == 4 * H
    s = res.summary
    assert s.n_with_signal == 1 and s.n_signals == 1
    assert s.units_gain_by_token == {"BTC": pytest.approx(0.005)}
    assert s.delay_days_median == pytest.approx(3 / 24)


def test_fee_is_applied_before_threshold():
    prices = {"ETH/BTC": _prices({H: 0.0525})}  # +5 % brut
    assert run_backtest([BASE], prices, fee=0.0, min_gain=0.04).summary.n_with_signal == 1
    assert run_backtest([BASE], prices, fee=0.02, min_gain=0.04).summary.n_with_signal == 0


def test_rearm_needs_drop_below_margin():
    # seuil 4 %, ré-armement sous 3.5 %
    prices = {"ETH/BTC": _prices({
        1 * H: 0.0522,   # +4.4 % -> alerte
        2 * H: 0.0519,   # +3.8 % : pas de ré-armement
        3 * H: 0.0523,   # +4.6 % : pas de nouvelle alerte
        4 * H: 0.0510,   # +2 % : ré-armement
        5 * H: 0.0525,   # +5 % : nouvelle alerte
    })}
    r = run_backtest([BASE], prices, fee=0.0, min_gain=0.04, rearm_margin=0.005).reports[0]
    assert [s.ts for s in r.signals] == [1 * H, 5 * H]


def test_return_swap_closes_position_and_stops_signals():
    back = _swap(2, 3 * H, "ETH", 2.0, "BTC", 0.104)
    prices = {
        "ETH/BTC": _prices({1 * H: 0.049, 2 * H: 0.053, 4 * H: 0.06}),
        "BTC/ETH": _prices({4 * H: 1 / 0.06}),
    }
    res = run_backtest([BASE, back], prices, fee=0.0, min_gain=0.04)
    reports = {r.swap.id: r for r in res.reports}
    r1 = reports[1]
    assert r1.closed_ts == 3 * H
    assert r1.closed_by == 2
    assert r1.realized_gain == pytest.approx(0.04)
    assert [s.ts for s in r1.signals] == [2 * H]  # rien après la fermeture
    assert r1.n_obs == 2
    # la 1re alerte (+6 %) battait le swap retour réel (+4 %)
    assert res.summary.n_signal_beats_realized == 1
    assert res.summary.n_with_realized == 1
    # Le swap retour devient lui-même une position (BTC -> ETH inverse)
    assert reports[2].symbol == "BTC/ETH"
    assert reports[2].closed_ts is None


def test_price_before_swap_is_ignored():
    late = _swap(1, 10 * H, "BTC", 0.1, "ETH", 2.0)
    prices = {"ETH/BTC": _prices({5 * H: 0.09, 11 * H: 0.05})}
    r = run_backtest([late], prices, fee=0.0, min_gain=0.01).reports[0]
    assert r.n_obs == 1
    assert r.signals == []


def test_partial_spend_reduces_units_gain():
    swaps = [BASE, _swap(2, 2 * H, "ETH", 1.0, "USDC", 3000.0)]
    prices = {"ETH/BTC": _prices({3 * H: 0.055}), "USDC/ETH": _prices({})}
    res = run_backtest(swaps, prices, fee=0.0, min_gain=0.05)
    r1 = next(r for r in res.reports if r.swap.id == 1)
    assert r1.closed_ts is None
    # reste 1 ETH pour 0.05 BTC -> 0.055 BTC : +0.005 BTC
    assert r1.first_signal.units_gain == pytest.approx(0.005)
    assert r1.first_signal.gain == pytest.approx(0.1)


def test_missing_prices_are_reported():
    res = run_backtest([BASE], {}, fee=0.0, min_gain=0.02, end_ts=10 * H)
    assert res.reports[0].has_data is False
    assert res.summary.n_without_data == 1
    assert res.summary.hit_rate == 0.0


def test_end_ts_limits_replay():
    prices = {"ETH/BTC": _prices({1 * H: 0.049, 5 * H: 0.06})}
    r = run_backtest([BASE], prices, fee=0.0, min_gain=0.04, end_ts=2 * H).reports[0]
    assert r.n_obs == 1 and r.signals == []


def test_needed_ranges():
    swaps = [BASE, _swap(2, 3 * H, "ETH", 2.0, "BTC", 0.104)]
    assert needed_ranges(swaps, 10 * H) == {"ETH/BTC": (0, 10 * H), "BTC/ETH": (3 * H, 10 * H)}


# --- Règles de sortie avec moyennes mobiles ------------------------------------

def test_ma_flags_cross_down():
    s = _prices({i * H: v for i, v in enumerate([1, 2, 3, 4, 3, 2, 1, 1])})
    f = ma_flags(s, 2, 3)
    assert not f["down"].iloc[:2].any()  # MA lente pas encore chaude
    assert f["cross_down"].sum() == 1    # un seul franchissement
    assert f["cross_down"][f["down"].idxmax()]


# hausse puis retournement : le seuil de 4 % est atteint avant le croisement
_RISE = [0.050, 0.051, 0.052, 0.0525, 0.054, 0.056, 0.057, 0.055, 0.052, 0.050, 0.049]
_RISE_PRICES = {"ETH/BTC": _prices({(i + 1) * H: v for i, v in enumerate(_RISE)})}


def _first_signal(mode, min_gain=0.04):
    rule = ExitRule(mode, 2, 4)
    return run_backtest([BASE], _RISE_PRICES, fee=0.0, min_gain=min_gain, rule=rule).reports[0].first_signal


def test_cross_and_waits_for_trend_exhaustion_but_keeps_floor():
    base = run_backtest([BASE], _RISE_PRICES, fee=0.0, min_gain=0.035).reports[0].first_signal
    assert base.ts == 3 * H  # +4 % dès la 3e bougie
    sig = _first_signal("cross_and", min_gain=0.035)
    assert sig.ts > base.ts
    assert sig.gain >= 0.035


def test_trail_waits_for_cross_after_threshold():
    sig = _first_signal("trail", min_gain=0.035)
    assert sig is not None and sig.ts > 3 * H


def test_cross_only_requires_positive_gain():
    sig = _first_signal("cross")
    assert sig is not None and sig.gain > 0


def test_cross_and_never_signals_without_cross():
    rising = {"ETH/BTC": _prices({(i + 1) * H: 0.05 + 0.001 * i for i in range(12)})}
    r = run_backtest([BASE], rising, fee=0.0, min_gain=0.04, rule=ExitRule("cross_and", 2, 4)).reports[0]
    assert r.signals == []
    assert run_backtest([BASE], rising, fee=0.0, min_gain=0.04).reports[0].signals


def test_exit_rule_validation():
    with pytest.raises(ValueError):
        ExitRule("nope")
    with pytest.raises(ValueError):
        ExitRule("trail", 30, 10)


def test_needed_ranges_warmup():
    assert needed_ranges([BASE], 10 * H, warmup_s=5 * H) == {"ETH/BTC": (0, 10 * H)}
    late = _swap(1, 10 * H, "BTC", 0.1, "ETH", 2.0)
    assert needed_ranges([late], 20 * H, warmup_s=4 * H) == {"ETH/BTC": (6 * H, 20 * H)}


# --- Historique et cache (sans réseau) ---------------------------------------

def test_fetch_history_paginates_until_end():
    candles = [[i * H * 1000, 1, 1, 1, float(i), 1] for i in range(2500)]
    calls = []

    def fake_fetch_ohlcv(self, symbol, timeframe="1h", since=None, limit=1000):
        calls.append(since)
        return [c for c in candles if c[0] >= since][:limit]

    feed = CcxtFeed.__new__(CcxtFeed)
    feed._exchange = type("FakeExchange", (), {"fetch_ohlcv": fake_fetch_ohlcv})()
    df = feed.fetch_history("ETH/BTC", "1h", 0, 2200 * H * 1000)
    assert len(df) == 2200
    assert df["close"].iloc[-1] == 2199.0
    assert len(calls) == 3


class _FakeHistoryFeed:
    def __init__(self, n: int):
        self.candles = [[i * H * 1000, 1, 1, 1, float(i), 1] for i in range(n)]
        self.calls = []

    def fetch_history(self, symbol, timeframe, since_ms, until_ms):
        self.calls.append((since_ms, until_ms))
        return _raw_to_df([c for c in self.candles if since_ms <= c[0] < until_ms])


def test_history_cache_fetches_only_missing_tail(tmp_path):
    feed = _FakeHistoryFeed(100)
    cache = HistoryCache(feed, tmp_path, "1h")
    df = cache.get("ETH/BTC", 0, 50 * H * 1000)
    assert len(df) == 50
    assert (tmp_path / "ETH-BTC_1h.csv").is_file()

    df = cache.get("ETH/BTC", 0, 80 * H * 1000)
    assert len(df) == 80
    assert feed.calls[1][0] == 49 * H * 1000 + 1  # reprise après la dernière bougie
    assert df.index.is_monotonic_increasing and not df.index.duplicated().any()

    cache.get("ETH/BTC", 0, 80 * H * 1000)
    assert len(feed.calls) == 2  # déjà en cache


def test_history_cache_drops_unfinished_candle(tmp_path):
    feed = _FakeHistoryFeed(100)
    # until au milieu de la bougie 10 : elle n'est pas encore terminée
    df = HistoryCache(feed, tmp_path, "1h").get("ETH/BTC", 0, 10 * H * 1000 + 1800 * 1000)
    assert len(df) == 10


def test_close_series_uses_candle_end():
    df = _raw_to_df([[0, 1, 1, 1, 0.05, 1], [H * 1000, 1, 1, 1, 0.06, 1]])
    s = close_series(df, "1h")
    assert list(s.index) == [H, 2 * H]
    assert list(s) == [0.05, 0.06]
