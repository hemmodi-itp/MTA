"""
PostgresConnector — DBConnector backed by psycopg 3.

Reads the connection string from DATABASE_URL (the same variable the Next.js
frontend's Prisma client uses). Prisma-only query parameters such as
`?schema=public` are stripped, since libpq rejects them.

Connections come from a small process-wide pool (one per database URL): the
pipeline writes from several threads at once (DAG steps run concurrently, the
heartbeat, the executor's per-test updates), and opening a TCP connection per
statement was the dominant cost of those writes. Each `connection()` block is
one transaction — committed on success, rolled back on error. Broken
connections are dropped instead of returned to the pool.

Tuning: AQP_DB_POOL_SIZE (default 8 idle connections kept), AQP_DB_CONNECT_TIMEOUT_S (default 10).
"""

import os
import queue
import threading
from contextlib import contextmanager
from typing import Any, Dict, Iterator, List, Optional
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from connectors.db.base import DBConnector

# Query params Prisma understands but libpq does not.
_PRISMA_ONLY_PARAMS = {"schema", "connection_limit", "pool_timeout", "pgbouncer", "socket_timeout"}

_pools: Dict[str, "_Pool"] = {}
_pools_lock = threading.Lock()


def normalize_database_url(url: str) -> str:
    """Drop Prisma-specific query params so psycopg accepts the URL."""
    parts = urlsplit(url)
    kept = [(k, v) for k, v in parse_qsl(parts.query) if k not in _PRISMA_ONLY_PARAMS]
    return urlunsplit(parts._replace(query=urlencode(kept)))


class _Pool:
    """LIFO pool of idle connections; never blocks — when empty a new connection is opened."""

    def __init__(self, url: str, size: int, connect_timeout: int) -> None:
        self.url, self.connect_timeout = url, connect_timeout
        self.idle: "queue.LifoQueue[Any]" = queue.LifoQueue(maxsize=size)

    def _open(self):
        import psycopg
        from psycopg.rows import dict_row

        conn = psycopg.connect(self.url, row_factory=dict_row, connect_timeout=self.connect_timeout)
        # Prisma stores DateTime as UTC in `timestamp without time zone` columns;
        # pin the session to UTC so now()/comparisons agree with it.
        conn.execute("SET TIME ZONE 'UTC'")
        conn.commit()
        return conn

    def get(self):
        while True:
            try:
                conn = self.idle.get_nowait()
            except queue.Empty:
                return self._open()
            if not conn.closed and not conn.broken:
                return conn

    def put(self, conn) -> None:
        if conn.closed or conn.broken:
            return
        try:
            self.idle.put_nowait(conn)
        except queue.Full:
            conn.close()

    def close_all(self) -> None:
        while True:
            try:
                self.idle.get_nowait().close()
            except queue.Empty:
                return


class PostgresConnector(DBConnector):
    def __init__(self, database_url: Optional[str] = None) -> None:
        raw = database_url or os.environ.get("DATABASE_URL", "")
        if not raw:
            raise RuntimeError(
                "DATABASE_URL is not set. Add it to the repo-root .env "
                "(same value as frontend/.env)."
            )
        self._url = normalize_database_url(raw)
        with _pools_lock:
            pool = _pools.get(self._url)
            if pool is None:
                pool = _pools[self._url] = _Pool(self._url, int(os.environ.get("AQP_DB_POOL_SIZE", "8")),
                                                 int(os.environ.get("AQP_DB_CONNECT_TIMEOUT_S", "10")))
        self._pool = pool

    @contextmanager
    def connection(self) -> Iterator[Any]:
        """Yield a pooled psycopg connection: one transaction, committed on success, rolled back on error."""
        conn = self._pool.get()
        try:
            yield conn
            conn.commit()
        except BaseException:
            try:
                conn.rollback()
            except Exception:
                conn.close()
            raise
        finally:
            self._pool.put(conn)

    def query(self, sql: str, params: List[Any] = None) -> List[Dict]:
        with self.connection() as conn:
            return list(conn.execute(sql, params or []).fetchall())

    def execute(self, sql: str, params: List[Any] = None) -> None:
        with self.connection() as conn:
            conn.execute(sql, params or [])

    def ping(self) -> bool:
        self.query("SELECT 1 AS ok")
        return True

    def close(self) -> None:
        self._pool.close_all()
