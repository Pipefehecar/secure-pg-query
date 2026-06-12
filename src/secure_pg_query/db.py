"""Database execution — the authoritative read-only guarantee.

Every query runs inside a READ ONLY session with a statement timeout. Even if
a write statement bypassed the string validator, PostgreSQL rejects it with
``cannot execute INSERT in a read-only transaction``. Results are capped to
avoid pulling unbounded rows into memory.
"""

import psycopg2

DEFAULT_TIMEOUT_MS = 10_000
DEFAULT_MAX_ROWS = 1_000


def run_query(
    db_config: dict,
    query: str,
    *,
    statement_timeout_ms: int = DEFAULT_TIMEOUT_MS,
    max_rows: int = DEFAULT_MAX_ROWS,
) -> dict:
    """Execute a read-only query and return columns + rows.

    Returns a dict: ``{"columns": [...], "rows": [...], "truncated": bool}``.
    Raises on connection or query errors (caller formats the message).
    """
    conn = None
    try:
        conn = psycopg2.connect(
            **db_config,
            options=f"-c statement_timeout={int(statement_timeout_ms)}",
            connect_timeout=10,
        )
        # Authoritative guard: writes are impossible regardless of the SQL string.
        conn.set_session(readonly=True, autocommit=False)

        with conn.cursor() as cur:
            cur.execute(query)
            if cur.description is None:
                return {"columns": [], "rows": [], "truncated": False}
            columns = [d.name for d in cur.description]
            rows = cur.fetchmany(max_rows + 1)
            truncated = len(rows) > max_rows
            if truncated:
                rows = rows[:max_rows]
            return {"columns": columns, "rows": rows, "truncated": truncated}
    finally:
        if conn is not None:
            conn.rollback()  # no writes, but be explicit
            conn.close()
