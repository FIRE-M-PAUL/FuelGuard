"""Fuel retail sales and stock (salesperson workflow)."""
from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from typing import Any

from backend.models.user_model import get_db

ALLOWED_FUEL_TYPES = frozenset({"Petrol", "Diesel"})
ALLOWED_PAYMENT_METHODS = frozenset({"Cash", "Mobile Money", "Card"})
DEFAULT_STOCK_LITRES = 10_000.0
DEFAULT_MINIMUM_LITRES = 1_200.0
DEFAULT_RETAIL_PRICE_PER_LITRE = 2.50


def _migrate_fuel_stock_minimum(db: sqlite3.Connection) -> None:
    cols = {row["name"] for row in db.execute("PRAGMA table_info(fuel_stock)").fetchall()}
    if "minimum_level" not in cols:
        db.execute(
            f"""
            ALTER TABLE fuel_stock ADD COLUMN minimum_level REAL NOT NULL DEFAULT {DEFAULT_MINIMUM_LITRES}
            """
        )


def _migrate_fuel_stock_selling_price(db: sqlite3.Connection) -> None:
    cols = {row["name"] for row in db.execute("PRAGMA table_info(fuel_stock)").fetchall()}
    if "selling_price_per_litre" not in cols:
        db.execute(
            f"""
            ALTER TABLE fuel_stock ADD COLUMN selling_price_per_litre REAL NOT NULL DEFAULT {DEFAULT_RETAIL_PRICE_PER_LITRE}
            """
        )


