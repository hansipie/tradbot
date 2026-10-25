from dataclasses import dataclass
from typing import Protocol

import pandas as pd

_EPS = 1e-9


@dataclass(frozen=True)
class Swap:
    id: int
    timestamp: int
    token_from: str
    amount_from: float
    wallet_from: str
    token_to: str
    amount_to: float
    wallet_to: str


@dataclass(frozen=True)
class OpenPosition:
    """Part d'un swap dont le token reçu n'a pas encore été dépensé."""

    swap: Swap
    remaining_to: float  # quantité de token_to encore détenue
    cost_from: float     # quantité de token_from correspondante à cette part

    @property
    def symbol(self) -> str:
        """Paire dont le prix donne des token_from par token_to."""
        return f"{self.swap.token_to}/{self.swap.token_from}"


@dataclass(frozen=True)
class SwapOpportunity:
    position: OpenPosition
    rate: float        # token_from reçus pour 1 token_to
    units_back: float  # token_from récupérés après frais en swappant tout le reste
    gain: float        # units_back / cost_from - 1


class PriceFeed(Protocol):
    def fetch_ohlcv(self, symbol: str, timeframe: str, limit: int) -> pd.DataFrame: ...


def open_positions(swaps: list[Swap]) -> list[OpenPosition]:
    """Swaps dont le token reçu est encore détenu, en consommant les lots FIFO.

    Une dépense ultérieure de token_to depuis le même wallet (retour vers token_from
    ou swap vers un 3e token) ferme d'abord les swaps les plus anciens. Une
    dépense partielle ne ferme qu'une partie du swap.
    """
    lots: dict[tuple[str, str], list[list]] = {}  # (wallet, token) -> [[swap, remaining_to]]
    for swap in sorted(swaps, key=lambda s: (s.timestamp, s.id)):
        to_spend = swap.amount_from
        for lot in lots.get((swap.wallet_from, swap.token_from), []):
            if to_spend <= _EPS:
                break
            used = min(lot[1], to_spend)
            lot[1] -= used
            to_spend -= used
        lots.setdefault((swap.wallet_to, swap.token_to), []).append([swap, swap.amount_to])

    positions = []
    for wallet_lots in lots.values():
        for swap, remaining in wallet_lots:
            if remaining > _EPS * max(swap.amount_to, 1.0) and swap.amount_to > 0:
                positions.append(
                    OpenPosition(swap, remaining, swap.amount_from * remaining / swap.amount_to)
                )
    return sorted(positions, key=lambda p: p.swap.timestamp)


def evaluate(position: OpenPosition, rate: float, fee: float) -> SwapOpportunity:
    units_back = position.remaining_to * rate * (1.0 - fee)
    gain = units_back / position.cost_from - 1.0 if position.cost_from > 0 else 0.0
    return SwapOpportunity(position, rate, units_back, gain)


def current_rate(feed: PriceFeed, position: OpenPosition) -> float:
    df = feed.fetch_ohlcv(position.symbol, "1h", limit=2)
    return float(df["close"].iloc[-1])
