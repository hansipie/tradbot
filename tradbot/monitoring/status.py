import json
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer

import structlog

log = structlog.get_logger()

_state: dict = {}


def update_state(**kwargs) -> None:
    _state.update(kwargs)
    _state["last_tick"] = datetime.now(timezone.utc).isoformat()


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path != "/status":
            self.send_response(404)
            self.end_headers()
            return
        body = json.dumps(_state, default=str).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        pass  # silence HTTP access logs


def start_status_server(port: int) -> None:
    server = HTTPServer(("0.0.0.0", port), _Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    log.info("status_server_started", port=port)
