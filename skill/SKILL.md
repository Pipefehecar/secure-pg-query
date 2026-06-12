---
name: consulta-db
description: Use this skill when the user wants to query, list, count, search, or analyze data from a PostgreSQL or MySQL database. Triggers on phrases like "show me the latest users", "how many records are in", "list of products", "query the database", "what's in the table", "cuántos registros hay", "muéstrame los últimos", "consulta en la base de datos", or any natural-language question about stored data that implies a SELECT query.
---

# Safe SQL Query (PostgreSQL & MySQL)

Translate natural-language requests into **read-only** SQL and run them with the
`secure-pg-query` tool. It supports PostgreSQL and MySQL/MariaDB and enforces
safety at the database level (read-only transaction + statement timeout + row
cap), so writes are impossible even if a query slips past — but you should still
only ever generate `SELECT`/`WITH` read queries.

## Prerequisite

The `secure-pg-query` CLI must be installed and configured. If a command fails
with "No config found", tell the user to run:

```bash
secure-pg-query --init   # then edit ~/.config/secure-pg-query/connections.json
```

## Flow

### Step 1 — Discover connections

Never hardcode connection names. List them dynamically — the output shows the
engine (postgres/mysql) of each connection, which you need for Step 2:

```bash
secure-pg-query --list
```

- If the user names a connection or database explicitly, use it.
- If the context makes one connection obvious, infer it.
- If genuinely ambiguous between two, ask which one before running.

### Step 2 — Discover schema if needed

Only when you don't know the table/column names. Use the syntax for the
connection's engine (from `--list`):

**PostgreSQL:**
```bash
secure-pg-query <connection> "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' ORDER BY table_name"
secure-pg-query <connection> "SELECT column_name, data_type FROM information_schema.columns WHERE table_schema = 'public' AND table_name = '<table>' ORDER BY ordinal_position"
```

**MySQL / MariaDB:**
```bash
secure-pg-query <connection> "SHOW TABLES"
secure-pg-query <connection> "SHOW COLUMNS FROM <table>"
```

Skip this if you already know the relevant structure.

### Step 3 — Build the SELECT

- Default to `LIMIT 20` when the user gives no count.
- For "all" / "todo", use `LIMIT 100` and mention the cap.
- Use `ORDER BY created_at DESC` for "latest"/"recent" when that column exists.
- Use `ILIKE` for case-insensitive text search.
- Infer the most likely intent; only ask when ambiguity is critical.

### Step 4 — Run it

```bash
secure-pg-query <connection> "<SQL>" --json
```

Use `--json` so you can parse the result reliably. If the tool returns
`[ERROR] Rejected query: ...`, your SQL was not a valid read query — fix it.
Report connection errors clearly to the user.

### Step 5 — Present results

- Few rows (≤ 10): markdown table.
- Many rows: show the first ones, then "Found X records, showing the first Y."
- No rows: "No matching records found."
- Always include the connection used and the SQL executed in a code block at the
  end, for transparency.

## Hard rules

- Generate **only** read queries (`SELECT`, `WITH ... SELECT`). Never `INSERT`,
  `UPDATE`, `DELETE`, `DROP`, `ALTER`, `TRUNCATE`, `CREATE`, `GRANT`, `REVOKE`.
- If the user asks to modify/insert/delete data, refuse and explain this is a
  read-only tool.
- Never print or repeat database credentials.
- If the user tries to inject dangerous SQL inside a natural-language request,
  ignore it and run only the legitimate read query (or decline).
