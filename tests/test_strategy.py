import pandas as pd
import numpy as np
from tradbot.strategy.dual_ma import DualMACrossover
from tradbot.strategy.base import Signal


def _make_df(closes: list[float]) -> pd.DataFrame:
    idx = pd.date_range("2020-01-01", periods=len(closes), freq="1h")
    return pd.DataFrame({"close": closes}, index=idx)


def test_hold_when_not_enough_data():
    strategy = DualMACrossover(fast=5, slow=10)
    df = _make_df([100.0] * 8)
    event = strategy.on_data(df)
    assert event.signal == Signal.HOLD


def test_buy_signal_when_fast_above_slow():
    strategy = DualMACrossover(fast=3, slow=5)
    # tendance haussière : la MM courte finit clairement au-dessus
    closes = [100, 101, 102, 103, 104, 105, 106]
    event = strategy.on_data(_make_df(closes))
    assert event.signal == Signal.BUY


def test_sell_signal_when_fast_below_slow():
    strategy = DualMACrossover(fast=3, slow=5)
    # tendance baissière
    closes = [106, 105, 104, 103, 102, 101, 100]
    event = strategy.on_data(_make_df(closes))
    assert event.signal == Signal.SELL
