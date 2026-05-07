"""
Persistent audit trail (OWASP A09 — Security Logging and Monitoring).

Stores security-relevant events in SQLite so administrators can review who did what,
from which IP, and when. Complements file-based system.log with structured queries.
"""
from __future__ import annotations

import sqlite3
from typing import Any

from backend.models.user_model import get_db
from backend.utils.timezone import now_cat_str


def init_db() -> None:
    db = get_db()
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            username TEXT,
            action TEXT NOT NULL,
            details TEXT,
            ip_address TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_audit_created ON audit_logs(created_at);
        CREATE INDEX IF NOT EXISTS idx_audit_action ON audit_logs(action);
        CREATE INDEX IF NOT EXISTS idx_audit_user ON audit_logs(user_id);
        """
    )
    db.commit()


def insert_entry(
    *,
    action: str,
    user_id: int | None = None,
    username: str | None = None,
    details: str | None = None,
    ip_address: str | None = None,
) -> int:
    db = get_db()
    cur = db.execute(
        """
        INSERT INTO audit_logs (user_id, username, action, details, ip_address, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (user_id, username, action, details, ip_address, now_cat_str()),
    )
    db.commit()
    return int(cur.lastrowid)


def list_recent(*, limit: int = 100) -> list[sqlite3.Row]:
    db = get_db()
    cur = db.execute(
        """
        SELECT * FROM audit_logs
        ORDER BY id DESC
        LIMIT ?
        """,
        (limit,),
    )
    return cur.fetchall()
