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

    def crossover_proximity(self, df: pd.DataFrame, horizon: float = 2.0) -> tuple[str, float] | None:
        """Retourne (direction, bougies_estimées) si un croisement est imminent, sinon None."""
        ma_fast = df["close"].rolling(self.fast).mean()
        ma_slow = df["close"].rolling(self.slow).mean()
        gap = ma_fast - ma_slow
        if pd.isna(gap.iloc[-1]):
            return None
        velocity = gap.diff().iloc[-1]
        if velocity == 0 or pd.isna(velocity):
            return None
        bars = -gap.iloc[-1] / velocity
        if 0 < bars <= horizon:
            direction = "BUY" if gap.iloc[-1] < 0 else "SELL"
            return direction, float(bars)
        return None

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
