import pandas as pd
import numpy as np
import pytest
from backtest.engine import BacktestResult, run_backtest
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
    capital_after = (capital_before / buy_price) * sell_price
    return (
        {"type": "buy",  "price": buy_price,  "capital_before": capital_before, "timestamp": None},
        {"type": "sell", "price": sell_price, "capital": capital_after,          "timestamp": None},
    )


def test_win_rate_all_winners():
    buy1, sell1 = _trade_pair(100, 130, 10_000)   # +30%
    buy2, sell2 = _trade_pair(130, 150, sell1["capital"])  # +15%
    result = _make_result([10_000, 13_000, 15_000], trades=[buy1, sell1, buy2, sell2])
    assert result.win_rate == 1.0


def test_win_rate_all_losers():
    buy1, sell1 = _trade_pair(100, 80, 10_000)   # -20%
    buy2, sell2 = _trade_pair(80, 60, sell1["capital"])  # -25%
    result = _make_result([10_000, 8_000, 6_000], trades=[buy1, sell1, buy2, sell2])
    assert result.win_rate == 0.0


def test_win_rate_mixed():
    buy1, sell1 = _trade_pair(100, 130, 10_000)   # gagnant
    buy2, sell2 = _trade_pair(130, 100, sell1["capital"])   # perdant
    result = _make_result([10_000, 13_000, 10_000], trades=[buy1, sell1, buy2, sell2])
    assert result.win_rate == pytest.approx(0.5)


def test_win_rate_no_trades():
    result = _make_result([10_000, 10_500], trades=[])
    assert result.win_rate == 0.0


def test_profit_factor_all_gains():
    buy1, sell1 = _trade_pair(100, 120, 10_000)
    buy2, sell2 = _trade_pair(120, 150, sell1["capital"])
    result = _make_result([10_000, 12_000, 15_000], trades=[buy1, sell1, buy2, sell2])
    assert result.profit_factor == float("inf")


def test_profit_factor_mixed():
    buy1, sell1 = _trade_pair(100, 120, 10_000)   # gain = 2000
    buy2, sell2 = _trade_pair(120, 110, sell1["capital"])  # perte ≈ -1000
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
    # Série haussière longue → au moins un trade BUY→SELL
    closes = list(range(100, 400))  # 300 bougies haussières
    idx = pd.date_range("2018-01-01", periods=len(closes), freq="D")
    df = pd.DataFrame({"close": closes}, index=idx)

    result = run_backtest(df, DualMACrossover(fast=10, slow=30))

    assert 0.0 <= result.win_rate <= 1.0
    assert result.profit_factor >= 0.0
    # Calmar et Sortino ont le même signe que CAGR si la série est gagnante
    if result.cagr > 0 and result.max_drawdown < 0:
        assert result.calmar > 0
