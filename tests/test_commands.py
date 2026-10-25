from tradbot.monitoring.commands import render_command

STATE = {
    "last_tick": "2026-01-01T00:00:00+00:00",
    "open_swaps": 2,
    "rate_errors": 0,
    "min_gain": 0.02,
    "swaps": [
        {"id": 1, "pair": "ETH/BTC", "rate": 0.05, "gain": 0.031, "feasible": True},
        {"id": 2, "pair": "SOL/ETH", "rate": 0.07, "gain": -0.004, "feasible": False},
    ],
}


def test_help_lists_commands():
    assert "/swaps" in render_command("/help", {})
    assert render_command("/start", {}) == render_command("/help", {})


def test_status_without_data_yet():
    assert "Aucune vérification" in render_command("/status", {})


def test_status_shows_counts():
    out = render_command("/status", STATE)
    assert "Swaps ouverts : 2" in out
    assert "2.0%" in out


def test_swaps_lists_each_pair():
    out = render_command("/swaps", STATE)
    assert "✅ ETH/BTC : +3.10%" in out
    assert "▫️ SOL/ETH : -0.40%" in out


def test_swaps_empty():
    assert render_command("/swaps", {"swaps": []}) == "Aucun swap ouvert."


def test_bot_suffix_and_case_ignored():
    assert render_command("/Swaps@tradbot_bot", STATE) == render_command("/swaps", STATE)


def test_unknown_or_plain_text_ignored():
    assert render_command("/nope", STATE) is None
    assert render_command("bonjour", STATE) is None
    assert render_command("", STATE) is None
