import pandas as pd
from .base import Signal, SignalEvent


class DualMACrossover:
    """
    Achète quand MM(fast) > MM(slow), vend sinon.
    Stratégie de référence — simple, robuste, peu de paramètres.
    """

    def __init__(self, fast: int = 50, slow: int = 200):
        self.fast = fast
        self.slow = slow

    def on_data(self, df: pd.DataFrame) -> SignalEvent:
        # Shift(1) : on décide avec les données confirmées de la bougie précédente
        ma_fast = df["close"].rolling(self.fast).mean().shift(1)
        ma_slow = df["close"].rolling(self.slow).mean().shift(1)

        last_fast = ma_fast.iloc[-1]
        last_slow = ma_slow.iloc[-1]
        last_price = df["close"].iloc[-1]

        if pd.isna(last_fast) or pd.isna(last_slow):
            return SignalEvent(Signal.HOLD, symbol="", price=last_price, reason="pas assez de données")

        if last_fast > last_slow:
            return SignalEvent(Signal.BUY, symbol="", price=last_price, reason=f"MA{self.fast}>{self.slow}")
        else:
            return SignalEvent(Signal.SELL, symbol="", price=last_price, reason=f"MA{self.fast}<{self.slow}")
