"""Operational approval queue for managers."""
from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from typing import Any

from backend.models.user_model import get_db

STATUS_PENDING = "Pending"
STATUS_APPROVED = "Approved"
STATUS_REJECTED = "Rejected"


def init_db() -> None:
    db = get_db()
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS approval_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            request_type TEXT NOT NULL,
            description TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'Pending',
            requested_by INTEGER NOT NULL,
            approved_by INTEGER,
            request_date TIMESTAMP NOT NULL,
            decision_date TIMESTAMP,
            CHECK (status IN ('Pending', 'Approved', 'Rejected')),
            FOREIGN KEY(requested_by) REFERENCES users(id) ON DELETE RESTRICT,
            FOREIGN KEY(approved_by) REFERENCES users(id) ON DELETE SET NULL
        );
        CREATE INDEX IF NOT EXISTS idx_approval_status ON approval_requests(status);
        CREATE INDEX IF NOT EXISTS idx_approval_requested_by ON approval_requests(requested_by);
        """
    )
    _backfill_fuel_records(db)
    db.commit()


def _fuel_record_id_from_description(description: str) -> int | None:
    if not description:
        return None
    head = description.split("|", 1)[0].strip()
    if not head.startswith("fuel_record:"):
        return None
    try:
        return int(head.split(":", 1)[1].strip())
    except (ValueError, IndexError):
        return None


def create_for_fuel_record(
    *,
    record_id: int,
    submitted_by: int,
    vehicle_id: str,
    driver_name: str,
) -> int:
    db = get_db()
    desc = (
        f"fuel_record:{record_id}|Vehicle {vehicle_id.strip()} — "
        f"{driver_name.strip()} — pending operational review"
    )
    when = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
    cur = db.execute(
        """
        INSERT INTO approval_requests (
            request_type, description, status, requested_by, request_date
        ) VALUES (?, ?, ?, ?, ?)
        """,
        ("Fuel record", desc, STATUS_PENDING, submitted_by, when),
    )
    db.commit()
    return int(cur.lastrowid)


def _backfill_fuel_records(db: sqlite3.Connection) -> None:
    pending = db.execute(
        """
        SELECT id, submitted_by, vehicle_id, driver_name
        FROM fuel_records
        WHERE status = 'pending'
        """
    ).fetchall()
    when = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
    for r in pending:
        rid = int(r["id"])
        prefix = f"fuel_record:{rid}|"
        exists = db.execute(
            "SELECT 1 FROM approval_requests WHERE description LIKE ? LIMIT 1",
            (prefix + "%",),
        ).fetchone()
        if exists:
            continue
        desc = (
            f"fuel_record:{rid}|Vehicle {r['vehicle_id']} — "
            f"{r['driver_name']} — pending operational review"
        )
        db.execute(
            """
            INSERT INTO approval_requests (
                request_type, description, status, requested_by, request_date
            ) VALUES (?, ?, ?, ?, ?)
            """,
            ("Fuel record", desc, STATUS_PENDING, int(r["submitted_by"]), when),
        )


def sync_decision_for_fuel_record(
    record_id: int,
    *,
    manager_id: int,
    approved: bool,
) -> None:
    """Keep approval queue in sync when a fuel record is reviewed via API."""
    db = get_db()
    prefix = f"fuel_record:{record_id}|"
    row = db.execute(
        """
        SELECT id, status FROM approval_requests
        WHERE description LIKE ? AND status = ?
        LIMIT 1
        """,
        (prefix + "%", STATUS_PENDING),
    ).fetchone()
    if not row:
        return
    new_status = STATUS_APPROVED if approved else STATUS_REJECTED
    when = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
    db.execute(
        """
        UPDATE approval_requests
        SET status = ?, approved_by = ?, decision_date = ?
        WHERE id = ?
        """,
        (new_status, manager_id, when, int(row["id"])),
    )
    db.commit()


def list_requests(
    *,
    status: str | None = None,
    limit: int = 200,
) -> list[sqlite3.Row]:
    db = get_db()
    clauses: list[str] = []
    params: list[Any] = []
    if status:
        clauses.append("ar.status = ?")
        params.append(status)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    cur = db.execute(
        f"""
        SELECT ar.*, u.username AS requested_by_username
        FROM approval_requests ar
        JOIN users u ON u.id = ar.requested_by
        {where}
        ORDER BY ar.request_date DESC, ar.id DESC
        LIMIT ?
        """,
        (*params, limit),
    )
    return cur.fetchall()


def get_by_id(request_id: int) -> sqlite3.Row | None:
    db = get_db()
    cur = db.execute("SELECT * FROM approval_requests WHERE id = ?", (request_id,))
    return cur.fetchone()


def count_pending() -> int:
    db = get_db()
    row = db.execute(
        "SELECT COUNT(*) AS c FROM approval_requests WHERE status = ?",
        (STATUS_PENDING,),
    ).fetchone()
    return int(row["c"]) if row else 0


def set_decision(
    request_id: int,
    *,
    new_status: str,
    manager_id: int,
) -> tuple[bool, str | None]:
    if new_status not in {STATUS_APPROVED, STATUS_REJECTED}:
        return False, "Invalid status."
    row = get_by_id(request_id)
    if not row:
        return False, "Request not found."
    if (row["status"] or "") != STATUS_PENDING:
        return False, "Request is no longer pending."
    when = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
    db = get_db()
    db.execute(
        """
        UPDATE approval_requests
        SET status = ?, approved_by = ?, decision_date = ?
        WHERE id = ?
        """,
        (new_status, manager_id, when, request_id),
    )
    db.commit()
    return True, None


def linked_fuel_record_id(description: str) -> int | None:
    return _fuel_record_id_from_description(description)
