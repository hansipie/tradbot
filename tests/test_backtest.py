import pandas as pd
import numpy as np
import pytest
from backtest.engine import BacktestResult, run_backtest
from tradbot.config import RiskConfig
from tradbot.risk.manager import RiskManager
from tradbot.strategy.base import Signal, SignalEvent
from tradbot.strategy.dual_ma import DualMACrossover


def _make_result(equity_values: list[float], trades: list[dict]) -> BacktestResult:
    idx = pd.date_range("2020-01-01", periods=len(equity_values), freq="D")
    return BacktestResult(
        trades=trades,
        equity=pd.Series(equity_values, index=idx, dtype=float),
    )


# --- Calmar ---

def test_calmar_positive():
    # CAGR positif, drawdown de 20%
    result = _make_result([10_000, 12_000, 9_600, 14_400], trades=[])
    assert result.calmar == pytest.approx(result.cagr / abs(result.max_drawdown), rel=1e-6)
    assert result.calmar > 0


def test_calmar_zero_when_no_drawdown():
    result = _make_result([10_000, 11_000, 12_000], trades=[])
    assert result.max_drawdown == 0.0
    assert result.calmar == 0.0


# --- Sortino ---

def test_sortino_higher_than_sharpe_when_mostly_upside():
    # Série avec plusieurs baisses mais globalement haussière
    # → downside_std < total_std → Sortino > Sharpe
    values = [10_000, 10_500, 10_200, 10_800, 10_400, 11_200, 10_900, 11_800]
    result = _make_result(values, trades=[])
    assert result.sortino > result.sharpe


def test_sortino_zero_when_no_downside():
    # Equity strictement croissante : aucun return négatif → downside vide → 0.0
    result = _make_result([10_000, 11_000, 12_000, 13_000], trades=[])
    assert result.sortino == 0.0


def test_sortino_negative_when_negative_mean_return():
    result = _make_result([10_000, 9_000, 8_000, 7_000], trades=[])
    assert result.sortino < 0


# --- Win rate & Profit factor ---

def _trade_pair(buy_price, sell_price, capital_before):
    """Fabrique un aller-retour BUY→SELL simplifié (sans frais pour clarté)."""
    units = capital_before / buy_price
    capital_after = units * sell_price
    return (
        {"type": "buy", "price": buy_price, "units": units, "fee": 0.0,
         "capital_after": 0.0, "timestamp": None},
        {"type": "sell", "price": sell_price, "units": units, "fee": 0.0,
         "capital_after": capital_after, "pnl": capital_after - capital_before,
         "timestamp": None},
    )


def test_win_rate_all_winners():
    buy1, sell1 = _trade_pair(100, 130, 10_000)   # +30%
    buy2, sell2 = _trade_pair(130, 150, sell1["capital_after"])  # +15%
    result = _make_result([10_000, 13_000, 15_000], trades=[buy1, sell1, buy2, sell2])
    assert result.win_rate == 1.0


def test_win_rate_all_losers():
    buy1, sell1 = _trade_pair(100, 80, 10_000)   # -20%
    buy2, sell2 = _trade_pair(80, 60, sell1["capital_after"])  # -25%
    result = _make_result([10_000, 8_000, 6_000], trades=[buy1, sell1, buy2, sell2])
    assert result.win_rate == 0.0


def test_win_rate_mixed():
    buy1, sell1 = _trade_pair(100, 130, 10_000)   # gagnant
    buy2, sell2 = _trade_pair(130, 100, sell1["capital_after"])   # perdant
    result = _make_result([10_000, 13_000, 10_000], trades=[buy1, sell1, buy2, sell2])
    assert result.win_rate == pytest.approx(0.5)


def test_win_rate_no_trades():
    result = _make_result([10_000, 10_500], trades=[])
    assert result.win_rate == 0.0


def test_profit_factor_all_gains():
    buy1, sell1 = _trade_pair(100, 120, 10_000)
    buy2, sell2 = _trade_pair(120, 150, sell1["capital_after"])
    result = _make_result([10_000, 12_000, 15_000], trades=[buy1, sell1, buy2, sell2])
    assert result.profit_factor == float("inf")


