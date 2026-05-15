import pandas as pd
import pytest
import ccxt

from tradbot.data.feed import CcxtFeed, _inverse_symbol, _invert_ohlcv, _cross_via_usdt, _raw_to_df


def _make_df(rows: list[tuple]) -> pd.DataFrame:
    df = pd.DataFrame(rows, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
    df.set_index("timestamp", inplace=True)
    return df


def test_inverse_symbol():
    assert _inverse_symbol("BTC/ETH") == "ETH/BTC"
    assert _inverse_symbol("ETH/BTC") == "BTC/ETH"
    assert _inverse_symbol("INVALID") is None


def test_invert_ohlcv_values():
    df = _make_df([(0, 0.05, 0.06, 0.04, 0.055, 100.0)])
    inv = _invert_ohlcv(df)
    assert inv["open"].iloc[0] == pytest.approx(1 / 0.05)
    assert inv["close"].iloc[0] == pytest.approx(1 / 0.055)
    # high de l'inverse = 1 / low de l'original
    assert inv["high"].iloc[0] == pytest.approx(1 / 0.04)
    # low de l'inverse = 1 / high de l'original
    assert inv["low"].iloc[0] == pytest.approx(1 / 0.06)


def test_fetch_ohlcv_fallback_to_inverse(monkeypatch):
    raw_inverse = [
        [0, 0.05, 0.06, 0.04, 0.055, 100.0],
    ]

    call_log = []

    def fake_fetch_ohlcv(self, symbol, timeframe="1h", limit=500):
        call_log.append(symbol)
        if symbol == "BTC/ETH":
            raise ccxt.BadSymbol("binance does not have market symbol BTC/ETH")
        return raw_inverse

    feed = CcxtFeed.__new__(CcxtFeed)
    feed._exchange = type("FakeExchange", (), {"fetch_ohlcv": fake_fetch_ohlcv})()

    df = feed.fetch_ohlcv("BTC/ETH", timeframe="1h", limit=1)

    assert call_log == ["BTC/ETH", "ETH/BTC"]
    assert df["close"].iloc[0] == pytest.approx(1 / 0.055)
    assert df["high"].iloc[0] == pytest.approx(1 / 0.04)
    assert df["low"].iloc[0] == pytest.approx(1 / 0.06)


def test_fetch_ohlcv_raises_when_no_inverse(monkeypatch):
    def fake_fetch_ohlcv(self, symbol, timeframe="1h", limit=500):
        raise ccxt.BadSymbol(f"unknown symbol {symbol}")

    feed = CcxtFeed.__new__(CcxtFeed)
    feed._exchange = type("FakeExchange", (), {"fetch_ohlcv": fake_fetch_ohlcv})()

    with pytest.raises(ccxt.BadSymbol):
        feed.fetch_ohlcv("BTC/ETH", timeframe="1h", limit=1)


def test_cross_via_usdt_values():
    btc_usdt = _raw_to_df([[0, 40000, 42000, 38000, 41000, 1.0]])
    eth_usdt = _raw_to_df([[0,  2000,  2100,  1900,  2050, 5.0]])
    result = _cross_via_usdt(btc_usdt, eth_usdt)
    assert result["open"].iloc[0] == pytest.approx(40000 / 2000)
    assert result["close"].iloc[0] == pytest.approx(41000 / 2050)
    # high = BTC_high / ETH_low
    assert result["high"].iloc[0] == pytest.approx(42000 / 1900)
    # low = BTC_low / ETH_high
    assert result["low"].iloc[0] == pytest.approx(38000 / 2100)
    assert result["volume"].iloc[0] == pytest.approx(1.0)


def test_fetch_ohlcv_fallback_to_usdt_cross():
    raw_btc_usdt = [[0, 40000, 42000, 38000, 41000, 1.0]]
    raw_eth_usdt = [[0,  2000,  2100,  1900,  2050, 5.0]]
    call_log = []

    def fake_fetch_ohlcv(self, symbol, timeframe="1h", limit=500):
        call_log.append(symbol)
        if symbol == "BTC/ETH":
            raise ccxt.BadSymbol("no BTC/ETH")
        if symbol == "ETH/BTC":
            raise ccxt.BadSymbol("no ETH/BTC")
        if symbol == "BTC/USDT":
            return raw_btc_usdt
        if symbol == "ETH/USDT":
            return raw_eth_usdt
        raise ccxt.BadSymbol(f"unknown {symbol}")

    feed = CcxtFeed.__new__(CcxtFeed)
    feed._exchange = type("FakeExchange", (), {"fetch_ohlcv": fake_fetch_ohlcv})()

    df = feed.fetch_ohlcv("BTC/ETH", timeframe="1h", limit=1)

    assert call_log == ["BTC/ETH", "ETH/BTC", "BTC/USDT", "ETH/USDT"]
    assert df["close"].iloc[0] == pytest.approx(41000 / 2050)
    assert df["high"].iloc[0] == pytest.approx(42000 / 1900)


def test_fetch_ohlcv_raises_when_usdt_cross_also_fails():
    def fake_fetch_ohlcv(self, symbol, timeframe="1h", limit=500):
        raise ccxt.BadSymbol(f"unknown {symbol}")

    feed = CcxtFeed.__new__(CcxtFeed)
    feed._exchange = type("FakeExchange", (), {"fetch_ohlcv": fake_fetch_ohlcv})()

    with pytest.raises(ccxt.BadSymbol):
        feed.fetch_ohlcv("BTC/ETH", timeframe="1h", limit=1)
