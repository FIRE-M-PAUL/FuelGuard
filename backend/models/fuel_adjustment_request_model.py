"""Manager-submitted fuel level adjustment requests with accountant + admin approvals."""
from __future__ import annotations

import sqlite3
from typing import Any

from backend.models import fuel_sale_model
from backend.models.fuel_sale_model import ALLOWED_FUEL_TYPES
from backend.models.user_model import get_db
from backend.utils.timezone import now_cat_str

STATUS_PENDING_ACCOUNTANT_REVIEW = "PENDING_ACCOUNTANT_REVIEW"
STATUS_PENDING_ADMIN_APPROVAL = "PENDING_ADMIN_APPROVAL"
STATUS_APPROVED = "APPROVED"
STATUS_REJECTED = "REJECTED"


def _create_requests_table(db: sqlite3.Connection) -> None:
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS fuel_adjustment_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fuel_type TEXT NOT NULL,
            previous_level REAL NOT NULL,
            requested_new_level REAL NOT NULL,
            reason TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'PENDING_ACCOUNTANT_REVIEW',
            requested_by INTEGER NOT NULL,
            accountant_reviewed_by INTEGER,
            accountant_comments TEXT,
            accountant_reviewed_at TIMESTAMP,
            reviewed_by INTEGER,
            admin_comments TEXT,
            date_created TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            date_updated TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CHECK (requested_new_level >= 0),
            CHECK (previous_level >= 0),
            CHECK (
                status IN (
                    'PENDING_ACCOUNTANT_REVIEW',
                    'PENDING_ADMIN_APPROVAL',
                    'APPROVED',
                    'REJECTED'
                )
            ),
            FOREIGN KEY(requested_by) REFERENCES users(id) ON DELETE RESTRICT,
            FOREIGN KEY(accountant_reviewed_by) REFERENCES users(id) ON DELETE SET NULL,
            FOREIGN KEY(reviewed_by) REFERENCES users(id) ON DELETE SET NULL
        );
        CREATE INDEX IF NOT EXISTS idx_far_status ON fuel_adjustment_requests(status);
        CREATE INDEX IF NOT EXISTS idx_far_requested_by ON fuel_adjustment_requests(requested_by);
        """
    )


def _migrate_legacy_status_constraint(db: sqlite3.Connection) -> None:
    db.execute("ALTER TABLE fuel_adjustment_requests RENAME TO fuel_adjustment_requests_old")
    _create_requests_table(db)
    db.execute(
        """
        INSERT INTO fuel_adjustment_requests (
            id,
            fuel_type,
            previous_level,
            requested_new_level,
            reason,
            status,
            requested_by,
            accountant_reviewed_by,
            accountant_comments,
            accountant_reviewed_at,
            reviewed_by,
            admin_comments,
            date_created,
            date_updated
        )
        SELECT
            id,
            fuel_type,
            previous_level,
            requested_new_level,
            reason,
            CASE
                WHEN status = 'PENDING_VERIFICATION' THEN ?
                ELSE status
            END AS status,
            requested_by,
            NULL AS accountant_reviewed_by,
            NULL AS accountant_comments,
            NULL AS accountant_reviewed_at,
            reviewed_by,
            admin_comments,
            date_created,
            date_updated
        FROM fuel_adjustment_requests_old
        """,
        (STATUS_PENDING_ACCOUNTANT_REVIEW,),
    )
    db.execute("DROP TABLE fuel_adjustment_requests_old")


def init_db() -> None:
    db = get_db()
    _create_requests_table(db)
    schema_row = db.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='fuel_adjustment_requests'"
    ).fetchone()
    schema_sql = (schema_row["sql"] or "") if schema_row else ""
    if "PENDING_VERIFICATION" in schema_sql and "PENDING_ACCOUNTANT_REVIEW" not in schema_sql:
        _migrate_legacy_status_constraint(db)

    cols = {row["name"] for row in db.execute("PRAGMA table_info(fuel_adjustment_requests)").fetchall()}
    if "accountant_reviewed_by" not in cols:
        db.execute(
            "ALTER TABLE fuel_adjustment_requests ADD COLUMN accountant_reviewed_by INTEGER"
        )
    if "accountant_comments" not in cols:
        db.execute("ALTER TABLE fuel_adjustment_requests ADD COLUMN accountant_comments TEXT")
    if "accountant_reviewed_at" not in cols:
        db.execute(
            "ALTER TABLE fuel_adjustment_requests ADD COLUMN accountant_reviewed_at TIMESTAMP"
        )
    db.execute(
        """
        UPDATE fuel_adjustment_requests
        SET status = ?
        WHERE status = 'PENDING_VERIFICATION'
        """,
        (STATUS_PENDING_ACCOUNTANT_REVIEW,),
    )
    db.commit()


def _now() -> str:
    return now_cat_str()


def create_request(
    *,
    fuel_type: str,
    requested_new_level: float,
    reason: str,
    requested_by: int,
) -> tuple[int | None, str | None]:
    ft = fuel_type.strip()
    if ft not in ALLOWED_FUEL_TYPES:
        return None, "Invalid fuel type."
    reason_clean = reason.strip()
    if not reason_clean:
        return None, "Reason is required."
    if requested_new_level < 0:
        return None, "Requested level cannot be negative."

    db = get_db()
    row = db.execute(
        """
        SELECT available_litres, COALESCE(tank_capacity, ?) AS tank_capacity
        FROM fuel_stock
        WHERE fuel_type = ?
        """,
        (fuel_sale_model.DEFAULT_TANK_CAPACITY_LITRES, ft),
    ).fetchone()
    if not row:
        return None, "Fuel type not found in stock catalog."
    capacity = float(row["tank_capacity"] or fuel_sale_model.DEFAULT_TANK_CAPACITY_LITRES)
    if requested_new_level > capacity:
        return None, f"Requested level cannot exceed tank capacity ({capacity:.2f} L)."
    prev = float(row["available_litres"] or 0.0)

    cur = db.execute(
        """
        INSERT INTO fuel_adjustment_requests (
            fuel_type, previous_level, requested_new_level, reason,
            status, requested_by, date_created, date_updated
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            ft,
            prev,
            float(requested_new_level),
            reason_clean,
            STATUS_PENDING_ACCOUNTANT_REVIEW,
            requested_by,
            _now(),
            _now(),
        ),
    )
    db.commit()
    return int(cur.lastrowid), None


