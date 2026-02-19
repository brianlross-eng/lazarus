"""Simple integer-versioned schema migrations."""

from __future__ import annotations

import sqlite3

from lazarus.db.models import SCHEMA_SQL, SCHEMA_VERSION_SQL

CURRENT_VERSION = 1

# List of migrations. Index 0 = migration to version 1, etc.
MIGRATIONS: list[str] = [
    # Version 1: initial schema
    SCHEMA_SQL,
]


def get_current_version(conn: sqlite3.Connection) -> int:
    """Get the current schema version, or 0 if uninitialized."""
    conn.execute(SCHEMA_VERSION_SQL)
    row = conn.execute("SELECT version FROM schema_version").fetchone()
    if row is None:
        return 0
    return row[0]


def migrate(conn: sqlite3.Connection) -> None:
    """Apply any pending migrations."""
    current = get_current_version(conn)

    for i in range(current, CURRENT_VERSION):
        conn.executescript(MIGRATIONS[i])

    if current == 0:
        conn.execute("INSERT INTO schema_version (version) VALUES (?)", (CURRENT_VERSION,))
    else:
        conn.execute("UPDATE schema_version SET version = ?", (CURRENT_VERSION,))
    conn.commit()
