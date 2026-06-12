"""Command-line interface.

Usage:
  secure-pg-query --init                 Scaffold the config file
  secure-pg-query --list                 List connections (no credentials)
  secure-pg-query <connection> "<SQL>"   Run a read-only query
  secure-pg-query <connection> "<SQL>" --json   Output rows as JSON
"""

import argparse
import json
import sys

from . import __version__
from .config import (
    get_connection,
    init_config,
    list_connections,
    resolve_config_path,
)
from .db import DEFAULT_MAX_ROWS, DEFAULT_TIMEOUT_MS, run_query
from .validate import is_safe_query


def _err(msg: str) -> int:
    print(f"[ERROR] {msg}", file=sys.stderr)
    return 1


def _print_table(columns: list[str], rows: list) -> None:
    if not rows:
        print("(0 rows)")
        return
    widths = [len(c) for c in columns]
    str_rows = [["" if v is None else str(v) for v in row] for row in rows]
    for row in str_rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(cell))
    sep = " | "
    print(sep.join(c.ljust(widths[i]) for i, c in enumerate(columns)))
    print("-+-".join("-" * w for w in widths))
    for row in str_rows:
        print(sep.join(cell.ljust(widths[i]) for i, cell in enumerate(row)))
    print(f"({len(rows)} row{'s' if len(rows) != 1 else ''})")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="secure-pg-query",
        description="Run safe, read-only PostgreSQL queries.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("--init", action="store_true", help="Scaffold the config file and exit.")
    parser.add_argument("--list", action="store_true", help="List available connections and exit.")
    parser.add_argument("--json", action="store_true", help="Output rows as JSON.")
    parser.add_argument(
        "--max-rows", type=int, default=DEFAULT_MAX_ROWS,
        help=f"Maximum rows to return (default: {DEFAULT_MAX_ROWS}).",
    )
    parser.add_argument(
        "--timeout-ms", type=int, default=DEFAULT_TIMEOUT_MS,
        help=f"Statement timeout in ms (default: {DEFAULT_TIMEOUT_MS}).",
    )
    parser.add_argument("connection", nargs="?", help="Connection name from the config.")
    parser.add_argument("query", nargs="?", help="The SELECT query to run.")
    args = parser.parse_args(argv)

    if args.init:
        try:
            path = init_config()
        except FileExistsError as e:
            return _err(str(e))
        except OSError as e:
            return _err(f"Could not create config: {e}")
        print(f"Created {path}\nEdit it with your real connections, then run --list.")
        return 0

    if args.list:
        try:
            conns = list_connections()
        except (FileNotFoundError, PermissionError, RuntimeError) as e:
            return _err(str(e))
        if not conns:
            print("No connections configured. Run: secure-pg-query --init")
            return 0
        for c in conns:
            print(f"{c['name']:<16} | {c['engine']:<10} | {c['database']:<16} | {c['env']}")
        return 0

    if not args.connection or args.query is None:
        parser.print_help(sys.stderr)
        print(f"\nConfig file: {resolve_config_path()}", file=sys.stderr)
        return 1

    ok, reason = is_safe_query(args.query)
    if not ok:
        return _err(f"Rejected query: {reason}")

    try:
        engine, db_config = get_connection(args.connection)
    except (FileNotFoundError, PermissionError, KeyError, ValueError, RuntimeError) as e:
        return _err(str(e))

    try:
        result = run_query(
            db_config,
            args.query,
            engine=engine,
            statement_timeout_ms=args.timeout_ms,
            max_rows=args.max_rows,
        )
    except Exception as e:  # noqa: BLE001 — surface a clean message, not a traceback
        return _err(str(e).strip())

    if args.json:
        payload = {
            "columns": result["columns"],
            "rows": [list(r) for r in result["rows"]],
            "truncated": result["truncated"],
        }
        print(json.dumps(payload, default=str, ensure_ascii=False, indent=2))
    else:
        _print_table(result["columns"], result["rows"])
        if result["truncated"]:
            print(f"\n[NOTE] Output truncated to {args.max_rows} rows. Use --max-rows to raise the cap.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
