from dataclasses import dataclass
from typing import Protocol
import structlog

from ..strategy.base import Signal, SignalEvent

log = structlog.get_logger()


@dataclass
class OrderResult:
    order_id: str
    symbol: str
    side: str
    amount: float
    price: float
    status: str


class Broker(Protocol):
    def place_market_order(self, symbol: str, side: str, amount: float) -> OrderResult: ...


class PaperBroker:
    """Broker simulé pour le paper trading — aucun ordre réel envoyé."""

    def place_market_order(self, symbol: str, side: str, amount: float) -> OrderResult:
        log.info("paper_order", symbol=symbol, side=side, amount=amount)
        return OrderResult(
            order_id="paper-0",
            symbol=symbol,
            side=side,
            amount=amount,
            price=0.0,
            status="filled",
        )


class ExecutionEngine:
    def __init__(self, broker: Broker):
        self._broker = broker

    def execute(self, event: SignalEvent, amount: float) -> OrderResult | None:
        if event.signal == Signal.HOLD:
            return None

        side = "buy" if event.signal == Signal.BUY else "sell"
        result = self._broker.place_market_order(event.symbol, side, amount)
        log.info("order_executed", result=result)
        return result
