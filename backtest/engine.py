from dataclasses import dataclass, field
import pandas as pd
from tradbot.strategy.base import Strategy, Signal
from tradbot.config import RiskConfig
from tradbot.risk.manager import Portfolio, RiskManager


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
    def _periods_per_year(self) -> float:
        if len(self.equity) < 2:
            return 252.0
        delta = self.equity.index.to_series().diff().median()
        if pd.isna(delta) or delta <= pd.Timedelta(0):
            return 252.0
        return float(pd.Timedelta(days=365.25) / delta)

    @property
    def sharpe(self) -> float:
        returns = self.equity.pct_change().dropna()
        if returns.std() == 0:
            return 0.0
        return (returns.mean() / returns.std()) * (self._periods_per_year ** 0.5)

    @property
    def sortino(self) -> float:
        returns = self.equity.pct_change().dropna()
        downside = returns[returns < 0]
        if downside.empty:
            return 0.0
        std = downside.std()
        if pd.isna(std) or std == 0:
            return 0.0
        return (returns.mean() / std) * (self._periods_per_year ** 0.5)

    @property
    def calmar(self) -> float:
        if self.max_drawdown == 0:
            return 0.0
        return self.cagr / abs(self.max_drawdown)

    @property
    def _round_trip_pnl(self) -> list[float]:
        return [trade["pnl"] for trade in self.trades
                if trade["type"] == "sell" and "pnl" in trade]

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
    slippage_pct: float = 0.001,
    risk: RiskManager | None = None,
    symbol: str = "",
) -> BacktestResult:
    risk = risk or RiskManager(RiskConfig())
    portfolio = Portfolio(capital=initial_capital, peak_capital=initial_capital)
    equity_curve: dict[pd.Timestamp, float] = {}
    trades: list[dict] = []
    cost_basis = 0.0
    current_hour = None

    for i in range(1, len(df)):
        timestamp = df.index[i]
        hour = timestamp.floor("h") if hasattr(timestamp, "floor") else timestamp
        if hour != current_hour:
            portfolio.trades_this_hour = 0
            current_hour = hour

        window = df.iloc[: i + 1]
        price = df["close"].iloc[i]
        market_block = risk.check_market(window, symbol)
        if market_block is not None:
            validated = market_block
        else:
            event = strategy.on_data(window)
            validated = risk.validate(event, portfolio)

        if validated.signal == Signal.BUY and portfolio.capital > 0.0:
            exec_price = price * (1 + slippage_pct)
            if validated.target_size is not None:
                target = min(max(validated.target_size, 0.0), 1.0)
                total = portfolio.capital + portfolio.position * price
                units = max(0.0, total * target / exec_price - portfolio.position)
            else:
                units = risk.position_size(portfolio.capital, exec_price)
            units = min(units, portfolio.capital / (exec_price * (1 + fee_rate)))
            if units > 0:
                gross = units * exec_price
                fee = gross * fee_rate
                portfolio.capital -= gross + fee
                portfolio.position += units
                cost_basis += gross + fee
                portfolio.trades_this_hour += 1
                trades.append({"type": "buy", "price": exec_price, "units": units,
                               "fee": fee, "timestamp": timestamp,
                               "capital_after": portfolio.capital})

        elif validated.signal == Signal.SELL and portfolio.position > 0.0:
            exec_price = price * (1 - slippage_pct)
            if validated.target_size is not None:
                target = min(max(validated.target_size, 0.0), 1.0)
                total = portfolio.capital + portfolio.position * price
                target_units = total * target / exec_price
                units = max(0.0, portfolio.position - target_units)
            else:
                units = portfolio.position
            units = min(units, portfolio.position)
            if units > 0:
                proceeds = units * exec_price
                fee = proceeds * fee_rate
                net_proceeds = proceeds - fee
                sold_fraction = units / portfolio.position
                realized_cost = cost_basis * sold_fraction
                portfolio.capital += net_proceeds
                portfolio.position -= units
                portfolio.trades_this_hour += 1
                trades.append({"type": "sell", "price": exec_price, "units": units,
                               "fee": fee, "timestamp": timestamp,
                               "capital_after": portfolio.capital,
                               "pnl": net_proceeds - realized_cost})
                cost_basis -= realized_cost
                if portfolio.position <= 0.0:
                    portfolio.position = 0.0
                    cost_basis = 0.0

        total = portfolio.capital + portfolio.position * price
        portfolio.peak_capital = max(portfolio.peak_capital, total)
        equity_curve[timestamp] = total

    result = BacktestResult(trades=trades, equity=pd.Series(equity_curve))
    return result
