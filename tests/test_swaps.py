import pandas as pd
import pytest

from tradbot.swaps import Swap, evaluate, open_positions, current_rate


def _swap(id, ts, tf, af, tt, at, wallet="Swissborg"):
    return Swap(id, ts, tf, af, wallet, tt, at, wallet)


def test_single_swap_is_open():
    pos = open_positions([_swap(1, 100, "BTC", 0.1, "ETH", 2.0)])
    assert len(pos) == 1
    assert pos[0].remaining_to == pytest.approx(2.0)
    assert pos[0].cost_from == pytest.approx(0.1)
    assert pos[0].symbol == "ETH/BTC"


def test_reverse_swap_closes_position():
    swaps = [
        _swap(1, 100, "BTC", 0.1, "ETH", 2.0),
        _swap(2, 200, "ETH", 2.0, "BTC", 0.11),
    ]
    pos = open_positions(swaps)
    # Seul le swap retour reste ouvert (BTC reçu, jamais redépensé)
    assert [p.swap.id for p in pos] == [2]


def test_spending_on_third_token_closes_position():
    swaps = [
        _swap(1, 100, "BTC", 0.1, "SOL", 10.0),
        _swap(2, 200, "SOL", 10.0, "USDC", 1500.0),
    ]
    assert [p.swap.id for p in open_positions(swaps)] == [2]


def test_partial_spend_keeps_remaining_share():
    swaps = [
        _swap(1, 100, "BTC", 0.1, "SOL", 10.0),
        _swap(2, 200, "SOL", 4.0, "USDC", 600.0),
    ]
    pos = {p.swap.id: p for p in open_positions(swaps)}
    assert pos[1].remaining_to == pytest.approx(6.0)
    assert pos[1].cost_from == pytest.approx(0.06)
    assert 2 in pos


def test_fifo_spends_oldest_lot_first():
    swaps = [
        _swap(1, 100, "BTC", 0.1, "SOL", 10.0),
        _swap(2, 150, "ETH", 1.0, "SOL", 5.0),
        _swap(3, 200, "SOL", 10.0, "USDC", 1500.0),
    ]
    ids = [p.swap.id for p in open_positions(swaps)]
    assert 1 not in ids
    assert 2 in ids and 3 in ids


def test_wallets_are_independent():
    swaps = [
        _swap(1, 100, "BTC", 0.1, "ETH", 2.0, wallet="A"),
        _swap(2, 200, "ETH", 2.0, "BTC", 0.11, wallet="B"),
    ]
    assert {p.swap.id for p in open_positions(swaps)} == {1, 2}


def test_evaluate_gain_with_fee():
    pos = open_positions([_swap(1, 100, "BTC", 0.1, "ETH", 2.0)])[0]
    # 1 ETH = 0.055 BTC → 2 ETH = 0.11 BTC, -1 % de frais = 0.1089 BTC
    opp = evaluate(pos, rate=0.055, fee=0.01)
    assert opp.units_back == pytest.approx(0.1089)
    assert opp.gain == pytest.approx(0.089)


def test_evaluate_negative_gain():
    pos = open_positions([_swap(1, 100, "BTC", 0.1, "ETH", 2.0)])[0]
    assert evaluate(pos, rate=0.04, fee=0.0).gain == pytest.approx(-0.2)


def test_current_rate_uses_last_close():
    class Feed:
        def fetch_ohlcv(self, symbol, timeframe, limit):
            assert symbol == "ETH/BTC"
            return pd.DataFrame({"close": [0.05, 0.056]})

    pos = open_positions([_swap(1, 100, "BTC", 0.1, "ETH", 2.0)])[0]
    assert current_rate(Feed(), pos) == pytest.approx(0.056)
