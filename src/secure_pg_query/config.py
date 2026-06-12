"""Configuration loading and connection resolution.

Credentials live OUTSIDE the repo, in the user config directory, with strict
permissions. The repo only ships ``connections.example.json``.

Resolution order for the config file:
  1. ``$SECURE_PG_CONFIG`` (explicit override)
  2. ``$XDG_CONFIG_HOME/secure-pg-query/connections.json``
     (defaults to ``~/.config/secure-pg-query/connections.json``)
"""

import json
import os
import stat
from pathlib import Path

REQUIRED_KEYS = ("host", "port", "database", "user", "password")

EXAMPLE_CONFIG = {
    "local": {
        "host": "localhost",
        "port": 5432,
        "database": "my_database",
        "user": "readonly_user",
        "password": "change_me",
        "env": "localhost (local)",
    },
    "prod_readonly": {
        "host": "my-db.example.com",
        "port": 5432,
        "database": "prod_db",
        "user": "readonly_user",
        "password": "change_me",
        "env": "AWS RDS (remote)",
    },
}


def resolve_config_path() -> Path:
    """Return the path to the connections config file (may not exist yet)."""
    override = os.environ.get("SECURE_PG_CONFIG")
    if override:
        return Path(override).expanduser()
    base = os.environ.get("XDG_CONFIG_HOME", "~/.config")
    return Path(base).expanduser() / "secure-pg-query" / "connections.json"


def _check_permissions(path: Path) -> None:
    """Refuse to run if the config is readable by group or others.

    Credentials in a world/group-readable file are a security hole, so we
    fail loudly instead of silently leaking them.
    """
    mode = path.stat().st_mode
    if mode & (stat.S_IRWXG | stat.S_IRWXO):
        raise PermissionError(
            f"{path} has insecure permissions (must be accessible only by you).\n"
            f"Fix it with:  chmod 600 {path}"
        )


def load_config(path: Path | None = None) -> dict:
    """Load and validate the full connections config."""
    path = path or resolve_config_path()
    if not path.exists():
        raise FileNotFoundError(
            f"No config found at {path}.\n"
            f"Create one with:  secure-pg-query --init"
        )
    _check_permissions(path)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Invalid JSON in {path}: {e}") from e
    if not isinstance(data, dict):
        raise RuntimeError(f"{path} must contain a JSON object of connections.")
    return data


def get_connection(connection_name: str, path: Path | None = None) -> dict:
    """Return the validated config for a single connection.

    Strips non-connection metadata (like ``env``) so the result can be passed
    straight to ``psycopg2.connect``.
    """
    data = load_config(path)
    if connection_name not in data:
        available = ", ".join(sorted(data.keys())) or "<none>"
        raise KeyError(
            f"Connection '{connection_name}' not found. Available: {available}"
        )
    cfg = dict(data[connection_name])
    missing = [k for k in REQUIRED_KEYS if k not in cfg]
    if missing:
        raise ValueError(
            f"Connection '{connection_name}' is missing keys: {', '.join(missing)}"
        )
    cfg.pop("env", None)  # metadata, not a psycopg2 param
    return cfg


def list_connections(path: Path | None = None) -> list[dict]:
    """Return connection summaries WITHOUT credentials, for display."""
    data = load_config(path)
    out = []
    for name, cfg in sorted(data.items()):
        out.append(
            {
                "name": name,
                "database": cfg.get("database", "?"),
                "env": cfg.get("env", ""),
            }
        )
    return out


def init_config(path: Path | None = None) -> Path:
    """Scaffold a config file with example connections and 0600 perms."""
    path = path or resolve_config_path()
    if path.exists():
        raise FileExistsError(f"Config already exists: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(EXAMPLE_CONFIG, indent=2) + "\n", encoding="utf-8")
    path.chmod(0o600)
    return path
