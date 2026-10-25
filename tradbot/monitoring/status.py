import hmac
import json
import threading
from collections.abc import Callable
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import structlog

from tradbot.swaps.payload import PayloadError, parse_swaps
from tradbot.swaps.evaluator import Swap

log = structlog.get_logger()

_state: dict = {}
_MAX_BODY = 1_000_000


def get_state() -> dict:
    return dict(_state)


def update_state(**kwargs) -> None:
    _state.update(kwargs)
    _state["last_tick"] = datetime.now(timezone.utc).isoformat()


def _make_handler(api_token: str, on_swaps: Callable[[list[Swap]], None] | None):
    class _Handler(BaseHTTPRequestHandler):
        timeout = 10  # coupe les clients qui n'envoient pas leur corps

        def _reply(self, code: int, body: dict | None = None) -> None:
            payload = json.dumps(body if body is not None else {}, default=str).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def _authorized(self) -> bool:
            header = self.headers.get("Authorization", "")
            scheme, _, token = header.partition(" ")
            return scheme == "Bearer" and hmac.compare_digest(token.encode(), api_token.encode())

        def do_GET(self) -> None:
            if self.path != "/status":
                self._reply(404)
                return
            if api_token and not self._authorized():
                self._reply(401)
                return
            self._reply(200, _state)

        def do_POST(self) -> None:
            if self.path != "/swaps" or not api_token or on_swaps is None:
                self._reply(404)
                return
            if not self._authorized():
                self._reply(401)
                return
            try:
                length = int(self.headers.get("Content-Length", ""))
            except ValueError:
                self._reply(411)
                return
            if length <= 0 or length > _MAX_BODY:
                self._reply(413)
                return
            try:
                swaps = parse_swaps(json.loads(self.rfile.read(length)))
            except (json.JSONDecodeError, UnicodeDecodeError):
                self._reply(400, {"error": "JSON invalide"})
                return
            except PayloadError as exc:
                self._reply(422, {"error": str(exc)})
                return
            try:
                on_swaps(swaps)
            except Exception as exc:
                log.error("swaps_push_failed", error=str(exc))
                self._reply(500)
                return
            log.info("swaps_received", count=len(swaps))
            self._reply(200, {"received": len(swaps)})

        def log_message(self, format: str, *args: object) -> None:
            pass  # silence HTTP access logs

    return _Handler


def start_status_server(
    port: int,
    api_token: str = "",
    on_swaps: Callable[[list[Swap]], None] | None = None,
) -> None:
    server = ThreadingHTTPServer(("0.0.0.0", port), _make_handler(api_token, on_swaps))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    log.info("status_server_started", port=port, swaps_push=bool(api_token and on_swaps))
