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
    sandbox: bool = False


@dataclass
class RiskConfig:
    max_position_pct: float = 0.02
    max_drawdown_pct: float = 0.10
    max_trades_per_hour: int = 10
    max_exposure_pct: float = 0.95      # position value / total portfolio max
    min_volume_factor: float = 0.1      # volume min = factor × moyenne 20 bougies


@dataclass
class MonitorConfig:
    telegram_token: str = field(default_factory=lambda: os.getenv("TELEGRAM_TOKEN", ""))
    telegram_chat_id: str = field(default_factory=lambda: os.getenv("TELEGRAM_CHAT_ID", ""))
    status_port: int = field(default_factory=lambda: int(os.getenv("MONITOR_PORT", "8080")))
    error_alert_threshold: int = 3  # alerter après N erreurs consécutives


@dataclass
class Config:
    exchange: ExchangeConfig = field(default_factory=ExchangeConfig)
    risk: RiskConfig = field(default_factory=RiskConfig)
    monitor: MonitorConfig = field(default_factory=MonitorConfig)
    symbols: list[str] = field(
        default_factory=lambda: [s.strip() for s in os.getenv("SYMBOLS", "BTC/USDC").split(",")]
    )
    timeframe: str = "1d"
    history_since: str = "2018-01-01"
    redis_url: str = field(default_factory=lambda: os.getenv("REDIS_URL", "redis://localhost:6379"))
    postgres_url: str = field(default_factory=lambda: os.getenv(
        "POSTGRES_URL", "postgresql://tradbot:tradbot@localhost:5432/tradbot"
    ))

    def data_file(self, symbol: str) -> Path:
        slug = symbol.replace("/", "_")
        return Path("data/historical") / f"{slug}_{self.timeframe}.parquet"
