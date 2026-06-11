from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from .exceptions import ConfigurationError
from .storage import SCHEMA, SqliteStore


class PostgresStore(SqliteStore):
    """Postgres/Supabase storage adapter.

    The public methods come from `SqliteStore`; this adapter swaps the
    connection implementation and placeholder style. For Supabase on Vercel,
    use the transaction pooler URL and disable prepared statements.
    """

    def __init__(self, database_url: str) -> None:
        self.db_path = database_url
        self.database_url = database_url

    def init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(SCHEMA)

    @contextmanager
    def _connect(self) -> Iterator["_PostgresConnection"]:
        try:
            import psycopg
            from psycopg.rows import dict_row
        except ImportError as exc:
            raise ConfigurationError("Install psycopg to use Supabase/Postgres storage.") from exc

        conn = psycopg.connect(
            self.database_url,
            row_factory=dict_row,
            autocommit=False,
            prepare_threshold=None,
        )
        try:
            yield _PostgresConnection(conn)
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()


class _PostgresConnection:
    def __init__(self, conn) -> None:
        self._conn = conn

    def execute(self, query: str, params=()):
        return self._conn.execute(_convert_placeholders(query), params)

    def executescript(self, script: str) -> None:
        for statement in _split_sql_script(script):
            self._conn.execute(statement)


def _convert_placeholders(query: str) -> str:
    return query.replace("?", "%s")


def _split_sql_script(script: str) -> list[str]:
    return [statement.strip() for statement in script.split(";") if statement.strip()]
