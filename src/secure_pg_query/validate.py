"""Query validation — first layer of defense.

This is a string-level allowlist filter. It is INTENTIONALLY paired with a
read-only database session (see ``db.py``), which is the authoritative
guarantee: even if a write slipped past this filter, PostgreSQL rejects it
inside a read-only transaction. Defense in depth — never rely on string
parsing alone.
"""

import re

# Statements that read data and are safe to run inside a read-only session.
# Covers both PostgreSQL and MySQL/MariaDB read commands.
_ALLOWED_STARTS = (
    "select", "with", "show", "explain", "table", "values", "describe", "desc",
)

# Keyword blocklist as a secondary check. Matched on word boundaries so
# legitimate identifiers like ``created_at`` or ``deleted_at`` are NOT blocked.
_FORBIDDEN = (
    "insert", "update", "delete", "drop", "alter", "truncate",
    "create", "grant", "revoke", "merge", "call", "do", "copy",
    "vacuum", "reindex", "cluster", "comment", "lock", "listen",
    "notify", "set", "reset", "begin", "commit", "rollback", "savepoint",
)
_FORBIDDEN_RE = re.compile(r"\b(" + "|".join(_FORBIDDEN) + r")\b", re.IGNORECASE)

# Functions that read the filesystem / open external connections / waste
# resources — dangerous even inside a SELECT. Covers PostgreSQL and MySQL.
_DANGEROUS_FN = (
    # PostgreSQL
    "pg_read_file", "pg_read_binary_file", "pg_ls_dir", "pg_stat_file",
    "lo_import", "lo_export", "dblink", "pg_sleep", "copy_from", "pg_terminate_backend",
    # MySQL / MariaDB
    "load_file", "benchmark", "sleep", "get_lock", "release_lock",
    "sys_exec", "sys_eval", "master_pos_wait",
)
_DANGEROUS_FN_RE = re.compile(r"\b(" + "|".join(_DANGEROUS_FN) + r")\b", re.IGNORECASE)

# MySQL file-write clauses inside a SELECT (e.g. SELECT ... INTO OUTFILE '/x').
_INTO_FILE_RE = re.compile(r"\binto\s+(outfile|dumpfile)\b", re.IGNORECASE)


def _strip_comments(query: str) -> str:
    """Remove -- line comments and /* */ block comments to stop evasion."""
    query = re.sub(r"/\*.*?\*/", " ", query, flags=re.DOTALL)
    query = re.sub(r"--[^\n]*", " ", query)
    return query


def _strip_string_literals(query: str) -> str:
    """Blank out single-quoted literals so their contents don't trip checks
    (e.g. a ``;`` or the word ``delete`` inside a WHERE value)."""
    return re.sub(r"'(?:''|[^'])*'", "''", query)


def is_safe_query(query: str) -> tuple[bool, str]:
    """Return ``(ok, reason)``. ``reason`` is empty when the query is allowed."""
    if not query or not query.strip():
        return False, "Empty query."

    cleaned = _strip_string_literals(_strip_comments(query)).strip()
    lowered = cleaned.lower()

    if not lowered.startswith(_ALLOWED_STARTS):
        return False, "Only read queries are allowed (SELECT/WITH/SHOW/EXPLAIN)."

    # Block stacked statements: any ; that is not the trailing one.
    trimmed = cleaned.rstrip().rstrip(";")
    if ";" in trimmed:
        return False, "Multiple statements are not allowed."

    m = _FORBIDDEN_RE.search(cleaned)
    if m:
        return False, f"Forbidden keyword: {m.group(1).upper()}."

    m = _DANGEROUS_FN_RE.search(cleaned)
    if m:
        return False, f"Forbidden function: {m.group(1)}."

    if _INTO_FILE_RE.search(cleaned):
        return False, "INTO OUTFILE/DUMPFILE is not allowed."

    return True, ""
