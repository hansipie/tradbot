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


class Strategy(Protocol):
    def on_data(self, df: pd.DataFrame) -> SignalEvent: ...
