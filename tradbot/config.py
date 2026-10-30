from dataclasses import dataclass, field
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
class MonitorConfig:
    telegram_token: str = field(default_factory=lambda: os.getenv("TELEGRAM_TOKEN", ""))
    telegram_chat_id: str = field(default_factory=lambda: os.getenv("TELEGRAM_CHAT_ID", ""))
    status_port: int = field(default_factory=lambda: int(os.getenv("MONITOR_PORT", "8080")))
    error_alert_threshold: int = 3  # alerter après N erreurs consécutives
    # Messages "démarré"/"arrêté" à chaque redémarrage (NOTIFY_LIFECYCLE=false pour les couper)
    notify_lifecycle: bool = field(
        default_factory=lambda: os.getenv("NOTIFY_LIFECYCLE", "true").lower() in ("1", "true", "yes")
    )


@dataclass
class SwapConfig:
    min_gain: float = field(default_factory=lambda: float(os.getenv("SWAP_MIN_GAIN_PCT", "2")) / 100)
    fee: float = field(default_factory=lambda: float(os.getenv("SWAP_FEE_PCT", "0.5")) / 100)
    check_interval_s: int = field(default_factory=lambda: int(os.getenv("SWAP_CHECK_INTERVAL_MIN", "15")) * 60)
    # Écart sous le seuil à franchir avant de pouvoir ré-alerter le même swap
    rearm_margin: float = 0.005
    # Token Bearer attendu par POST /swaps ; vide = endpoint désactivé
    api_token: str = field(default_factory=lambda: os.getenv("SWAPS_API_TOKEN", ""))
    cryptoupdate_db: str = field(
        default_factory=lambda: os.getenv("CRYPTOUPDATE_DB", "../CryptoUpdate/data/db.sqlite3")
    )


@dataclass
class Config:
    exchange: ExchangeConfig = field(default_factory=ExchangeConfig)
    monitor: MonitorConfig = field(default_factory=MonitorConfig)
    swaps: SwapConfig = field(default_factory=SwapConfig)
    postgres_url: str = field(default_factory=lambda: os.getenv(
        "POSTGRES_URL", "postgresql://tradbot:tradbot@localhost:5432/tradbot"
    ))