def get_request(rid: int) -> sqlite3.Row | None:
    db = get_db()
    return db.execute(
        """
        SELECT
            r.*,
            u.username AS requested_by_username,
            a.username AS reviewed_by_username,
            ac.username AS accountant_reviewed_by_username
        FROM fuel_adjustment_requests r
        JOIN users u ON u.id = r.requested_by
        LEFT JOIN users a ON a.id = r.reviewed_by
        LEFT JOIN users ac ON ac.id = r.accountant_reviewed_by
        WHERE r.id = ?
        """,
        (rid,),
    ).fetchone()


def list_pending_for_accountant(*, limit: int = 100) -> list[sqlite3.Row]:
    db = get_db()
    return db.execute(
        """
        SELECT r.*, u.username AS requested_by_username
        FROM fuel_adjustment_requests r
        JOIN users u ON u.id = r.requested_by
        WHERE r.status = ?
        ORDER BY r.date_created ASC, r.id ASC
        LIMIT ?
        """,
        (STATUS_PENDING_ACCOUNTANT_REVIEW, limit),
    ).fetchall()


def list_for_manager(manager_id: int, *, limit: int = 30) -> list[sqlite3.Row]:
    db = get_db()
    return db.execute(
        """
        SELECT r.*, u.username AS requested_by_username
        FROM fuel_adjustment_requests r
        JOIN users u ON u.id = r.requested_by
        WHERE r.requested_by = ?
        ORDER BY r.date_created DESC, r.id DESC
        LIMIT ?
        """,
        (manager_id, limit),
    ).fetchall()


