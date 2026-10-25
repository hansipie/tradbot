import psycopg

from tradbot.swaps.evaluator import Swap


class SwapStore:
    """Copie PostgreSQL des swaps de CryptoUpdate (clé = id source)."""

    def __init__(self, postgres_url: str):
        self._url = postgres_url

    def upsert_many(self, swaps: list[Swap]) -> None:
        with psycopg.connect(self._url) as conn:
            conn.cursor().executemany(
                """
                INSERT INTO swaps (id, ts, token_from, amount_from, wallet_from,
                                   token_to, amount_to, wallet_to)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET
                    ts = EXCLUDED.ts,
                    token_from = EXCLUDED.token_from,
                    amount_from = EXCLUDED.amount_from,
                    wallet_from = EXCLUDED.wallet_from,
                    token_to = EXCLUDED.token_to,
                    amount_to = EXCLUDED.amount_to,
                    wallet_to = EXCLUDED.wallet_to
                """,
                [
                    (s.id, s.timestamp, s.token_from, s.amount_from, s.wallet_from,
                     s.token_to, s.amount_to, s.wallet_to)
                    for s in swaps
                ],
            )
            # Un swap supprimé dans CryptoUpdate disparaît aussi de la copie
            conn.execute("DELETE FROM swaps WHERE id <> ALL(%s::int[])", ([s.id for s in swaps],))
            conn.commit()

    def load_all(self) -> list[Swap]:
        with psycopg.connect(self._url) as conn:
            rows = conn.execute(
                """
                SELECT id, ts, token_from, amount_from, wallet_from,
                       token_to, amount_to, wallet_to
                FROM swaps ORDER BY ts, id
                """
            ).fetchall()
        return [
            Swap(r[0], int(r[1]), r[2], float(r[3]), r[4], r[5], float(r[6]), r[7])
            for r in rows
        ]
