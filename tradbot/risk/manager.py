from dataclasses import dataclass
from ..strategy.base import Signal, SignalEvent
from ..config import RiskConfig


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

        return event

    def position_size(self, capital: float, price: float) -> float:
        """Retourne le nombre d'unités à acheter selon le % de capital alloué."""
        allocated = capital * self.cfg.max_position_pct
        return allocated / price
