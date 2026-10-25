import http.client
import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

from tradbot.monitoring.status import _make_handler
from tradbot.swaps.payload import PayloadError, parse_swaps

ROW = {
    "id": 1, "timestamp": 1788505800,
    "token_from": "sol", "amount_from": 1.44, "wallet_from": "Swissborg",
    "token_to": "USDC", "amount_to": 147.8, "wallet_to": "Swissborg",
}


def test_parse_swaps_normalizes_tokens():
    swaps = parse_swaps({"swaps": [ROW]})
    assert swaps[0].token_from == "SOL"
    assert swaps[0].amount_to == pytest.approx(147.8)


def test_parse_swaps_accepts_empty_list():
    assert parse_swaps({"swaps": []}) == []


def test_parse_swaps_dedupes_by_id():
    assert len(parse_swaps({"swaps": [ROW, dict(ROW, amount_from=2.0)]})) == 1


@pytest.mark.parametrize("bad", [
    [],
    {"swaps": "x"},
    {"swaps": [{"id": 1}]},
    {"swaps": [dict(ROW, amount_from=0)]},
    {"swaps": [dict(ROW, amount_from=-1)]},
    {"swaps": [dict(ROW, amount_from=float("nan"))]},
    {"swaps": [dict(ROW, amount_from="1.4")]},
    {"swaps": [dict(ROW, amount_from=True)]},
    {"swaps": [dict(ROW, id="1")]},
    {"swaps": [dict(ROW, timestamp=0)]},
    {"swaps": [dict(ROW, token_to="")]},
    {"swaps": [dict(ROW, wallet_to="x" * 65)]},
])
def test_parse_swaps_rejects_invalid(bad):
    with pytest.raises(PayloadError):
        parse_swaps(bad)


@pytest.fixture
def server():
    received = []
    srv = ThreadingHTTPServer(("127.0.0.1", 0), _make_handler("secret", received.extend))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_port}", received
    srv.shutdown()


def _post(url, body, token="secret"):
    headers = {"Content-Type": "application/json"}
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    data = body if isinstance(body, bytes) else json.dumps(body).encode()
    req = urllib.request.Request(f"{url}/swaps", data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status
    except urllib.error.HTTPError as exc:
        return exc.code


def test_push_ok(server):
    url, received = server
    assert _post(url, {"swaps": [ROW]}) == 200
    assert [s.id for s in received] == [1]


def test_push_requires_valid_token(server):
    url, received = server
    assert _post(url, {"swaps": [ROW]}, token="wrong") == 401
    assert _post(url, {"swaps": [ROW]}, token=None) == 401
    assert received == []


def test_push_rejects_bad_json_and_payload(server):
    url, received = server
    assert _post(url, b"not json") == 400
    assert _post(url, {"swaps": [dict(ROW, amount_from=-1)]}) == 422
    assert received == []


def test_push_rejects_oversized_body(server):
    url, received = server
    # Seul l'en-tête annonce un corps trop gros : le serveur doit refuser sans le lire
    conn = http.client.HTTPConnection(url.removeprefix("http://"), timeout=5)
    conn.putrequest("POST", "/swaps")
    conn.putheader("Authorization", "Bearer secret")
    conn.putheader("Content-Length", "1000001")
    conn.endheaders()
    assert conn.getresponse().status == 413
    conn.close()
    assert received == []


def test_push_disabled_without_token():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), _make_handler("", lambda s: None))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        assert _post(f"http://127.0.0.1:{srv.server_port}", {"swaps": [ROW]}, token="") == 404
    finally:
        srv.shutdown()


def test_status_still_served(server):
    url, _ = server
    with urllib.request.urlopen(f"{url}/status", timeout=5) as resp:
        assert resp.status == 200
