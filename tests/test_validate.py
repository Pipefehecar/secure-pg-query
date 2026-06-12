"""Tests for the query validator. Run with: python -m pytest"""

from secure_pg_query.validate import is_safe_query


def ok(q):
    allowed, _ = is_safe_query(q)
    return allowed


def test_allows_basic_select():
    assert ok("SELECT * FROM users LIMIT 10")


def test_allows_created_at_identifier():
    # Regression: substring blocklists wrongly blocked "created" (contains "create").
    assert ok("SELECT id, created_at FROM users ORDER BY created_at DESC LIMIT 5")


def test_allows_deleted_at_identifier():
    assert ok("SELECT id FROM users WHERE deleted_at IS NULL")


def test_allows_cte():
    assert ok("WITH recent AS (SELECT id FROM orders LIMIT 5) SELECT * FROM recent")


def test_allows_count():
    assert ok("SELECT COUNT(*) FROM sites")


def test_allows_explain():
    assert ok("EXPLAIN SELECT * FROM users")


def test_allows_trailing_semicolon():
    assert ok("SELECT 1;")


def test_blocks_insert():
    assert not ok("INSERT INTO users (name) VALUES ('x')")


def test_blocks_update():
    assert not ok("UPDATE users SET name = 'x' WHERE id = 1")


def test_blocks_delete():
    assert not ok("DELETE FROM users WHERE id = 1")


def test_blocks_drop():
    assert not ok("DROP TABLE users")


def test_blocks_stacked_statements():
    assert not ok("SELECT 1; DROP TABLE users")


def test_blocks_cte_with_delete():
    assert not ok("WITH t AS (DELETE FROM users RETURNING *) SELECT * FROM t")


def test_blocks_comment_evasion():
    assert not ok("SELECT 1 /* */ ; DROP TABLE users")


def test_blocks_dangerous_function():
    assert not ok("SELECT pg_read_file('/etc/passwd')")


def test_blocks_pg_sleep():
    assert not ok("SELECT pg_sleep(100)")


def test_blocks_dblink():
    assert not ok("SELECT * FROM dblink('host=evil', 'SELECT 1') AS t(x int)")


def test_semicolon_inside_string_is_fine():
    assert ok("SELECT * FROM logs WHERE msg = 'a;b'")


def test_keyword_inside_string_is_fine():
    assert ok("SELECT * FROM logs WHERE action = 'delete'")


def test_blocks_empty():
    assert not ok("")
