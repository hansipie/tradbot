import redis

from tradbot.risk.manager import Portfolio


_KEY_PREFIX = "tradbot:portfolio"


def _key(symbol: str) -> str:
    return f"{_KEY_PREFIX}:{symbol.replace('/', '_')}"


class PortfolioStore:
    def __init__(self, redis_url: str):
        self._r = redis.from_url(redis_url, decode_responses=True)

    def save(self, portfolio: Portfolio, symbol: str) -> None:
        self._r.hset(_key(symbol), mapping={
            "capital": float(portfolio.capital),
            "peak_capital": float(portfolio.peak_capital),
            "position": float(portfolio.position),
            "trades_this_hour": int(portfolio.trades_this_hour),
        })

    def load(self, symbol: str) -> Portfolio | None:
        data = self._r.hgetall(_key(symbol))
        if not data:
            return None
        try:
            return Portfolio(
                capital=float(data["capital"]),
                peak_capital=float(data["peak_capital"]),
                position=float(data["position"]),
                trades_this_hour=int(data["trades_this_hour"]),
            )
        except (ValueError, KeyError):
            self._r.delete(_key(symbol))
            return None