def init_db() -> None:
    db = get_db()
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS fuel_sales (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fuel_type TEXT NOT NULL,
            quantity REAL NOT NULL,
            price_per_litre REAL NOT NULL,
            total_amount REAL NOT NULL,
            payment_method TEXT NOT NULL,
            customer_name TEXT NOT NULL,
            vehicle_number TEXT NOT NULL,
            salesperson_id INTEGER NOT NULL,
            sale_date TIMESTAMP NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            CHECK (quantity > 0),
            CHECK (price_per_litre > 0),
            CHECK (total_amount > 0),
            FOREIGN KEY(salesperson_id) REFERENCES users(id) ON DELETE RESTRICT
        );

        CREATE TABLE IF NOT EXISTS fuel_stock (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fuel_type TEXT NOT NULL UNIQUE,
            available_litres REAL NOT NULL DEFAULT 0,
            last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            CHECK (available_litres >= 0)
        );

        CREATE INDEX IF NOT EXISTS idx_fuel_sales_salesperson ON fuel_sales(salesperson_id);
        CREATE INDEX IF NOT EXISTS idx_fuel_sales_sale_date ON fuel_sales(sale_date);
        """
    )
    for ft in sorted(ALLOWED_FUEL_TYPES):
        db.execute(
            """
            INSERT OR IGNORE INTO fuel_stock (fuel_type, available_litres)
            VALUES (?, ?)
            """,
            (ft, DEFAULT_STOCK_LITRES),
        )
    _migrate_fuel_stock_minimum(db)
    _migrate_fuel_stock_selling_price(db)
    db.commit()


def get_all_stock() -> list[sqlite3.Row]:
    db = get_db()
    cur = db.execute(
        "SELECT * FROM fuel_stock ORDER BY fuel_type COLLATE NOCASE"
    )
    return cur.fetchall()


def get_retail_price_per_litre(fuel_type: str) -> float | None:
    row = get_stock_row(fuel_type.strip())
    if not row:
        return None
    try:
        p = float(row["selling_price_per_litre"])
    except (KeyError, TypeError, ValueError):
        p = DEFAULT_RETAIL_PRICE_PER_LITRE
    return p if p > 0 else None


def get_retail_prices_dict() -> dict[str, float]:
    return {
        str(r["fuel_type"]): float(r["selling_price_per_litre"])
        for r in get_all_stock()
    }


def set_retail_price_per_litre(fuel_type: str, price: float) -> tuple[bool, str | None]:
    if fuel_type.strip() not in ALLOWED_FUEL_TYPES:
        return False, "Invalid fuel type."
    if price <= 0:
        return False, "Price must be positive."
    db = get_db()
    cur = db.execute(
        """
        UPDATE fuel_stock
        SET selling_price_per_litre = ?, last_updated = CURRENT_TIMESTAMP
        WHERE fuel_type = ?
        """,
        (round(price, 4), fuel_type.strip()),
    )
    db.commit()
    if cur.rowcount == 0:
        return False, "Fuel type not in stock catalog."
    return True, None


def stock_status(available_litres: float, minimum_level: float) -> str:
    """Normal, Low, or Critical (for manager stock monitor)."""
    if available_litres <= minimum_level * 0.5:
        return "Critical"
    if available_litres <= minimum_level:
        return "Low"
    return "Normal"


def list_stock_for_manager() -> list[dict[str, Any]]:
    rows = get_all_stock()
    out: list[dict[str, Any]] = []
    for r in rows:
        avail = float(r["available_litres"])
        try:
            min_l = float(r["minimum_level"])
        except (KeyError, TypeError, ValueError):
            min_l = DEFAULT_MINIMUM_LITRES
        out.append(
            {
                "fuel_type": r["fuel_type"],
                "available_litres": avail,
                "minimum_level": min_l,
                "status": stock_status(avail, min_l),
            }
        )
    return out


def retail_sales_summary_today() -> tuple[float, int]:
    today = datetime.now(UTC).date().isoformat()
    db = get_db()
    row = db.execute(
        """
        SELECT COALESCE(SUM(quantity), 0) AS litres, COUNT(*) AS cnt
        FROM fuel_sales
        WHERE date(sale_date) = date(?)
        """,
        (today,),
    ).fetchone()
    return float(row["litres"]), int(row["cnt"])


def list_recent_retail_sales(*, limit: int = 12) -> list[sqlite3.Row]:
    db = get_db()
    cur = db.execute(
        """
        SELECT fs.*, u.username AS salesperson_username
        FROM fuel_sales fs
        JOIN users u ON u.id = fs.salesperson_id
        ORDER BY fs.sale_date DESC, fs.id DESC
        LIMIT ?
        """,
        (limit,),
    )
    return cur.fetchall()


def get_stock_row(fuel_type: str) -> sqlite3.Row | None:
    db = get_db()
    cur = db.execute(
        "SELECT * FROM fuel_stock WHERE fuel_type = ?",
        (fuel_type.strip(),),
    )
    return cur.fetchone()


def get_sale_by_id(sale_id: int) -> sqlite3.Row | None:
    db = get_db()
    cur = db.execute(
        """
        SELECT fs.*, u.username AS salesperson_username
        FROM fuel_sales fs
        JOIN users u ON u.id = fs.salesperson_id
        WHERE fs.id = ?
        """,
        (sale_id,),
    )
    return cur.fetchone()


def list_sales_by_salesperson(salesperson_id: int, *, limit: int = 20) -> list[sqlite3.Row]:
    db = get_db()
    cur = db.execute(
        """
        SELECT * FROM fuel_sales
        WHERE salesperson_id = ?
        ORDER BY sale_date DESC, id DESC
        LIMIT ?
        """,
        (salesperson_id, limit),
    )
    return cur.fetchall()


def list_all_sales_for_accounting(
    *,
    search: str | None = None,
    payment_method: str | None = None,
    fuel_type: str | None = None,
    verified_only: bool | None = None,
    unverified_only: bool | None = None,
    sort: str = "date_desc",
) -> list[sqlite3.Row]:
    """List retail sales with salesperson name for accountant views."""
    db = get_db()
    clauses: list[str] = ["1=1"]
    params: list = []
    if search:
        like = f"%{search.strip()}%"
        clauses.append(
            "(CAST(fs.id AS TEXT) LIKE ? OR fs.customer_name LIKE ? OR fs.vehicle_number LIKE ? "
            "OR u.username LIKE ?)"
        )
        params.extend([like, like, like, like])
    if payment_method:
        clauses.append("fs.payment_method = ?")
        params.append(payment_method)
    if fuel_type:
        clauses.append("fs.fuel_type = ?")
        params.append(fuel_type)
    if verified_only:
        clauses.append("COALESCE(fs.payment_verified, 0) = 1")
    if unverified_only:
        clauses.append("COALESCE(fs.payment_verified, 0) = 0")
    where = " AND ".join(clauses)
    order = {
        "date_desc": "fs.sale_date DESC, fs.id DESC",
        "date_asc": "fs.sale_date ASC, fs.id ASC",
        "amount_desc": "fs.total_amount DESC, fs.id DESC",
        "amount_asc": "fs.total_amount ASC, fs.id ASC",
        "id_desc": "fs.id DESC",
    }.get(sort, "fs.sale_date DESC, fs.id DESC")
    cur = db.execute(
        f"""
        SELECT fs.*, u.username AS salesperson_username
        FROM fuel_sales fs
        JOIN users u ON u.id = fs.salesperson_id
        WHERE {where}
        ORDER BY {order}
        """,
        params,
    )
    return cur.fetchall()


def set_payment_verified(sale_id: int, *, verified_by: int, verified: bool = True) -> bool:
    db = get_db()
    cur = db.execute("SELECT id FROM fuel_sales WHERE id = ?", (sale_id,))
    if not cur.fetchone():
        return False
    when = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S") if verified else None
    db.execute(
        """
        UPDATE fuel_sales
        SET payment_verified = ?, verified_at = ?, verified_by = ?
        WHERE id = ?
        """,
        (1 if verified else 0, when, verified_by if verified else None, sale_id),
    )
    db.commit()
    return True


def record_sale(
    *,
    fuel_type: str,
    quantity: float,
    price_per_litre: float,
    total_amount: float,
    payment_method: str,
    customer_name: str,
    vehicle_number: str,
    salesperson_id: int,
    sale_date: str | None = None,
) -> tuple[int | None, str | None]:
    """Atomic sale + stock decrement. Returns (sale_id, error_message)."""
    if fuel_type not in ALLOWED_FUEL_TYPES:
        return None, "Invalid fuel type."
    if payment_method not in ALLOWED_PAYMENT_METHODS:
        return None, "Invalid payment method."
    if quantity <= 0:
        return None, "Quantity must be positive."
    if price_per_litre <= 0:
        return None, "Price per litre must be positive."
    expected = round(quantity * price_per_litre, 2)
    if abs(expected - round(total_amount, 2)) > 0.02:
        return None, "Total amount does not match quantity and price."

    when = sale_date or datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
    db = get_db()
    try:
        db.execute("BEGIN IMMEDIATE")
        cur = db.execute(
            "SELECT available_litres FROM fuel_stock WHERE fuel_type = ?",
            (fuel_type,),
        )
        row = cur.fetchone()
        if not row:
            db.rollback()
            return None, "Fuel type not in stock system."
        available = float(row["available_litres"])
        if quantity > available:
            db.rollback()
            return None, "Insufficient stock for this fuel type."
        db.execute(
            """
            UPDATE fuel_stock
            SET available_litres = available_litres - ?,
                last_updated = CURRENT_TIMESTAMP
            WHERE fuel_type = ?
            """,
            (quantity, fuel_type),
        )
        cur = db.execute(
            """
            INSERT INTO fuel_sales (
                fuel_type, quantity, price_per_litre, total_amount,
                payment_method, customer_name, vehicle_number,
                salesperson_id, sale_date
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                fuel_type,
                quantity,
                price_per_litre,
                expected,
                payment_method,
                customer_name.strip(),
                vehicle_number.strip(),
                salesperson_id,
                when,
            ),
        )
        sale_id = int(cur.lastrowid)
        db.commit()
        return sale_id, None
    except Exception:
        db.rollback()
        raise
