import math
import signal
import time
from datetime import datetime, timezone
from pathlib import Path

import structlog

from tradbot.config import Config
from tradbot.data.feed import CcxtFeed
from tradbot.execution.engine import ExecutionEngine, PaperBroker
from tradbot.monitoring.alerter import Alerter
from tradbot.monitoring.logger import setup_logging
from tradbot.monitoring.status import start_status_server, update_state
from tradbot.risk.manager import Portfolio, RiskManager
from tradbot.storage import PgStore, PortfolioStore
from tradbot.strategy.base import Signal
from tradbot.strategy.dual_ma import DualMACrossover

log = structlog.get_logger()

_running = True
_SENTINEL = Path("/tmp/tradbot.stop")


def _handle_signal(signum, frame) -> None:
    global _running
    log.info("shutdown_requested", signum=signum)
    _running = False


def _timeframe_seconds(tf: str) -> int:
    units = {"m": 60, "h": 3600, "d": 86400, "w": 604800}
    return int(tf[:-1]) * units[tf[-1]]


def _seconds_to_next_candle(interval: int) -> float:
    now = time.time()
    next_open = math.ceil(now / interval) * interval
    return next_open - now + 5  # +5s pour que la bougie soit bien fermée côté exchange


def _tick(feed, strategy, risk, engine, portfolio, symbol, cfg, portfolio_store, pg, alerter, proximity_alerted: set) -> None:
    df = feed.fetch_ohlcv(symbol, cfg.timeframe, limit=500)
    price = df["close"].iloc[-1]

    market_block = risk.check_market(df, symbol)
    if market_block is not None:
        log.info("market_blocked", symbol=symbol, reason=market_block.reason)
        update_state(
            symbol=symbol,
            capital=round(portfolio.capital, 2),
            position=portfolio.position,
            portfolio_value=round(portfolio.capital + portfolio.position * price, 2),
            peak_capital=round(portfolio.peak_capital, 2),
            drawdown=0.0,
            last_signal=market_block.signal.value,
            last_price=price,
        )
        return

    prox = strategy.crossover_proximity(df)
    if prox is not None:
        direction, bars = prox
        alert_key = f"{symbol}:{direction}"
        if alert_key not in proximity_alerted:
            alerter.crossover_imminent(symbol, direction, bars, cfg.timeframe)
            proximity_alerted.add(alert_key)
    else:
        proximity_alerted.discard(f"{symbol}:BUY")
        proximity_alerted.discard(f"{symbol}:SELL")

    raw = strategy.on_data(df)
    raw.symbol = symbol
    validated = risk.validate(raw, portfolio)

    log.info("signal", symbol=symbol, raw=raw.signal.value, validated=validated.signal.value, reason=validated.reason)

    if raw.signal != Signal.HOLD and validated.signal == Signal.HOLD:
        if "drawdown" in validated.reason:
            drawdown = (portfolio.peak_capital - portfolio.capital) / portfolio.peak_capital
            alerter.drawdown_limit(drawdown)

    if validated.signal != Signal.HOLD:
        amount = risk.position_size(portfolio.capital, validated.price)
        engine.execute(validated, amount)
        portfolio.trades_this_hour += 1

        if validated.signal == Signal.BUY:
            portfolio.capital -= amount * validated.price
            portfolio.position += amount
        elif validated.signal == Signal.SELL:
            portfolio.capital += portfolio.position * validated.price
            portfolio.position = 0.0

        portfolio.peak_capital = max(portfolio.peak_capital, portfolio.capital)
        pg.record_trade(validated, amount, portfolio.capital, portfolio.position)
        portfolio_store.save(portfolio, symbol)
        alerter.trade(validated.signal.value, validated.symbol, validated.price, portfolio.capital)

    pg.record_equity(df.index[-1], portfolio.capital, portfolio.position * price)

    update_state(
        symbol=symbol,
        capital=round(portfolio.capital, 2),
        position=portfolio.position,
        portfolio_value=round(portfolio.capital + portfolio.position * price, 2),
        peak_capital=round(portfolio.peak_capital, 2),
        drawdown=round((portfolio.peak_capital - portfolio.capital) / portfolio.peak_capital, 4)
        if portfolio.peak_capital > 0 else 0.0,
        last_signal=validated.signal.value,
        last_price=price,
    )


def main() -> None:
    global _running
    setup_logging()
    cfg = Config()

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)
    _SENTINEL.unlink(missing_ok=True)

    alerter = Alerter(cfg.monitor.telegram_token, cfg.monitor.telegram_chat_id)
    start_status_server(cfg.monitor.status_port)

    portfolio_store = PortfolioStore(cfg.redis_url)
    pg = PgStore(cfg.postgres_url)
    pg.init_schema()

    feed = CcxtFeed(cfg.exchange.id, cfg.exchange.api_key, cfg.exchange.api_secret, cfg.exchange.sandbox)
    risk = RiskManager(cfg.risk)
    engine = ExecutionEngine(PaperBroker())

    # État par paire : portfolio + stratégie indépendants
    per_symbol: dict[str, tuple[Portfolio, DualMACrossover]] = {}
    for sym in cfg.symbols:
        portfolio = portfolio_store.load(sym) or Portfolio(capital=10_000.0, peak_capital=10_000.0)
        log.info("portfolio_loaded", symbol=sym, capital=portfolio.capital, position=portfolio.position)
        per_symbol[sym] = (portfolio, DualMACrossover(fast=50, slow=200))

    interval = _timeframe_seconds(cfg.timeframe)
    current_hour = datetime.now(timezone.utc).hour
    consecutive_errors = 0
    proximity_alerted: set[str] = set()

    log.info("bot_started", symbols=cfg.symbols, timeframe=cfg.timeframe, interval_s=interval)
    for sym, (portfolio, _) in per_symbol.items():
        alerter.bot_started(sym, portfolio.capital)

    while _running and not _SENTINEL.exists():
        now_hour = datetime.now(timezone.utc).hour
        if now_hour != current_hour:
            for portfolio, _ in per_symbol.values():
                portfolio.trades_this_hour = 0
            current_hour = now_hour

        try:
            for sym, (portfolio, strategy) in per_symbol.items():
                _tick(feed, strategy, risk, engine, portfolio, sym, cfg, portfolio_store, pg, alerter, proximity_alerted)
            consecutive_errors = 0
        except Exception as exc:
            consecutive_errors += 1
            log.error("tick_error", error=str(exc), consecutive=consecutive_errors)
            if consecutive_errors >= cfg.monitor.error_alert_threshold:
                alerter.consecutive_errors(consecutive_errors, str(exc))
            deadline = time.monotonic() + 60
            while _running and time.monotonic() < deadline:
                time.sleep(1)
            continue

        sleep_s = _seconds_to_next_candle(interval)
        log.info("sleeping_until_next_candle", seconds=round(sleep_s))
        deadline = time.monotonic() + sleep_s
        while _running and not _SENTINEL.exists() and time.monotonic() < deadline:
            time.sleep(1)

    alerter.bot_stopped()
    log.info("bot_stopped")


if __name__ == "__main__":
    main()
