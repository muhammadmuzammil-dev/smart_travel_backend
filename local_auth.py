"""
Local SQLite-based auth fallback.
Used automatically when Supabase is unreachable.
Database stored at: backend/data/users.db
"""

import sqlite3
import os
from pathlib import Path
from typing import Optional, Dict

DB_PATH = Path(__file__).parent / "data" / "users.db"


def _get_conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Create users table if it doesn't exist."""
    with _get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id       INTEGER PRIMARY KEY AUTOINCREMENT,
                email    TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                full_name TEXT
            )
        """)
        conn.commit()


def user_exists(email: str) -> bool:
    with _get_conn() as conn:
        row = conn.execute(
            "SELECT 1 FROM users WHERE email = ?", (email,)
        ).fetchone()
    return row is not None


def create_user(email: str, password_hash: str, full_name: Optional[str] = None) -> Dict:
    with _get_conn() as conn:
        conn.execute(
            "INSERT INTO users (email, password_hash, full_name) VALUES (?, ?, ?)",
            (email, password_hash, full_name),
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM users WHERE email = ?", (email,)
        ).fetchone()
    return dict(row)


def get_user_by_email(email: str) -> Optional[Dict]:
    with _get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE email = ?", (email,)
        ).fetchone()
    return dict(row) if row else None


# Auto-initialise on import
init_db()
