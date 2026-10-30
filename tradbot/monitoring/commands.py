import json
import threading
import urllib.request
from collections.abc import Callable

import structlog

log = structlog.get_logger()

_POLL_TIMEOUT_S = 30
_HELP = (
    "<b>Commandes</b>\n"
    "/status — état du bot\n"
    "/swaps — swaps ouverts et gain\n"
    "/clear_swaps — supprime tous les swaps (demande confirmation)\n"
    "/help — cette aide"
)


def render_command(
    text: str, state: dict, clear_swaps: Callable[[], int] | None = None,
) -> str | None:
    """Réponse à une commande Telegram, ou None si ce n'est pas une commande connue."""
    parts = text.strip().split()
    command = parts[0].split("@")[0].lower() if parts else ""

    if command in ("/start", "/help"):
        return _HELP

    if command == "/status":
        if not state:
            return "⏳ Aucune vérification effectuée pour l'instant."
        return (
            "🤖 <b>Bot actif</b>\n"
            f"Dernière vérification : {state.get('last_tick', '?')}\n"
            f"Swaps ouverts : {state.get('open_swaps', 0)}\n"
            f"Prix indisponibles : {state.get('rate_errors', 0)}\n"
            f"Seuil d'alerte : {state.get('min_gain', 0):.1%}"
        )

    if command == "/swaps":
        swaps = state.get("swaps", [])
        if not swaps:
            return "Aucun swap ouvert."
        lines = [
            f"{'✅' if s['feasible'] else '▫️'} {s['pair']} : {s['gain']:+.2%}"
            for s in swaps
        ]
        return "🔁 <b>Swaps ouverts</b>\n" + "\n".join(lines)

    if command == "/clear_swaps" and clear_swaps is not None:
        if [p.lower() for p in parts[1:]] != ["confirm"]:
            return (
                "⚠️ <b>Supprimer tous les swaps ?</b>\n"
                "Ils seront de nouveau copiés à la prochaine synchronisation.\n"
                "Confirme avec : /clear_swaps confirm"
            )
        return f"🗑 {clear_swaps()} swap(s) supprimé(s)."

    return None


def _api(token: str, method: str, payload: dict, timeout: float) -> dict:
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/{method}",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.load(resp)


def _poll(
    token: str, chat_id: str, get_state: Callable[[], dict],
    clear_swaps: Callable[[], int] | None,
) -> None:
    offset = 0
    while True:
        try:
            data = _api(
                token, "getUpdates",
                {"offset": offset, "timeout": _POLL_TIMEOUT_S, "allowed_updates": ["message"]},
                _POLL_TIMEOUT_S + 10,
            )
            for update in data.get("result", []):
                offset = update["update_id"] + 1
                msg = update.get("message") or {}
                # Seul le chat configuré peut interroger le bot
                if str(msg.get("chat", {}).get("id")) != chat_id:
                    continue
                reply = render_command(msg.get("text", ""), get_state(), clear_swaps)
                if reply:
                    _api(token, "sendMessage",
                         {"chat_id": chat_id, "text": reply, "parse_mode": "HTML"}, 10)
        except Exception as exc:
            log.warning("telegram_poll_failed", error=str(exc))
            threading.Event().wait(10)


def start_command_listener(
    token: str, chat_id: str, get_state: Callable[[], dict],
    clear_swaps: Callable[[], int] | None = None,
) -> None:
    if not (token and chat_id):
        return
    threading.Thread(target=_poll, args=(token, chat_id, get_state, clear_swaps), daemon=True).start()
    log.info("command_listener_started")
