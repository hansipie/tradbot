from tradbot.config import Config
from tradbot.monitoring.logger import setup_logging
from tradbot.data.feed import CcxtFeed
from tradbot.strategy.dual_ma import DualMACrossover
from tradbot.risk.manager import RiskManager, Portfolio
from tradbot.execution.engine import ExecutionEngine, PaperBroker
import structlog

log = structlog.get_logger()


def main() -> None:
    setup_logging()
    cfg = Config()

    feed = CcxtFeed(cfg.exchange.id, cfg.exchange.api_key, cfg.exchange.api_secret, cfg.exchange.sandbox)
    strategy = DualMACrossover(fast=50, slow=200)
    risk = RiskManager(cfg.risk)
    broker = PaperBroker()
    engine = ExecutionEngine(broker)
    portfolio = Portfolio(capital=10_000.0, peak_capital=10_000.0)

    log.info("bot_started", symbol=cfg.symbol, timeframe=cfg.timeframe)

    df = feed.fetch_ohlcv(cfg.symbol, cfg.timeframe, limit=500)
    raw_signal = strategy.on_data(df)
    raw_signal.symbol = cfg.symbol
    validated = risk.validate(raw_signal, portfolio)

    log.info("signal", raw=raw_signal.signal.value, validated=validated.signal.value, reason=validated.reason)

    if validated.signal.value != "HOLD":
        amount = risk.position_size(portfolio.capital, validated.price)
        engine.execute(validated, amount)


if __name__ == "__main__":
    main()
