import html
import json
import urllib.request
from datetime import datetime, timezone

import structlog

log = structlog.get_logger()


class Alerter:
    def __init__(self, token: str, chat_id: str):
        self._token = token
        self._chat_id = chat_id
        self._enabled = bool(token and chat_id)

    def _send(self, text: str) -> None:
        if not self._enabled:
            return
        url = f"https://api.telegram.org/bot{self._token}/sendMessage"
        payload = json.dumps({"chat_id": self._chat_id, "text": text, "parse_mode": "HTML"}).encode()
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=5):
                pass
        except Exception as exc:
            log.warning("telegram_alert_failed", error=str(exc))

    def bot_started(self, description: str) -> None:
        self._send(f"🤖 <b>Bot démarré</b>\n{description}")

    def bot_stopped(self) -> None:
        self._send("🛑 <b>Bot arrêté</b>")

    def trade(self, side: str, symbol: str, price: float, capital_after: float) -> None:
        emoji = "🟢" if side == "BUY" else "🔴"
        self._send(
            f"{emoji} <b>{side}</b> {symbol}\n"
            f"Prix : {price:,.2f} $\n"
            f"Capital : {capital_after:,.2f} $"
        )

    def drawdown_limit(self, drawdown: float) -> None:
        self._send(
            f"⚠️ <b>Drawdown max atteint</b>\n"
            f"Drawdown courant : {drawdown:.1%}\n"
            f"Trades suspendus jusqu'à récupération."
        )

    def consecutive_errors(self, count: int, last_error: str) -> None:
        self._send(f"🚨 <b>{count} erreurs consécutives</b>\n{last_error}")

    def swap_feasible(
        self, token_from: str, token_to: str, remaining_to: float, units_back: float,
        cost_from: float, gain: float, swapped_on: str,
    ) -> None:
        self._send(
            f"🔁 <b>Swap faisable : {token_to} → {token_from}</b>\n"
            f"Gain : {gain:+.2%} en {token_from}\n"
            f"Tu rends {remaining_to:.8g} {token_to}\n"
            f"Tu récupères ~{units_back:.8g} {token_from} (départ : {cost_from:.8g}, swap du {swapped_on})"
        )

    def swaps_synced(self, swaps: list, max_listed: int = 10) -> None:
        lines = [f"🔄 <b>Synchronisation des swaps</b>\n{len(swaps)} swap(s) reçu(s)"]
        for s in swaps[:max_listed]:
            date = datetime.fromtimestamp(s.timestamp, timezone.utc).strftime("%d/%m/%Y %H:%M")
            lines.append(
                f"\n#{s.id} · {date}\n"
                f"{s.amount_from:.8g} {html.escape(s.token_from)} ({html.escape(s.wallet_from)}) → "
                f"{s.amount_to:.8g} {html.escape(s.token_to)} ({html.escape(s.wallet_to)})"
            )
        if len(swaps) > max_listed:
            lines.append(f"\n… et {len(swaps) - max_listed} autre(s)")
        self._send("\n".join(lines))

    def crossover_imminent(self, symbol: str, direction: str, bars: float, timeframe: str) -> None:
        emoji = "📈" if direction == "BUY" else "📉"
        self._send(
            f"{emoji} <b>Croisement MA imminent</b>\n"
            f"Symbole : {symbol}\n"
            f"Direction : {direction}\n"
            f"Dans ~{bars:.1f} bougie(s) ({timeframe})"
        )
