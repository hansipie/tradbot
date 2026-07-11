from dataclasses import dataclass
from enum import Enum
from typing import Protocol
import pandas as pd


class Signal(Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


@dataclass
class SignalEvent:
    signal: Signal
    symbol: str
    price: float
    reason: str = ""
    confidence: float | None = None
    expected_return: float | None = None
    horizon_bars: int | None = None
    target_size: float | None = None


class Strategy(Protocol):
    def on_data(self, df: pd.DataFrame) -> SignalEvent: ...
