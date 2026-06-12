"""Database execution — the authoritative read-only guarantee.

Every query runs inside a READ ONLY session/transaction with a statement
timeout. Even if a write statement bypassed the string validator, the database
itself rejects it:

  - PostgreSQL: ``cannot execute INSERT in a read-only transaction``
  - MySQL/MariaDB: ``Cannot execute statement in a READ ONLY transaction`` (1792)

Results are capped to avoid pulling unbounded rows into memory. Drivers are
imported lazily so a missing optional driver only matters for the engine that
needs it.
"""

DEFAULT_TIMEOUT_MS = 10_000
DEFAULT_MAX_ROWS = 1_000


def run_query(
    db_config: dict,
    query: str,
    *,
    engine: str = "postgres",
    statement_timeout_ms: int = DEFAULT_TIMEOUT_MS,
    max_rows: int = DEFAULT_MAX_ROWS,
) -> dict:
    """Execute a read-only query and return ``{columns, rows, truncated}``.

    Raises on connection or query errors (the caller formats the message).
    """
    if engine == "postgres":
        return _run_postgres(db_config, query, statement_timeout_ms, max_rows)
    if engine == "mysql":
        return _run_mysql(db_config, query, statement_timeout_ms, max_rows)
    raise ValueError(f"Unsupported engine: {engine}")


def _fetch(cur, max_rows: int) -> dict:
    """Shared result shaping for any DB-API cursor."""
    if cur.description is None:
        return {"columns": [], "rows": [], "truncated": False}
    columns = [d[0] for d in cur.description]  # name is index 0 in both drivers
    rows = cur.fetchmany(max_rows + 1)
    truncated = len(rows) > max_rows
    if truncated:
        rows = rows[:max_rows]
    return {"columns": columns, "rows": [tuple(r) for r in rows], "truncated": truncated}


def _run_postgres(db_config, query, timeout_ms, max_rows) -> dict:
    try:
        import psycopg2
    except ImportError as e:
        raise RuntimeError(
            "psycopg2 is required for PostgreSQL. Install with: pip install psycopg2-binary"
        ) from e

    conn = None
    try:
        conn = psycopg2.connect(
            **db_config,
            options=f"-c statement_timeout={int(timeout_ms)}",
            connect_timeout=10,
        )
        # Authoritative guard: writes are impossible regardless of the SQL string.
        conn.set_session(readonly=True, autocommit=False)
        with conn.cursor() as cur:
            cur.execute(query)
            return _fetch(cur, max_rows)
    finally:
        if conn is not None:
            conn.rollback()
            conn.close()


def _run_mysql(db_config, query, timeout_ms, max_rows) -> dict:
    try:
        import pymysql
    except ImportError as e:
        raise RuntimeError(
            "PyMySQL is required for MySQL. Install with: pip install PyMySQL"
        ) from e

    conn = None
    try:
        conn = pymysql.connect(
            host=db_config["host"],
            port=int(db_config["port"]),
            user=db_config["user"],
            password=db_config["password"],
            database=db_config["database"],
            connect_timeout=10,
            read_timeout=max(1, int(timeout_ms / 1000) + 5),
            autocommit=False,
        )
        with conn.cursor() as cur:
            # Cap server-side execution time (ms, applies to SELECT). MySQL 5.7.8+.
            try:
                cur.execute("SET SESSION max_execution_time=%s", (int(timeout_ms),))
            except Exception:
                pass  # MariaDB / older MySQL: read_timeout still bounds it
            # Authoritative guard: any write inside this tx errors with 1792.
            cur.execute("START TRANSACTION READ ONLY")
            cur.execute(query)
            return _fetch(cur, max_rows)
    finally:
        if conn is not None:
            try:
                conn.rollback()
            except Exception:
                pass
            conn.close()
