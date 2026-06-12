# secure-pg-query

Safe, **read-only** PostgreSQL queries for AI agents and humans.

Point an AI assistant (or yourself) at a PostgreSQL database and let it run
queries — **without** risking a write, even when the database user has full
edit permissions. Two layers of defense:

1. **Read-only session (authoritative).** Every query runs inside a
   `READ ONLY` transaction. PostgreSQL itself rejects any `INSERT` / `UPDATE` /
   `DELETE` / DDL with `cannot execute ... in a read-only transaction` — no
   string parsing can be tricked into allowing a write.
2. **Query validator (defense in depth).** A string filter rejects anything
   that is not a read query, blocks stacked statements, comment-evasion, and
   dangerous functions (`pg_read_file`, `dblink`, `pg_sleep`, …) before it ever
   reaches the database.

Plus: a **statement timeout** (no `pg_sleep`/cartesian DoS), a **row cap** (no
unbounded memory), and **strict config permissions** (refuses to run on a
world-readable credentials file).

> Belt and suspenders: even so, point this at a database role that only has
> `GRANT SELECT`. The tool protects against accidents; least privilege protects
> against everything else.

## Install

```bash
pipx install git+https://github.com/Pipefehecar/secure-pg-query
# or
pip install git+https://github.com/Pipefehecar/secure-pg-query
```

Requires Python 3.10+ and `psycopg2-binary` (installed automatically).

## Configure

```bash
secure-pg-query --init
```

This creates `~/.config/secure-pg-query/connections.json` with `chmod 600` and
example connections. Edit it with your real databases:

```json
{
  "mydb": {
    "host": "localhost",
    "port": 5432,
    "database": "my_database",
    "user": "readonly_user",
    "password": "secret",
    "env": "localhost (local)"
  }
}
```

Credentials live in your user config directory — **never** in the repo. Override
the location with `SECURE_PG_CONFIG=/path/to/connections.json` if you prefer.

## Use

```bash
# List configured connections (never prints credentials)
secure-pg-query --list

# Run a query
secure-pg-query mydb "SELECT id, email, created_at FROM users ORDER BY created_at DESC LIMIT 5"

# JSON output (handy for scripts / agents)
secure-pg-query mydb "SELECT COUNT(*) FROM users" --json
```

Anything that is not a read query is rejected before it runs:

```bash
$ secure-pg-query mydb "DELETE FROM users"
[ERROR] Rejected query: Forbidden keyword: DELETE.
```

### Options

| Flag | Default | Meaning |
|------|---------|---------|
| `--list` | — | List connections and exit |
| `--init` | — | Scaffold the config file and exit |
| `--json` | off | Output rows as JSON |
| `--max-rows N` | 1000 | Cap returned rows |
| `--timeout-ms N` | 10000 | Statement timeout |

## Use it as a Claude Code skill

A ready-made skill lives in [`skill/SKILL.md`](skill/SKILL.md). Copy it so Claude
Code can translate natural-language questions into safe queries:

```bash
mkdir -p ~/.claude/skills/consulta-db
cp skill/SKILL.md ~/.claude/skills/consulta-db/SKILL.md
```

Then ask things like *"show me the last 5 users in mydb"* and the skill will run
`secure-pg-query` for you. It discovers connections dynamically via
`secure-pg-query --list`, so there is nothing machine-specific to edit.

## Develop

```bash
pip install -e ".[dev]" pytest
python -m pytest
```

## Security model & limitations

- The read-only session is the real guarantee; the validator is a fast,
  user-friendly first filter. Do not rely on the validator alone.
- `EXPLAIN ANALYZE` of a writing statement is blocked by the keyword filter and
  by the read-only session.
- This tool does not sandbox the network — a `readonly_user` role with no
  superuser and no `SELECT` on sensitive tables is still your responsibility.
- Found a hole? Open an issue. Validator gaps are bugs.

## License

MIT — see [LICENSE](LICENSE).
