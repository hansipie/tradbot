from dataclasses import dataclass, field
from pathlib import Path
from dotenv import load_dotenv
import os

load_dotenv()


@dataclass
class ExchangeConfig:
    id: str = "binance"
    api_key: str = field(default_factory=lambda: os.getenv("EXCHANGE_API_KEY", ""))
    api_secret: str = field(default_factory=lambda: os.getenv("EXCHANGE_API_SECRET", ""))
    sandbox: bool = True


@dataclass
class RiskConfig:
    max_position_pct: float = 0.02
    max_drawdown_pct: float = 0.10
    max_trades_per_hour: int = 10


@dataclass
class Config:
    exchange: ExchangeConfig = field(default_factory=ExchangeConfig)
    risk: RiskConfig = field(default_factory=RiskConfig)
    symbol: str = "BTC/USDT"
    timeframe: str = "1d"
    history_since: str = "2018-01-01"
    redis_url: str = field(default_factory=lambda: os.getenv("REDIS_URL", "redis://localhost:6379"))
    postgres_url: str = field(default_factory=lambda: os.getenv(
        "POSTGRES_URL", "postgresql://tradbot:tradbot@localhost:5432/tradbot"
    ))

    @property
    def data_file(self) -> Path:
        slug = self.symbol.replace("/", "_")
        return Path("data/historical") / f"{slug}_{self.timeframe}.parquet"