def test_profit_factor_mixed():
    buy1, sell1 = _trade_pair(100, 120, 10_000)   # gain = 2000
    buy2, sell2 = _trade_pair(120, 110, sell1["capital_after"])  # perte ≈ -1000
    result = _make_result([10_000, 12_000, 11_000], trades=[buy1, sell1, buy2, sell2])
    pnl = result._round_trip_pnl
    gains = sum(p for p in pnl if p > 0)
    losses = abs(sum(p for p in pnl if p < 0))
    assert result.profit_factor == pytest.approx(gains / losses, rel=1e-6)
    assert result.profit_factor > 1  # stratégie gagnante globalement


def test_profit_factor_no_trades():
    result = _make_result([10_000, 10_500], trades=[])
    assert result.profit_factor == 0.0


# --- Intégration : run_backtest produit des métriques cohérentes ---

def test_run_backtest_metrics_consistent():
    closes = list(range(100, 400))
    idx = pd.date_range("2018-01-01", periods=len(closes), freq="D")
    df = pd.DataFrame({"close": closes}, index=idx)

    result = run_backtest(df, DualMACrossover(fast=10, slow=30))

    assert 0.0 <= result.win_rate <= 1.0
    assert result.profit_factor >= 0.0
    if result.cagr > 0 and result.max_drawdown < 0:
        assert result.calmar > 0


# --- Slippage ---

def test_slippage_reduces_capital():
    closes = list(range(100, 400))
    idx = pd.date_range("2018-01-01", periods=len(closes), freq="D")
    df = pd.DataFrame({"close": closes}, index=idx)
    strategy = DualMACrossover(fast=10, slow=30)

    result_no_slip = run_backtest(df, strategy, slippage_pct=0.0)
    result_slip    = run_backtest(df, strategy, slippage_pct=0.005)

    # Le slippage dégrade toujours la performance finale
    assert result_slip.equity.iloc[-1] <= result_no_slip.equity.iloc[-1]


def test_slippage_zero_equals_no_slippage():
    closes = [100, 110, 120, 115, 130, 125, 140]
    idx = pd.date_range("2020-01-01", periods=len(closes), freq="D")
    df = pd.DataFrame({"close": closes}, index=idx)
    strategy = DualMACrossover(fast=2, slow=4)

    r1 = run_backtest(df, strategy, slippage_pct=0.0)
    r2 = run_backtest(df, strategy, slippage_pct=0.0, fee_rate=0.0)
    # Sans frais ni slippage, le résultat est reproductible
    assert r2.equity.iloc[-1] >= r1.equity.iloc[-1]


class _SequenceStrategy:
    def __init__(self, signals: list[Signal]):
        self.signals = iter(signals)

    def on_data(self, df: pd.DataFrame) -> SignalEvent:
        return SignalEvent(next(self.signals), "BTC/USDT", float(df["close"].iloc[-1]))


def test_sharpe_uses_equity_frequency():
    values = [100.0, 102.0, 101.0, 104.0]
    daily = BacktestResult(equity=pd.Series(
        values, index=pd.date_range("2020-01-01", periods=4, freq="1D")
    ))
    five_minutes = BacktestResult(equity=pd.Series(
        values, index=pd.date_range("2020-01-01", periods=4, freq="5min")
    ))
    assert five_minutes.sharpe > daily.sharpe


def test_backtest_respects_partial_position_size():
    df = pd.DataFrame(
        {"close": [100.0, 100.0, 100.0]},
        index=pd.date_range("2020-01-01", periods=3, freq="1D"),
    )
    risk = RiskManager(RiskConfig(max_position_pct=0.5))
    result = run_backtest(
        df, _SequenceStrategy([Signal.BUY, Signal.HOLD]), risk=risk,
        fee_rate=0.0, slippage_pct=0.0,
    )
    buy = result.trades[0]
    assert buy["capital_after"] == pytest.approx(5_000.0)
    assert buy["units"] == pytest.approx(50.0)


