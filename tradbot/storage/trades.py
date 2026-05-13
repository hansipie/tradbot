from pathlib import Path

import pandas as pd
import psycopg

from tradbot.strategy.base import SignalEvent

_SCHEMA = Path(__file__).parent / "schema.sql"


class PgStore:
    def __init__(self, postgres_url: str):
        self._url = postgres_url

    def init_schema(self) -> None:
        with psycopg.connect(self._url) as conn:
            conn.execute(_SCHEMA.read_text())
            conn.commit()

    def record_trade(
        self,
        event: SignalEvent,
        amount: float,
        capital_after: float,
        position_after: float,
    ) -> None:
        with psycopg.connect(self._url) as conn:
            conn.execute(
                """
                INSERT INTO trades (symbol, side, price, amount, capital_after, position_after, reason, ts)
                VALUES (%s, %s, %s, %s, %s, %s, %s, now())
                """,
                (event.symbol, event.signal.value, event.price, amount,
                 capital_after, position_after, event.reason),
            )
            conn.commit()

    def record_equity(
        self,
        ts: pd.Timestamp,
        capital: float,
        position_value: float,
    ) -> None:
        with psycopg.connect(self._url) as conn:
            conn.execute(
                """
                INSERT INTO equity (ts, capital, position_value, total)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (ts) DO UPDATE
                SET capital = EXCLUDED.capital,
                    position_value = EXCLUDED.position_value,
                    total = EXCLUDED.total
                """,
                (ts, capital, position_value, capital + position_value),
            )
            conn.commit()
