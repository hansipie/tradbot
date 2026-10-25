"""Copie les swaps de CryptoUpdate (SQLite, lecture seule) vers PostgreSQL.

uv run python scripts/sync_swaps.py [chemin/vers/db.sqlite3]
"""
import sqlite3
import sys
from pathlib import Path

from tradbot.config import Config
from tradbot.storage import PgStore, SwapStore
from tradbot.swaps import Swap


def read_swaps(db_path: Path) -> list[Swap]:
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        rows = conn.execute(
            """
            SELECT id, timestamp, token_from, amount_from, wallet_from,
                   token_to, amount_to, wallet_to
            FROM Swaps
            WHERE token_from IS NOT NULL AND token_to IS NOT NULL
              AND amount_from > 0 AND amount_to > 0
            """
        ).fetchall()
    finally:
        conn.close()
    return [Swap(r[0], int(r[1]), r[2], float(r[3]), r[4], r[5], float(r[6]), r[7]) for r in rows]


def main() -> None:
    cfg = Config()
    db_path = Path(sys.argv[1] if len(sys.argv) > 1 else cfg.swaps.cryptoupdate_db)
    if not db_path.is_file():
        sys.exit(f"Base introuvable : {db_path}")

    swaps = read_swaps(db_path)
    PgStore(cfg.postgres_url).init_schema()
    SwapStore(cfg.postgres_url).upsert_many(swaps)
    print(f"{len(swaps)} swaps synchronisés depuis {db_path}")


if __name__ == "__main__":
    main()
