import pandas as pd
import numpy as np
import pytest
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


def test_crossover_proximity_none_when_insufficient_data():
    strategy = DualMACrossover(fast=3, slow=5)
    df = _make_df([10.0] * 4)  # pas assez pour MA slow=5
    assert strategy.crossover_proximity(df) is None


def test_crossover_proximity_none_when_parallel():
    strategy = DualMACrossover(fast=3, slow=5)
    # closes constantes → gap = 0, velocity = 0
    assert strategy.crossover_proximity(_make_df([10.0] * 7)) is None


def test_crossover_proximity_none_when_diverging():
    strategy = DualMACrossover(fast=3, slow=5)
    # gap positif croissant → bars négatif
    assert strategy.crossover_proximity(_make_df([10, 11, 13, 15, 17, 20, 24])) is None


def test_crossover_proximity_buy_imminent():
    strategy = DualMACrossover(fast=3, slow=5)
    # fast rattrape slow par le bas : bars ≈ 1.0 → BUY
    closes = [15, 14, 13, 12, 11, 11.5, 12]
    result = strategy.crossover_proximity(_make_df(closes))
    assert result is not None
    direction, bars = result
    assert direction == "BUY"
    assert bars == pytest.approx(1.0)


def test_crossover_proximity_sell_imminent():
    strategy = DualMACrossover(fast=3, slow=5)
    # fast descend vers slow par le haut : bars ≈ 1.0 → SELL
    closes = [11, 12, 13, 14, 15, 14.5, 14]
    result = strategy.crossover_proximity(_make_df(closes))
    assert result is not None
    direction, bars = result
    assert direction == "SELL"
    assert bars == pytest.approx(1.0)


def test_crossover_proximity_none_when_beyond_horizon():
    strategy = DualMACrossover(fast=3, slow=5)
    # croisement dans ~1 bougie, mais horizon réduit à 0.5
    closes = [15, 14, 13, 12, 11, 11.5, 12]
    assert strategy.crossover_proximity(_make_df(closes), horizon=0.5) is None
