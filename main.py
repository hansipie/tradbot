import signal
import time
from datetime import datetime, timezone
from pathlib import Path

import structlog

from tradbot.config import Config, SwapConfig
from tradbot.data.feed import CcxtFeed
from tradbot.monitoring.alerter import Alerter
from tradbot.monitoring.logger import setup_logging
from tradbot.monitoring.status import start_status_server, update_state
from tradbot.storage import PgStore, SwapStore
from tradbot.swaps import current_rate, evaluate, open_positions

log = structlog.get_logger()

_running = True
_SENTINEL = Path("/tmp/tradbot.stop")


def _handle_signal(signum, frame) -> None:
    global _running
    log.info("shutdown_requested", signum=signum)
    _running = False


def _check_swaps(feed, store: SwapStore, alerter: Alerter, cfg: SwapConfig, alerted: set[int]) -> int:
    """Évalue chaque swap ouvert et alerte quand le gain franchit le seuil.

    Retourne le nombre de positions dont le prix n'a pas pu être lu.
    """
    positions = open_positions(store.load_all())
    errors = 0
    opportunities = []

    for pos in positions:
        swap_id = pos.swap.id
        try:
            opp = evaluate(pos, current_rate(feed, pos), cfg.fee)
        except Exception as exc:
            errors += 1
            log.warning("swap_rate_unavailable", swap_id=swap_id, symbol=pos.symbol, error=str(exc))
            continue

        opportunities.append(opp)
        log.info("swap_checked", swap_id=swap_id, symbol=pos.symbol, rate=opp.rate, gain=round(opp.gain, 4))

        if opp.gain >= cfg.min_gain:
            if swap_id not in alerted:
                alerter.swap_feasible(
                    pos.swap.token_from, pos.swap.token_to, pos.remaining_to, opp.units_back,
                    pos.cost_from, opp.gain,
                    datetime.fromtimestamp(pos.swap.timestamp, timezone.utc).strftime("%d/%m/%Y"),
                )
                alerted.add(swap_id)
        elif opp.gain < cfg.min_gain - cfg.rearm_margin:
            alerted.discard(swap_id)

    # Les swaps refermés ne doivent plus rester en mémoire
    alerted &= {p.swap.id for p in positions}

    update_state(
        open_swaps=len(positions),
        rate_errors=errors,
        min_gain=cfg.min_gain,
        swaps=[
            {
                "id": o.position.swap.id,
                "pair": o.position.symbol,
                "rate": o.rate,
                "gain": round(o.gain, 4),
                "feasible": o.gain >= cfg.min_gain,
            }
            for o in sorted(opportunities, key=lambda o: o.gain, reverse=True)
        ],
    )
    return errors


def main() -> None:
    global _running
    setup_logging()
    cfg = Config()

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)
    _SENTINEL.unlink(missing_ok=True)

    alerter = Alerter(cfg.monitor.telegram_token, cfg.monitor.telegram_chat_id)

    PgStore(cfg.postgres_url).init_schema()
    store = SwapStore(cfg.postgres_url)
    start_status_server(cfg.monitor.status_port, cfg.swaps.api_token, store.upsert_many)
    feed = CcxtFeed(cfg.exchange.id, cfg.exchange.api_key, cfg.exchange.api_secret, cfg.exchange.sandbox)

    alerted: set[int] = set()
    consecutive_errors = 0

    log.info(
        "bot_started",
        min_gain=cfg.swaps.min_gain,
        fee=cfg.swaps.fee,
        interval_s=cfg.swaps.check_interval_s,
    )
    alerter.bot_started(f"surveillance des swaps (seuil {cfg.swaps.min_gain:.1%})")

    while _running and not _SENTINEL.exists():
        wait_s = cfg.swaps.check_interval_s
        try:
            _check_swaps(feed, store, alerter, cfg.swaps, alerted)
            consecutive_errors = 0
        except Exception as exc:
            consecutive_errors += 1
            log.error("check_error", error=str(exc), consecutive=consecutive_errors)
            if consecutive_errors >= cfg.monitor.error_alert_threshold:
                alerter.consecutive_errors(consecutive_errors, str(exc))
            wait_s = 60

        deadline = time.monotonic() + wait_s
        while _running and not _SENTINEL.exists() and time.monotonic() < deadline:
            time.sleep(1)

    alerter.bot_stopped()
    log.info("bot_stopped")


if __name__ == "__main__":
    main()
