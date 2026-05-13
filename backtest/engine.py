from dataclasses import dataclass, field
import pandas as pd
from tradbot.strategy.base import Strategy, Signal


@dataclass
class BacktestResult:
    trades: list[dict] = field(default_factory=list)
    equity: pd.Series = field(default_factory=pd.Series)

    @property
    def cagr(self) -> float:
        if len(self.equity) < 2:
            return 0.0
        years = (self.equity.index[-1] - self.equity.index[0]).days / 365.25
        return (self.equity.iloc[-1] / self.equity.iloc[0]) ** (1 / years) - 1 if years > 0 else 0.0

    @property
    def max_drawdown(self) -> float:
        peak = self.equity.cummax()
        return ((self.equity - peak) / peak).min()

    @property
    def sharpe(self) -> float:
        returns = self.equity.pct_change().dropna()
        if returns.std() == 0:
            return 0.0
        return (returns.mean() / returns.std()) * (252 ** 0.5)

    @property
    def sortino(self) -> float:
        returns = self.equity.pct_change().dropna()
        downside = returns[returns < 0]
        if downside.empty:
            return 0.0
        std = downside.std()
        if pd.isna(std) or std == 0:
            return 0.0
        return (returns.mean() / std) * (252 ** 0.5)

    @property
    def calmar(self) -> float:
        if self.max_drawdown == 0:
            return 0.0
        return self.cagr / abs(self.max_drawdown)

    @property
    def _round_trip_pnl(self) -> list[float]:
        buys = [t for t in self.trades if t["type"] == "buy"]
        sells = [t for t in self.trades if t["type"] == "sell"]
        return [s["capital"] - b["capital_before"] for b, s in zip(buys, sells)]

    @property
    def win_rate(self) -> float:
        pnl = self._round_trip_pnl
        if not pnl:
            return 0.0
        return sum(1 for p in pnl if p > 0) / len(pnl)

    @property
    def profit_factor(self) -> float:
        pnl = self._round_trip_pnl
        gains = sum(p for p in pnl if p > 0)
        losses = abs(sum(p for p in pnl if p < 0))
        if losses == 0:
            return float("inf") if gains > 0 else 0.0
        return gains / losses


def run_backtest(
    df: pd.DataFrame,
    strategy: Strategy,
    initial_capital: float = 10_000.0,
    fee_rate: float = 0.001,
) -> BacktestResult:
    capital = initial_capital
    position = 0.0
    equity_curve: dict[pd.Timestamp, float] = {}
    trades: list[dict] = []

    for i in range(1, len(df)):
        window = df.iloc[: i + 1]
        event = strategy.on_data(window)
        price = df["close"].iloc[i]

        if event.signal == Signal.BUY and position == 0.0:
            capital_before = capital
            units = capital / price
            fee = units * price * fee_rate
            position = units
            capital = 0.0 - fee
            trades.append({"type": "buy", "price": price, "timestamp": df.index[i], "capital_before": capital_before})

        elif event.signal == Signal.SELL and position > 0.0:
            proceeds = position * price
            fee = proceeds * fee_rate
            capital = proceeds - fee
            trades.append({"type": "sell", "price": price, "timestamp": df.index[i], "capital": capital})
            position = 0.0

        equity_curve[df.index[i]] = capital + position * price

    result = BacktestResult(trades=trades, equity=pd.Series(equity_curve))
    return result
