from dataclasses import dataclass

import pandas as pd

from ..config import RiskConfig
from ..strategy.base import Signal, SignalEvent


@dataclass
class Portfolio:
    capital: float
    peak_capital: float
    position: float = 0.0       # taille en unités de l'actif
    trades_this_hour: int = 0


class RiskManager:
    def __init__(self, config: RiskConfig):
        self.cfg = config

    def validate(self, event: SignalEvent, portfolio: Portfolio) -> SignalEvent:
        if event.signal == Signal.HOLD:
            return event

        drawdown = (portfolio.peak_capital - portfolio.capital) / portfolio.peak_capital
        if drawdown >= self.cfg.max_drawdown_pct:
            return SignalEvent(Signal.HOLD, event.symbol, event.price,
                               reason=f"drawdown max atteint ({drawdown:.1%})")

        if portfolio.trades_this_hour >= self.cfg.max_trades_per_hour:
            return SignalEvent(Signal.HOLD, event.symbol, event.price,
                               reason="limite de trades/heure atteinte")

        if event.signal == Signal.BUY:
            total = portfolio.capital + portfolio.position * event.price
            if total > 0:
                exposure = portfolio.position * event.price / total
                if exposure >= self.cfg.max_exposure_pct:
                    return SignalEvent(Signal.HOLD, event.symbol, event.price,
                                       reason=f"exposition max atteinte ({exposure:.1%})")

        return event

    def check_market(self, df: pd.DataFrame, symbol: str) -> SignalEvent | None:
        """Retourne un HOLD si les conditions de marché sont anormales, None sinon."""
        if "volume" not in df.columns or len(df) < 21:
            return None
        last_volume = df["volume"].iloc[-1]
        avg_volume = df["volume"].iloc[-21:-1].mean()
        if avg_volume > 0 and last_volume < avg_volume * self.cfg.min_volume_factor:
            return SignalEvent(Signal.HOLD, symbol, df["close"].iloc[-1],
                               reason=f"volume anormal ({last_volume:.0f} < {avg_volume * self.cfg.min_volume_factor:.0f})")
        return None

    def position_size(self, capital: float, price: float) -> float:
        allocated = capital * self.cfg.max_position_pct
        return allocated / price
