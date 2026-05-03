"""Fuel record persistence and reporting queries."""
from __future__ import annotations

import sqlite3
from typing import Any

from backend.models.user_model import get_db

ALLOWED_FUEL_STATUS = frozenset({"pending", "approved", "rejected"})


def init_db() -> None:
    db = get_db()
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS fuel_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            vehicle_id TEXT NOT NULL,
            driver_name TEXT NOT NULL,
            fuel_amount REAL NOT NULL,
            fuel_type TEXT NOT NULL,
            record_date TEXT NOT NULL,
            location TEXT NOT NULL,
            odometer_reading REAL NOT NULL,
            cost REAL NOT NULL,
            station_name TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            submitted_by INTEGER NOT NULL,
            reviewed_by INTEGER,
            review_note TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            CHECK (fuel_amount >= 0),
            CHECK (odometer_reading >= 0),
            CHECK (cost >= 0),
            CHECK (status IN ('pending', 'approved', 'rejected')),
            FOREIGN KEY(submitted_by) REFERENCES users(id) ON DELETE RESTRICT,
            FOREIGN KEY(reviewed_by) REFERENCES users(id) ON DELETE SET NULL
        );

        CREATE INDEX IF NOT EXISTS idx_fuel_status ON fuel_records(status);
        CREATE INDEX IF NOT EXISTS idx_fuel_date ON fuel_records(record_date);
        CREATE INDEX IF NOT EXISTS idx_fuel_submitted_by ON fuel_records(submitted_by);
        CREATE INDEX IF NOT EXISTS idx_fuel_vehicle_id ON fuel_records(vehicle_id);
        """
    )
    db.commit()


def create_fuel_record(payload: dict[str, Any], submitted_by: int) -> int:
    db = get_db()
    cur = db.execute(
        """
        INSERT INTO fuel_records (
            vehicle_id, driver_name, fuel_amount, fuel_type, record_date,
            location, odometer_reading, cost, station_name, status, submitted_by
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?)
        """,
        (
            payload["vehicle_id"],
            payload["driver_name"],
            float(payload["fuel_amount"]),
            payload["fuel_type"],
            payload["record_date"],
            payload["location"],
            float(payload["odometer_reading"]),
            float(payload["cost"]),
            payload["station_name"],
            submitted_by,
        ),
    )
    record_id = int(cur.lastrowid)
    db.commit()
    return record_id


def list_fuel_records(*, status: str | None = None, submitted_by: int | None = None) -> list[sqlite3.Row]:
    db = get_db()
    clauses: list[str] = []
    values: list[Any] = []
    if status:
        clauses.append("fr.status = ?")
        values.append(status)
    if submitted_by is not None:
        clauses.append("fr.submitted_by = ?")
        values.append(submitted_by)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    cur = db.execute(
        f"""
        SELECT fr.*, submitter.username AS submitted_by_username, reviewer.username AS reviewed_by_username
        FROM fuel_records fr
        JOIN users submitter ON submitter.id = fr.submitted_by
        LEFT JOIN users reviewer ON reviewer.id = fr.reviewed_by
        {where}
        ORDER BY fr.record_date DESC, fr.id DESC
        """,
        values,
    )
    return cur.fetchall()


def get_fuel_record(record_id: int) -> sqlite3.Row | None:
    db = get_db()
    cur = db.execute("SELECT * FROM fuel_records WHERE id = ?", (record_id,))
    return cur.fetchone()


def update_fuel_status(record_id: int, *, status: str, reviewed_by: int, review_note: str | None) -> None:
    db = get_db()
    db.execute(
        """
        UPDATE fuel_records
        SET status = ?, reviewed_by = ?, review_note = ?, updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (status, reviewed_by, review_note, record_id),
    )
    db.commit()


def dashboard_metrics() -> dict[str, Any]:
    db = get_db()
    totals = db.execute(
        """
        SELECT
            COUNT(*) AS total_records,
            COALESCE(SUM(cost), 0) AS total_cost,
            SUM(CASE WHEN status = 'approved' THEN 1 ELSE 0 END) AS approved_requests,
            SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) AS pending_requests
        FROM fuel_records
        """
    ).fetchone()
    monthly = db.execute(
        """
        SELECT substr(record_date, 1, 7) AS month, ROUND(COALESCE(SUM(fuel_amount), 0), 2) AS total_fuel
        FROM fuel_records
        GROUP BY substr(record_date, 1, 7)
        ORDER BY month DESC
        LIMIT 6
        """
    ).fetchall()
    return {
        "total_records": int(totals["total_records"]) if totals else 0,
        "total_cost": float(totals["total_cost"]) if totals else 0.0,
        "approved_requests": int(totals["approved_requests"] or 0) if totals else 0,
        "pending_requests": int(totals["pending_requests"] or 0) if totals else 0,
        "monthly_usage": [dict(row) for row in monthly],
    }
