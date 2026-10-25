from pathlib import Path

import psycopg

_SCHEMA = Path(__file__).parent / "schema.sql"


class PgStore:
    def __init__(self, postgres_url: str):
        self._url = postgres_url

    def init_schema(self) -> None:
        with psycopg.connect(self._url) as conn:
            conn.execute(_SCHEMA.read_text())
            conn.commit()
