import json
import urllib.request

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

    def bot_started(self, symbol: str, capital: float) -> None:
        self._send(f"🤖 <b>Bot démarré</b>\nSymbole : {symbol}\nCapital : {capital:.2f} $")

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
