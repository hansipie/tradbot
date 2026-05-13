import pandas as pd
from .base import Signal, SignalEvent


class RSIMeanReversion:
    """
    Achète quand RSI(period) < oversold ET prix > MA(ma_filter), vend quand RSI > overbought.
    Le filtre MA évite d'acheter dans une tendance baissière de fond (catching a falling knife).
    """

    def __init__(self, period: int = 14, oversold: float = 30, overbought: float = 70,
                 ma_filter: int | None = 200):
        self.period = period
        self.oversold = oversold
        self.overbought = overbought
        self.ma_filter = ma_filter

    def on_data(self, df: pd.DataFrame) -> SignalEvent:
        close = df["close"]
        delta = close.diff()
        gain = delta.clip(lower=0).rolling(self.period).mean()
        loss = (-delta.clip(upper=0)).rolling(self.period).mean()
        rs = gain / loss.replace(0, float("inf"))
        rsi = (100 - 100 / (1 + rs)).shift(1)

        last_rsi = rsi.iloc[-1]
        last_price = close.iloc[-1]

        if pd.isna(last_rsi):
            return SignalEvent(Signal.HOLD, symbol="", price=last_price, reason="pas assez de données")

        # Filtre de tendance : on n'achète que si le prix est au-dessus de la MA
        trend_ok = True
        if self.ma_filter is not None:
            ma = close.rolling(self.ma_filter).mean().shift(1).iloc[-1]
            if pd.isna(ma):
                return SignalEvent(Signal.HOLD, symbol="", price=last_price, reason="pas assez de données pour MA")
            trend_ok = last_price > ma

        if last_rsi < self.oversold and trend_ok:
            return SignalEvent(Signal.BUY, symbol="", price=last_price,
                               reason=f"RSI {last_rsi:.1f} < {self.oversold} + tendance haussière")
        if last_rsi > self.overbought:
            return SignalEvent(Signal.SELL, symbol="", price=last_price,
                               reason=f"RSI {last_rsi:.1f} > {self.overbought}")

        return SignalEvent(Signal.HOLD, symbol="", price=last_price, reason=f"RSI {last_rsi:.1f}")
