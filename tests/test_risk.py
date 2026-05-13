import pandas as pd
import pytest
from tradbot.config import RiskConfig
from tradbot.risk.manager import Portfolio, RiskManager
from tradbot.strategy.base import Signal, SignalEvent


def _cfg(**kwargs) -> RiskConfig:
    return RiskConfig(**kwargs)


def _portfolio(**kwargs) -> Portfolio:
    defaults = {"capital": 10_000.0, "peak_capital": 10_000.0}
    return Portfolio(**{**defaults, **kwargs})


def _event(signal=Signal.BUY, price=50_000.0) -> SignalEvent:
    return SignalEvent(signal=signal, symbol="BTC/USDT", price=price)


def _df_with_volume(volumes: list[float], closes: list[float] | None = None) -> pd.DataFrame:
    n = len(volumes)
    idx = pd.date_range("2020-01-01", periods=n, freq="D")
    closes = closes or [100.0] * n
    return pd.DataFrame({"close": closes, "volume": volumes}, index=idx)


# --- Drawdown ---

def test_drawdown_blocks_signal():
    risk = RiskManager(_cfg(max_drawdown_pct=0.10))
    portfolio = _portfolio(capital=8_900.0, peak_capital=10_000.0)  # -11%
    result = risk.validate(_event(), portfolio)
    assert result.signal == Signal.HOLD
    assert "drawdown" in result.reason


def test_drawdown_below_limit_passes():
    risk = RiskManager(_cfg(max_drawdown_pct=0.10))
    portfolio = _portfolio(capital=9_500.0, peak_capital=10_000.0)  # -5%
    assert risk.validate(_event(), portfolio).signal == Signal.BUY


# --- Trades par heure ---

def test_trades_per_hour_blocks():
    risk = RiskManager(_cfg(max_trades_per_hour=3))
    portfolio = _portfolio(trades_this_hour=3)
    result = risk.validate(_event(), portfolio)
    assert result.signal == Signal.HOLD
    assert "heure" in result.reason


# --- Exposition totale ---

def test_exposure_blocks_buy_when_already_exposed():
    # max_drawdown_pct=1.0 pour isoler le check d'exposition
    risk = RiskManager(_cfg(max_exposure_pct=0.95, max_drawdown_pct=1.0))
    # position 0.2 BTC à 50 000$ = 10 000$ / total 10 200$ ≈ 98% d'exposition
    portfolio = _portfolio(capital=200.0, peak_capital=200.0, position=0.2)
    result = risk.validate(_event(Signal.BUY, price=50_000.0), portfolio)
    assert result.signal == Signal.HOLD
    assert "exposition" in result.reason


def test_exposure_does_not_block_sell():
    risk = RiskManager(_cfg(max_exposure_pct=0.50, max_drawdown_pct=1.0))
    portfolio = _portfolio(capital=200.0, peak_capital=200.0, position=0.2)
    # SELL ne doit pas être bloqué par le check d'exposition
    result = risk.validate(_event(Signal.SELL, price=50_000.0), portfolio)
    assert result.signal == Signal.SELL


def test_exposure_passes_when_no_position():
    risk = RiskManager(_cfg(max_exposure_pct=0.95))
    portfolio = _portfolio(capital=10_000.0, position=0.0)
    assert risk.validate(_event(Signal.BUY, price=50_000.0), portfolio).signal == Signal.BUY


# --- Volume anormal ---

def test_volume_check_blocks_on_low_volume():
    risk = RiskManager(_cfg(min_volume_factor=0.1))
    # 20 bougies à volume=1000, dernière à 10 (1% de la moyenne)
    volumes = [1000.0] * 20 + [10.0]
    result = risk.check_market(_df_with_volume(volumes), "BTC/USDT")
    assert result is not None
    assert result.signal == Signal.HOLD
    assert "volume" in result.reason


def test_volume_check_passes_on_normal_volume():
    risk = RiskManager(_cfg(min_volume_factor=0.1))
    volumes = [1000.0] * 21
    assert risk.check_market(_df_with_volume(volumes), "BTC/USDT") is None


def test_volume_check_skipped_when_no_volume_column():
    risk = RiskManager(_cfg())
    idx = pd.date_range("2020-01-01", periods=25, freq="D")
    df = pd.DataFrame({"close": [100.0] * 25}, index=idx)
    assert risk.check_market(df, "BTC/USDT") is None


def test_volume_check_skipped_when_not_enough_rows():
    risk = RiskManager(_cfg(min_volume_factor=0.1))
    volumes = [1000.0] * 10 + [1.0]
    assert risk.check_market(_df_with_volume(volumes), "BTC/USDT") is None