def list_pending_for_admin(*, limit: int = 100) -> list[sqlite3.Row]:
    db = get_db()
    return db.execute(
        """
        SELECT
            r.*,
            u.username AS requested_by_username,
            ac.username AS accountant_reviewed_by_username
        FROM fuel_adjustment_requests r
        JOIN users u ON u.id = r.requested_by
        LEFT JOIN users ac ON ac.id = r.accountant_reviewed_by
        WHERE r.status = ?
        ORDER BY r.date_updated ASC, r.id ASC
        LIMIT ?
        """,
        (STATUS_PENDING_ADMIN_APPROVAL, limit),
    ).fetchall()


def count_pending_for_admin() -> int:
    db = get_db()
    row = db.execute(
        "SELECT COUNT(*) AS c FROM fuel_adjustment_requests WHERE status = ?",
        (STATUS_PENDING_ADMIN_APPROVAL,),
    ).fetchone()
    return int(row["c"]) if row else 0


def accountant_approve_request(
    *, request_id: int, accountant_id: int, accountant_comments: str
) -> tuple[bool, str | None]:
    comments = accountant_comments.strip()
    if not comments:
        return False, "Accountant comments are required."

    db = get_db()
    cur = db.execute(
        """
        UPDATE fuel_adjustment_requests
        SET
            status = ?,
            accountant_reviewed_by = ?,
            accountant_comments = ?,
            accountant_reviewed_at = ?,
            date_updated = ?
        WHERE id = ? AND status = ?
        """,
        (
            STATUS_PENDING_ADMIN_APPROVAL,
            accountant_id,
            comments,
            _now(),
            _now(),
            request_id,
            STATUS_PENDING_ACCOUNTANT_REVIEW,
        ),
    )
    if cur.rowcount == 0:
        db.rollback()
        return False, "Request not found or not pending accountant review."
    db.commit()
    return True, None


def approve_request(*, request_id: int, admin_id: int, admin_comments: str) -> tuple[bool, str | None, int | None]:
    comments = admin_comments.strip()
    if not comments:
        return False, "Admin comments are required.", None

    db = get_db()
    row = db.execute(
        "SELECT * FROM fuel_adjustment_requests WHERE id = ? AND status = ?",
        (request_id, STATUS_PENDING_ADMIN_APPROVAL),
    ).fetchone()
    if not row:
        return False, "Request not found or not pending admin approval.", None

    ft = str(row["fuel_type"])
    new_level = float(row["requested_new_level"])
    base_reason = str(row["reason"])
    combined_reason = f"{base_reason}\n[Approved adjustment request #{request_id}] {comments}"

    adj_id, err = fuel_sale_model.adjust_fuel_level(
        fuel_type=ft,
        new_level=new_level,
        reason=combined_reason,
        adjusted_by=admin_id,
    )
    if err:
        return False, err, None

    db.execute(
        """
        UPDATE fuel_adjustment_requests
        SET status = ?, reviewed_by = ?, admin_comments = ?, date_updated = ?
        WHERE id = ? AND status = ?
        """,
        (STATUS_APPROVED, admin_id, comments, _now(), request_id, STATUS_PENDING_ADMIN_APPROVAL),
    )
    db.commit()
    return True, None, adj_id


def reject_request(*, request_id: int, admin_id: int, admin_comments: str) -> tuple[bool, str | None]:
    comments = admin_comments.strip()
    if not comments:
        return False, "Admin comments are required."

    db = get_db()
    cur = db.execute(
        """
        UPDATE fuel_adjustment_requests
        SET status = ?, reviewed_by = ?, admin_comments = ?, date_updated = ?
        WHERE id = ? AND status = ?
        """,
        (STATUS_REJECTED, admin_id, comments, _now(), request_id, STATUS_PENDING_ADMIN_APPROVAL),
    )
    if cur.rowcount == 0:
        db.rollback()
        return False, "Request not found or not pending."
    db.commit()
    return True, None


def status_display(status: str) -> str:
    s = (status or "").upper()
    return {
        STATUS_PENDING_ACCOUNTANT_REVIEW: "Pending accountant review",
        STATUS_PENDING_ADMIN_APPROVAL: "Pending admin approval",
        STATUS_APPROVED: "Approved",
        STATUS_REJECTED: "Rejected",
    }.get(s, status or "—")
