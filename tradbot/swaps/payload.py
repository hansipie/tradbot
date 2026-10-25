import math

from .evaluator import Swap

MAX_SWAPS = 5000


class PayloadError(ValueError):
    pass


def _text(row: dict, key: str) -> str:
    value = row.get(key)
    if not isinstance(value, str) or not value.strip() or len(value) > 64:
        raise PayloadError(f"{key} invalide")
    return value.strip()


def _positive(row: dict, key: str) -> float:
    value = row.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise PayloadError(f"{key} invalide")
    if not math.isfinite(value) or value <= 0:
        raise PayloadError(f"{key} doit être > 0")
    return float(value)


def parse_swaps(data: object) -> list[Swap]:
    """Valide le corps JSON {"swaps": [...]} envoyé par CryptoUpdate."""
    if not isinstance(data, dict) or not isinstance(data.get("swaps"), list):
        raise PayloadError('attendu : {"swaps": [...]}')
    rows = data["swaps"]
    if len(rows) > MAX_SWAPS:
        raise PayloadError("trop de swaps")

    swaps: dict[int, Swap] = {}
    for row in rows:
        if not isinstance(row, dict):
            raise PayloadError("swap invalide")
        swap_id, ts = row.get("id"), row.get("timestamp")
        if isinstance(swap_id, bool) or not isinstance(swap_id, int):
            raise PayloadError("id invalide")
        if isinstance(ts, bool) or not isinstance(ts, int) or ts <= 0:
            raise PayloadError("timestamp invalide")
        swaps[swap_id] = Swap(
            swap_id,
            ts,
            _text(row, "token_from").upper(),
            _positive(row, "amount_from"),
            _text(row, "wallet_from"),
            _text(row, "token_to").upper(),
            _positive(row, "amount_to"),
            _text(row, "wallet_to"),
        )
    return list(swaps.values())
