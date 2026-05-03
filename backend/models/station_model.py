"""Station operations: shifts, in-app alerts, and system settings (SQLite)."""
from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from typing import Any

from backend.models.user_model import get_db

DEFAULT_STATION_NAME = "FuelGuard Station"
LARGE_SALE_THRESHOLD = 10_000.0


def init_db() -> None:
    db = get_db()
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS system_settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS shifts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'open',
            started_at TIMESTAMP NOT NULL,
            ended_at TIMESTAMP,
            opening_meter REAL NOT NULL,
            closing_meter REAL,
            opening_cash REAL NOT NULL DEFAULT 0,
            cash_collected REAL,
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            CHECK (status IN ('open', 'closed')),
            CHECK (opening_meter >= 0),
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE RESTRICT
        );

        CREATE INDEX IF NOT EXISTS idx_shifts_user ON shifts(user_id);
        CREATE INDEX IF NOT EXISTS idx_shifts_started ON shifts(started_at);
        CREATE INDEX IF NOT EXISTS idx_shifts_status ON shifts(status);

        CREATE TABLE IF NOT EXISTS alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            alert_type TEXT NOT NULL,
            message TEXT NOT NULL,
            severity TEXT NOT NULL DEFAULT 'info',
            user_id INTEGER,
            meta_json TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            acknowledged_at TIMESTAMP,
            CHECK (severity IN ('info', 'warning', 'error', 'critical'))
        );

        CREATE INDEX IF NOT EXISTS idx_alerts_created ON alerts(created_at);
        CREATE INDEX IF NOT EXISTS idx_alerts_ack ON alerts(acknowledged_at);
        """
    )
    row = db.execute(
        "SELECT 1 FROM system_settings WHERE key = ?", ("station_name",)
    ).fetchone()
    if not row:
        db.execute(
            "INSERT INTO system_settings (key, value) VALUES ('station_name', ?)",
            (DEFAULT_STATION_NAME,),
        )
    db.commit()


def get_setting(key: str, default: str = "") -> str:
    db = get_db()
    r = db.execute(
        "SELECT value FROM system_settings WHERE key = ?", (key,)
    ).fetchone()
    return str(r["value"]) if r else default


def set_setting(key: str, value: str) -> None:
    db = get_db()
    db.execute(
        """
        INSERT INTO system_settings (key, value, updated_at)
        VALUES (?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = CURRENT_TIMESTAMP
        """,
        (key, value),
    )
    db.commit()


def station_name() -> str:
    return get_setting("station_name", DEFAULT_STATION_NAME)


def get_open_shift(user_id: int) -> sqlite3.Row | None:
    db = get_db()
    return db.execute(
        """
        SELECT * FROM shifts
        WHERE user_id = ? AND status = 'open'
        ORDER BY id DESC LIMIT 1
        """,
        (user_id,),
    ).fetchone()


def start_shift(
    *,
    user_id: int,
    opening_meter: float,
    opening_cash: float = 0.0,
    notes: str | None = None,
) -> tuple[int | None, str | None]:
    if opening_meter < 0:
        return None, "Opening meter cannot be negative."
    if get_open_shift(user_id):
        return None, "You already have an open shift. End it before starting a new one."
    db = get_db()
    when = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
    cur = db.execute(
        """
        INSERT INTO shifts (user_id, status, started_at, opening_meter, opening_cash, notes)
        VALUES (?, 'open', ?, ?, ?, ?)
        """,
        (user_id, when, opening_meter, opening_cash, notes),
    )
    db.commit()
    return int(cur.lastrowid), None


def end_shift(
    *,
    shift_id: int,
    user_id: int,
    closing_meter: float,
    cash_collected: float,
    notes: str | None = None,
) -> tuple[bool, str | None]:
    if closing_meter < 0 or cash_collected < 0:
        return False, "Meter and cash values must be non-negative."
    db = get_db()
    row = db.execute(
        "SELECT * FROM shifts WHERE id = ? AND user_id = ?", (shift_id, user_id)
    ).fetchone()
    if not row or (row["status"] or "").lower() != "open":
        return False, "Shift not found or already closed."
    if closing_meter < float(row["opening_meter"]):
        return False, "Closing meter must be greater than or equal to opening meter."
    when = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
    prior_notes = (row["notes"] or "").strip()
    close_note = (notes or "").strip()
    if close_note:
        merged_notes = f"{prior_notes}\n[Shift end {when}] {close_note}".strip() if prior_notes else close_note
    else:
        merged_notes = prior_notes or None
    db.execute(
        """
        UPDATE shifts
        SET status = 'closed', ended_at = ?, closing_meter = ?, cash_collected = ?,
            notes = ?
        WHERE id = ?
        """,
        (when, closing_meter, cash_collected, merged_notes, shift_id),
    )
    db.commit()
    return True, None


def shift_sales_summary(shift_id: int) -> dict[str, Any]:
    db = get_db()
    sh = db.execute("SELECT * FROM shifts WHERE id = ?", (shift_id,)).fetchone()
    if not sh:
        return {"litres": 0.0, "revenue": 0.0, "transactions": 0}
    uid = int(sh["user_id"])
    start = sh["started_at"]
    end = sh["ended_at"] or datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
    row = db.execute(
        """
        SELECT COALESCE(SUM(quantity), 0) AS litres,
               COALESCE(SUM(total_amount), 0) AS revenue,
               COUNT(*) AS cnt
        FROM fuel_sales
        WHERE salesperson_id = ?
        AND datetime(sale_date) >= datetime(?)
        AND datetime(sale_date) <= datetime(?)
        """,
        (uid, start, end),
    ).fetchone()
    return {
        "litres": float(row["litres"] or 0),
        "revenue": float(row["revenue"] or 0),
        "transactions": int(row["cnt"] or 0),
    }


def list_shifts_for_user(user_id: int, *, limit: int = 30) -> list[sqlite3.Row]:
    db = get_db()
    return db.execute(
        """
        SELECT * FROM shifts
        WHERE user_id = ?
        ORDER BY started_at DESC, id DESC
        LIMIT ?
        """,
        (user_id, limit),
    ).fetchall()


def list_recent_shifts_with_staff(*, limit: int = 120) -> list[sqlite3.Row]:
    """All shifts (any user), newest first; open shifts listed before closed."""
    db = get_db()
    return db.execute(
        """
        SELECT s.*, u.username, u.full_name, u.email, u.role AS user_role
        FROM shifts s
        JOIN users u ON u.id = s.user_id
        ORDER BY CASE WHEN s.status = 'open' THEN 0 ELSE 1 END,
                 s.started_at DESC, s.id DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()


def list_shifts_between(date_from: str, date_to: str) -> list[sqlite3.Row]:
    db = get_db()
    return db.execute(
        """
        SELECT s.*, u.username
        FROM shifts s
        JOIN users u ON u.id = s.user_id
        WHERE date(s.started_at) >= date(?) AND date(s.started_at) <= date(?)
        ORDER BY s.started_at DESC, s.id DESC
        """,
        (date_from, date_to),
    ).fetchall()


def create_alert(
    *,
    alert_type: str,
    message: str,
    severity: str = "warning",
    user_id: int | None = None,
    meta: dict[str, Any] | None = None,
) -> int:
    sev = severity if severity in {"info", "warning", "error", "critical"} else "warning"
    db = get_db()
    meta_json = json.dumps(meta) if meta else None
    cur = db.execute(
        """
        INSERT INTO alerts (alert_type, message, severity, user_id, meta_json)
        VALUES (?, ?, ?, ?, ?)
        """,
        (alert_type, message, sev, user_id, meta_json),
    )
    db.commit()
    return int(cur.lastrowid)


def list_recent_alerts(*, limit: int = 25, include_acknowledged: bool = False) -> list[sqlite3.Row]:
    db = get_db()
    if include_acknowledged:
        return db.execute(
            "SELECT * FROM alerts ORDER BY created_at DESC, id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return db.execute(
        """
        SELECT * FROM alerts
        WHERE acknowledged_at IS NULL
        ORDER BY created_at DESC, id DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()


def acknowledge_alert(alert_id: int) -> bool:
    db = get_db()
    when = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
    cur = db.execute(
        "UPDATE alerts SET acknowledged_at = ? WHERE id = ? AND acknowledged_at IS NULL",
        (when, alert_id),
    )
    db.commit()
    return cur.rowcount > 0


def maybe_alert_low_fuel(fuel_type: str, available: float, minimum: float) -> None:
    if available <= minimum:
        db = get_db()
        existing = db.execute(
            """
            SELECT id FROM alerts
            WHERE alert_type = 'low_fuel'
              AND acknowledged_at IS NULL
              AND (
                    message LIKE ?
                    OR COALESCE(meta_json, '') LIKE ?
                  )
            LIMIT 1
            """,
            (f"LOW FUEL WARNING: {fuel_type}%", f'%"{fuel_type}"%'),
        ).fetchone()
        if existing:
            return
        create_alert(
            alert_type="low_fuel",
            message=f"LOW FUEL WARNING: {fuel_type} is at {available:.0f} L (minimum {minimum:.0f} L).",
            severity="critical",
            meta={"fuel_type": fuel_type, "available": available, "minimum": minimum},
        )


def reconcile_low_fuel_alert(fuel_type: str, available: float, minimum: float) -> None:
    """Ensure low-fuel alerts reflect the latest measured stock level."""
    if available <= minimum:
        maybe_alert_low_fuel(fuel_type, available, minimum)
        return
    db = get_db()
    when = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
    db.execute(
        """
        UPDATE alerts
        SET acknowledged_at = ?
        WHERE alert_type = 'low_fuel'
          AND acknowledged_at IS NULL
          AND (
                message LIKE ?
                OR COALESCE(meta_json, '') LIKE ?
              )
        """,
        (when, f"LOW FUEL WARNING: {fuel_type}%", f'%"{fuel_type}"%'),
    )
    db.commit()


def maybe_alert_large_sale(sale_id: int, total_amount: float) -> None:
    if total_amount >= LARGE_SALE_THRESHOLD:
        create_alert(
            alert_type="large_sale",
            message=f"Large transaction recorded: sale #{sale_id} for K{total_amount:,.2f}.",
            severity="warning",
            meta={"sale_id": sale_id},
        )


def maybe_alert_high_expenses_daily(expenses_today: float, revenue_today: float) -> None:
    if revenue_today <= 0:
        return
    if expenses_today > revenue_today * 0.85 and expenses_today > 100:
        create_alert(
            alert_type="high_expenses",
            message=(
                f"High expenses today: K{expenses_today:,.2f} vs revenue K{revenue_today:,.2f}. "
                "Review spending."
            ),
            severity="warning",
        )