def test_buy_never_makes_capital_negative():
    df = pd.DataFrame(
        {"close": [100.0, 100.0]},
        index=pd.date_range("2020-01-01", periods=2, freq="1D"),
    )
    result = run_backtest(
        df, _SequenceStrategy([Signal.BUY]),
        risk=RiskManager(RiskConfig(max_position_pct=1.0)),
        fee_rate=0.01, slippage_pct=0.0,
    )
    assert result.trades[0]["capital_after"] >= 0.0


def test_sell_liquidates_all_units():
    df = pd.DataFrame(
        {"close": [100.0, 100.0, 100.0, 100.0]},
        index=pd.date_range("2020-01-01", periods=4, freq="1D"),
    )
    result = run_backtest(
        df, _SequenceStrategy([Signal.BUY, Signal.BUY, Signal.SELL]),
        risk=RiskManager(RiskConfig(max_position_pct=0.5)),
        fee_rate=0.0, slippage_pct=0.0,
    )
    buys = [trade for trade in result.trades if trade["type"] == "buy"]
    sell = [trade for trade in result.trades if trade["type"] == "sell"][0]
    assert sell["units"] == pytest.approx(sum(trade["units"] for trade in buys))


class _TargetSequenceStrategy:
    """Comme _SequenceStrategy mais permet de fixer target_size par signal."""

    def __init__(self, signals: list[tuple[Signal, float | None]]):
        self.signals = iter(signals)

    def on_data(self, df: pd.DataFrame) -> SignalEvent:
        signal, target_size = next(self.signals)
        return SignalEvent(signal, "BTC/USDT", float(df["close"].iloc[-1]), target_size=target_size)


def test_sell_respects_partial_target_size():
    df = pd.DataFrame(
        {"close": [100.0, 100.0, 100.0]},
        index=pd.date_range("2020-01-01", periods=3, freq="1D"),
    )
    result = run_backtest(
        df,
        _TargetSequenceStrategy([(Signal.BUY, None), (Signal.SELL, 0.3)]),
        risk=RiskManager(RiskConfig(max_position_pct=1.0)),
        fee_rate=0.0, slippage_pct=0.0,
    )
    buy = result.trades[0]
    sell = result.trades[1]
    # Ne vend que ce qu'il faut pour ramener l'exposition à 30% du portefeuille (10 000$)
    assert sell["units"] == pytest.approx(70.0)
    assert sell["capital_after"] == pytest.approx(7_000.0)
    # PnL réalisé proportionnel à la fraction vendue (70% du coût d'achat, revendu au même prix)
    assert sell["pnl"] == pytest.approx(0.0)


def test_sell_partial_then_full_closes_position():
    df = pd.DataFrame(
        {"close": [100.0, 100.0, 100.0, 100.0]},
        index=pd.date_range("2020-01-01", periods=4, freq="1D"),
    )
    result = run_backtest(
        df,
        _TargetSequenceStrategy([(Signal.BUY, None), (Signal.SELL, 0.3), (Signal.SELL, 0.0)]),
        risk=RiskManager(RiskConfig(max_position_pct=1.0)),
        fee_rate=0.0, slippage_pct=0.0,
    )
    sells = [trade for trade in result.trades if trade["type"] == "sell"]
    assert len(sells) == 2
    assert sells[1]["units"] == pytest.approx(30.0)


def test_check_market_blocks_backtest_trades():
    # 20 bougies à volume normal, dernière à volume anormalement bas
    volumes = [1000.0] * 20 + [10.0]
    closes = [100.0] * 21
    df = pd.DataFrame(
        {"close": closes, "volume": volumes},
        index=pd.date_range("2020-01-01", periods=21, freq="1D"),
    )
    risk = RiskManager(RiskConfig(min_volume_factor=0.1))
    result = run_backtest(
        df, _SequenceStrategy([Signal.BUY] * 20),
        risk=risk, fee_rate=0.0, slippage_pct=0.0,
    )
    # Le signal BUY émis sur la dernière bougie (volume anormal) est bloqué
    assert all(trade["timestamp"] != df.index[-1] for trade in result.trades)
