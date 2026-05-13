import redis

from tradbot.risk.manager import Portfolio


_KEY = "tradbot:portfolio"


class PortfolioStore:
    def __init__(self, redis_url: str):
        self._r = redis.from_url(redis_url, decode_responses=True)

    def save(self, portfolio: Portfolio) -> None:
        self._r.hset(_KEY, mapping={
            "capital": portfolio.capital,
            "peak_capital": portfolio.peak_capital,
            "position": portfolio.position,
            "trades_this_hour": portfolio.trades_this_hour,
        })

    def load(self) -> Portfolio | None:
        data = self._r.hgetall(_KEY)
        if not data:
            return None
        return Portfolio(
            capital=float(data["capital"]),
            peak_capital=float(data["peak_capital"]),
            position=float(data["position"]),
            trades_this_hour=int(data["trades_this_hour"]),
        )
