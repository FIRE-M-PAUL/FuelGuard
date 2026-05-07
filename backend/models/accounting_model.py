"""Expenses, fuel purchases, and finance aggregates for accountants."""
from __future__ import annotations

import sqlite3
from datetime import date, timedelta
from typing import Any

from backend.models.fuel_sale_model import ALLOWED_FUEL_TYPES
from backend.models.user_model import get_db
from backend.utils.timezone import date_days_ago_cat_iso, now_cat, today_cat_iso

EXPENSE_CATEGORIES = frozenset(
    {"Fuel Purchase", "Maintenance", "Salary", "Utilities", "Other"}
)

_LEGACY_EXPENSE_CATEGORY_MAP = {
    "Operations": "Other",
    "Admin": "Other",
    "Payroll": "Salary",
    "Maintenance": "Maintenance",
    "Utilities": "Utilities",
    "Other": "Other",
}


def _migrate_fuel_sales_verification(db: sqlite3.Connection) -> None:
    cols = {row["name"] for row in db.execute("PRAGMA table_info(fuel_sales)").fetchall()}
    if "payment_verified" not in cols:
        db.execute(
            "ALTER TABLE fuel_sales ADD COLUMN payment_verified INTEGER NOT NULL DEFAULT 0"
        )
    if "verified_at" not in cols:
        db.execute("ALTER TABLE fuel_sales ADD COLUMN verified_at TIMESTAMP")
    if "verified_by" not in cols:
        db.execute("ALTER TABLE fuel_sales ADD COLUMN verified_by INTEGER")


def _migrate_expense_columns(db: sqlite3.Connection) -> None:
    cols = {row["name"] for row in db.execute("PRAGMA table_info(expenses)").fetchall()}
    if "expense_name" not in cols:
        db.execute("ALTER TABLE expenses ADD COLUMN expense_name TEXT")
    db.execute(
        """
        UPDATE expenses
        SET expense_name = description
        WHERE expense_name IS NULL OR trim(expense_name) = ''
        """
    )


def _migrate_expense_categories_inplace(db: sqlite3.Connection) -> None:
    for old, new in _LEGACY_EXPENSE_CATEGORY_MAP.items():
        if old == new:
            continue
        db.execute("UPDATE expenses SET category = ? WHERE category = ?", (new, old))


def init_db() -> None:
    db = get_db()
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS expenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            description TEXT NOT NULL,
            amount REAL NOT NULL,
            category TEXT NOT NULL,
            date TIMESTAMP NOT NULL,
            recorded_by INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            CHECK (amount > 0),
            FOREIGN KEY(recorded_by) REFERENCES users(id) ON DELETE RESTRICT
        );

        CREATE TABLE IF NOT EXISTS fuel_purchases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            supplier_name TEXT NOT NULL,
            fuel_type TEXT NOT NULL,
            quantity REAL NOT NULL,
            price_per_litre REAL NOT NULL,
            total_cost REAL NOT NULL,
            purchase_date TIMESTAMP NOT NULL,
            recorded_by INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            CHECK (quantity > 0),
            CHECK (price_per_litre > 0),
            CHECK (total_cost > 0),
            FOREIGN KEY(recorded_by) REFERENCES users(id) ON DELETE RESTRICT
        );

        CREATE INDEX IF NOT EXISTS idx_expenses_date ON expenses(date);
        CREATE INDEX IF NOT EXISTS idx_expenses_recorded ON expenses(recorded_by);
        CREATE INDEX IF NOT EXISTS idx_purchases_date ON fuel_purchases(purchase_date);
        """
    )
    _migrate_fuel_sales_verification(db)
    _migrate_expense_columns(db)
    _migrate_expense_categories_inplace(db)
    db.commit()


def add_expense(
    *,
    expense_name: str | None,
    description: str,
    amount: float,
    category: str,
    date_str: str,
    recorded_by: int,
) -> int:
    db = get_db()
    name = (expense_name or description or "").strip() or "Expense"
    cur = db.execute(
        """
        INSERT INTO expenses (expense_name, description, amount, category, date, recorded_by)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            name,
            description.strip(),
            amount,
            category.strip(),
            date_str,
            recorded_by,
        ),
    )
    db.commit()
    return int(cur.lastrowid)


def list_expenses(*, limit: int = 200) -> list[sqlite3.Row]:
    db = get_db()
    cur = db.execute(
        """
        SELECT e.*, u.username AS recorded_by_username
        FROM expenses e
        JOIN users u ON u.id = e.recorded_by
        ORDER BY e.date DESC, e.id DESC
        LIMIT ?
        """,
        (limit,),
    )
    return cur.fetchall()


def list_expenses_filtered(
    *,
    date_from: str | None = None,
    date_to: str | None = None,
    category: str | None = None,
    limit: int = 500,
) -> list[sqlite3.Row]:
    db = get_db()
    clauses: list[str] = ["1=1"]
    params: list[Any] = []
    if date_from:
        clauses.append("date(e.date) >= date(?)")
        params.append(date_from)
    if date_to:
        clauses.append("date(e.date) <= date(?)")
        params.append(date_to)
    if category:
        clauses.append("e.category = ?")
        params.append(category)
    where = " AND ".join(clauses)
    params.append(limit)
    return db.execute(
        f"""
        SELECT e.*, u.username AS recorded_by_username
        FROM expenses e
        JOIN users u ON u.id = e.recorded_by
        WHERE {where}
        ORDER BY e.date DESC, e.id DESC
        LIMIT ?
        """,
        params,
    ).fetchall()


def total_expenses_filtered(
    *,
    date_from: str | None = None,
    date_to: str | None = None,
    category: str | None = None,
) -> float:
    db = get_db()
    clauses: list[str] = ["1=1"]
    params: list[Any] = []
    if date_from:
        clauses.append("date(date) >= date(?)")
        params.append(date_from)
    if date_to:
        clauses.append("date(date) <= date(?)")
        params.append(date_to)
    if category:
        clauses.append("category = ?")
        params.append(category)
    where = " AND ".join(clauses)
    row = db.execute(
        f"SELECT COALESCE(SUM(amount), 0) AS s FROM expenses WHERE {where}",
        params,
    ).fetchone()
    manual = float(row["s"] or 0) if row else 0.0
    if category and category != "Fuel Purchase":
        return manual

    p_clauses: list[str] = ["1=1"]
    p_params: list[Any] = []
    if date_from:
        p_clauses.append("date(purchase_date) >= date(?)")
        p_params.append(date_from)
    if date_to:
        p_clauses.append("date(purchase_date) <= date(?)")
        p_params.append(date_to)
    p_where = " AND ".join(p_clauses)
    prow = db.execute(
        f"SELECT COALESCE(SUM(total_cost), 0) AS s FROM fuel_purchases WHERE {p_where}",
        p_params,
    ).fetchone()
    purchases = float(prow["s"] or 0) if prow else 0.0
    return manual + purchases


def get_expense(expense_id: int) -> sqlite3.Row | None:
    db = get_db()
    return db.execute("SELECT * FROM expenses WHERE id = ?", (expense_id,)).fetchone()


def update_expense(
    expense_id: int,
    *,
    expense_name: str,
    description: str,
    amount: float,
    category: str,
    date_str: str,
) -> bool:
    db = get_db()
    cur = db.execute(
        """
        UPDATE expenses
        SET expense_name = ?, description = ?, amount = ?, category = ?, date = ?
        WHERE id = ?
        """,
        (expense_name.strip(), description.strip(), amount, category.strip(), date_str, expense_id),
    )
    db.commit()
    return cur.rowcount > 0


def delete_expense(expense_id: int) -> bool:
    db = get_db()
    cur = db.execute("DELETE FROM expenses WHERE id = ?", (expense_id,))
    db.commit()
    return cur.rowcount > 0


def total_fuel_purchase_cost_between(date_from: str, date_to: str) -> float:
    db = get_db()
    row = db.execute(
        """
        SELECT COALESCE(SUM(total_cost), 0) AS s
        FROM fuel_purchases
        WHERE date(purchase_date) >= date(?) AND date(purchase_date) <= date(?)
        """,
        (date_from, date_to),
    ).fetchone()
    return float(row["s"]) if row else 0.0


def normalize_fuel_purchase_calendar_date(raw: str) -> tuple[str | None, str | None]:
    """Coerce ``date`` / ``datetime-local`` form values to ``YYYY-MM-DD`` (station calendar day)."""
    s = (raw or "").strip()
    if not s:
        return None, "Purchase date is required."
    if "T" in s:
        s = s.split("T", 1)[0].strip()
    elif len(s) > 10 and s[10] == " ":
        s = s[:10].strip()
    try:
        date.fromisoformat(s)
    except ValueError:
        return None, "Invalid purchase date."
    return s, None


def record_fuel_purchase(
    *,
    supplier_name: str,
    fuel_type: str,
    quantity: float,
    price_per_litre: float,
    total_cost: float,
    purchase_date: str,
    recorded_by: int,
) -> tuple[int | None, str | None]:
    norm_date, date_err = normalize_fuel_purchase_calendar_date(purchase_date)
    if date_err or not norm_date:
        return None, date_err or "Invalid purchase date."
    purchase_date = norm_date

    if fuel_type not in ALLOWED_FUEL_TYPES:
        return None, "Invalid fuel type."
    expected = round(quantity * price_per_litre, 2)
    if abs(expected - round(total_cost, 2)) > 0.02:
        return None, "Total cost does not match quantity and price."
    if quantity <= 0 or price_per_litre <= 0:
        return None, "Quantity and price must be positive."

    db = get_db()
    chk = db.execute(
        "SELECT 1 FROM fuel_stock WHERE fuel_type = ?", (fuel_type,)
    ).fetchone()
    if not chk:
        return None, "Fuel type not in stock catalog."
    try:
        db.execute("BEGIN IMMEDIATE")
        cur = db.execute(
            """
            INSERT INTO fuel_purchases (
                supplier_name, fuel_type, quantity, price_per_litre,
                total_cost, purchase_date, recorded_by
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                supplier_name.strip(),
                fuel_type,
                quantity,
                price_per_litre,
                expected,
                purchase_date,
                recorded_by,
            ),
        )
        pid = int(cur.lastrowid)
        db.execute(
            """
            UPDATE fuel_stock
            SET available_litres = available_litres + ?,
                last_updated = CURRENT_TIMESTAMP
            WHERE fuel_type = ?
            """,
            (quantity, fuel_type),
        )
        db.commit()
        return pid, None
    except Exception:
        db.rollback()
        raise


def list_fuel_purchases(*, limit: int = 200) -> list[sqlite3.Row]:
    db = get_db()
    cur = db.execute(
        """
        SELECT fp.*, u.username AS recorded_by_username
        FROM fuel_purchases fp
        JOIN users u ON u.id = fp.recorded_by
        ORDER BY fp.purchase_date DESC, fp.id DESC
        LIMIT ?
        """,
        (limit,),
    )
    return cur.fetchall()


def total_revenue_between(date_from: str, date_to: str) -> float:
    db = get_db()
    row = db.execute(
        """
        SELECT COALESCE(SUM(total_amount), 0) AS s
        FROM fuel_sales
        WHERE date(sale_date) >= date(?) AND date(sale_date) <= date(?)
        """,
        (date_from, date_to),
    ).fetchone()
    return float(row["s"]) if row else 0.0


def total_expenses_between(date_from: str, date_to: str) -> float:
    """Manual expenses plus fuel purchase costs (recorded under Fuel Purchases)."""
    db = get_db()
    row = db.execute(
        """
        SELECT COALESCE(SUM(amount), 0) AS s
        FROM expenses
        WHERE date(date) >= date(?) AND date(date) <= date(?)
        """,
        (date_from, date_to),
    ).fetchone()
    manual = float(row["s"] or 0) if row else 0.0
    return manual + total_fuel_purchase_cost_between(date_from, date_to)


def count_sales_between(date_from: str, date_to: str) -> int:
    db = get_db()
    row = db.execute(
        """
        SELECT COUNT(*) AS c FROM fuel_sales
        WHERE date(sale_date) >= date(?) AND date(sale_date) <= date(?)
        """,
        (date_from, date_to),
    ).fetchone()
    return int(row["c"]) if row else 0


def total_purchased_litres_between(date_from: str, date_to: str) -> float:
    db = get_db()
    row = db.execute(
        """
        SELECT COALESCE(SUM(quantity), 0) AS s
        FROM fuel_purchases
        WHERE date(purchase_date) >= date(?) AND date(purchase_date) <= date(?)
        """,
        (date_from, date_to),
    ).fetchone()
    return float(row["s"]) if row else 0.0


def payment_method_summary_today() -> list[sqlite3.Row]:
    db = get_db()
    today = today_cat_iso()
    return db.execute(
        """
        SELECT payment_method, COUNT(*) AS cnt, COALESCE(SUM(total_amount), 0) AS total
        FROM fuel_sales
        WHERE date(sale_date) = date(?)
        GROUP BY payment_method
        ORDER BY total DESC
        """,
        (today,),
    ).fetchall()


def daily_series_last_days(days: int = 7) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Revenue and expense totals per day for simple charts."""
    db = get_db()
    start = date_days_ago_cat_iso(days - 1)
    rev_rows = db.execute(
        """
        SELECT date(sale_date) AS d, COALESCE(SUM(total_amount), 0) AS total
        FROM fuel_sales
        WHERE date(sale_date) >= date(?)
        GROUP BY date(sale_date)
        """,
        (start,),
    ).fetchall()
    exp_rows = db.execute(
        """
        SELECT date(date) AS d, COALESCE(SUM(amount), 0) AS total
        FROM expenses
        WHERE date(date) >= date(?)
        GROUP BY date(date)
        """,
        (start,),
    ).fetchall()
    pur_rows = db.execute(
        """
        SELECT date(purchase_date) AS d, COALESCE(SUM(total_cost), 0) AS total
        FROM fuel_purchases
        WHERE date(purchase_date) >= date(?)
        GROUP BY date(purchase_date)
        """,
        (start,),
    ).fetchall()
    rev_map = {r["d"]: float(r["total"]) for r in rev_rows}
    exp_map = {r["d"]: float(r["total"]) for r in exp_rows}
    for r in pur_rows:
        d = r["d"]
        exp_map[d] = exp_map.get(d, 0.0) + float(r["total"] or 0)
    out_rev: list[dict[str, Any]] = []
    out_exp: list[dict[str, Any]] = []
    for i in range(days):
        d = (now_cat().date() - timedelta(days=days - 1 - i)).isoformat()
        out_rev.append({"day": d, "total": rev_map.get(d, 0.0)})
        out_exp.append({"day": d, "total": exp_map.get(d, 0.0)})
    return out_rev, out_exp


def recent_mixed_activity(*, limit: int = 12) -> list[dict[str, Any]]:
    db = get_db()
    items: list[dict[str, Any]] = []
    for r in db.execute(
        """
        SELECT 'sale' AS kind, id, total_amount AS amount, sale_date AS at,
               fuel_type || ' sale' AS label
        FROM fuel_sales
        ORDER BY sale_date DESC, id DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall():
        items.append(dict(r))
    for r in db.execute(
        """
        SELECT 'expense' AS kind, id, amount, date AS at, category || ': ' || substr(description,1,40) AS label
        FROM expenses
        ORDER BY date DESC, id DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall():
        items.append(dict(r))
    for r in db.execute(
        """
        SELECT 'purchase' AS kind, id, total_cost AS amount, purchase_date AS at,
               'Purchase ' || fuel_type AS label
        FROM fuel_purchases
        ORDER BY purchase_date DESC, id DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall():
        items.append(dict(r))
    items.sort(key=lambda x: str(x["at"]), reverse=True)
    return items[:limit]


def get_finance_snapshot() -> dict[str, Any]:
    """Single-day and rolling figures for accountant dashboard."""
    today = today_cat_iso()
    month_start = now_cat().date().replace(day=1).isoformat()
    revenue_today = total_revenue_between(today, today)
    expenses_today = total_expenses_between(today, today)
    profit_today = revenue_today - expenses_today
    sales_count_today = count_sales_between(today, today)
    purchases_litres_today = total_purchased_litres_between(today, today)
    revenue_month = total_revenue_between(month_start, today)
    expenses_month = total_expenses_between(month_start, today)
    profit_month = revenue_month - expenses_month
    payment_rows = payment_method_summary_today()
    rev_series, exp_series = daily_series_last_days(7)
    activity = recent_mixed_activity(limit=12)
    rmax = max((x["total"] for x in rev_series), default=0.0)
    emax = max((x["total"] for x in exp_series), default=0.0)
    chart_max = max(rmax, emax, 1.0)
    return {
        "today": today,
        "revenue_today": revenue_today,
        "expenses_today": expenses_today,
        "profit_today": profit_today,
        "sales_count_today": sales_count_today,
        "purchases_litres_today": purchases_litres_today,
        "revenue_month": revenue_month,
        "expenses_month": expenses_month,
        "profit_month": profit_month,
        "payment_summary": payment_rows,
        "rev_series": rev_series,
        "exp_series": exp_series,
        "chart_max": chart_max,
        "recent_activity": activity,
    }


def export_daily_sales_rows(day: str) -> list[list[Any]]:
    db = get_db()
    cur = db.execute(
        """
        SELECT fs.id, fs.fuel_type, fs.quantity, fs.price_per_litre, fs.total_amount,
               fs.payment_method, fs.sale_date, u.username
        FROM fuel_sales fs
        JOIN users u ON u.id = fs.salesperson_id
        WHERE date(fs.sale_date) = date(?)
        ORDER BY fs.id
        """,
        (day,),
    )
    rows: list[list[Any]] = [
        [
            "id",
            "fuel_type",
            "quantity",
            "price_per_litre",
            "total_amount",
            "payment_method",
            "sale_date",
            "salesperson",
        ]
    ]
    for r in cur.fetchall():
        rows.append(
            [
                r["id"],
                r["fuel_type"],
                r["quantity"],
                r["price_per_litre"],
                r["total_amount"],
                r["payment_method"],
                r["sale_date"],
                r["username"],
            ]
        )
    return rows


def export_monthly_revenue_rows(year: int, month: int) -> list[list[Any]]:
    db = get_db()
    ym = f"{year:04d}-{month:02d}"
    cur = db.execute(
        """
        SELECT date(sale_date) AS d, COUNT(*) AS cnt, COALESCE(SUM(total_amount), 0) AS revenue
        FROM fuel_sales
        WHERE strftime('%Y-%m', sale_date) = ?
        GROUP BY date(sale_date)
        ORDER BY d
        """,
        (ym,),
    )
    rows: list[list[Any]] = [["date", "sale_count", "revenue"]]
    for r in cur.fetchall():
        rows.append([r["d"], r["cnt"], r["revenue"]])
    return rows


def export_expenses_rows(date_from: str, date_to: str) -> list[list[Any]]:
    db = get_db()
    cur = db.execute(
        """
        SELECT e.id, e.description, e.amount, e.category, e.date, u.username
        FROM expenses e
        JOIN users u ON u.id = e.recorded_by
        WHERE date(e.date) >= date(?) AND date(e.date) <= date(?)
        ORDER BY e.date, e.id
        """,
        (date_from, date_to),
    )
    rows: list[list[Any]] = [
        ["id", "description", "amount", "category", "date", "recorded_by"],
    ]
    for r in cur.fetchall():
        rows.append(
            [
                r["id"],
                r["description"],
                r["amount"],
                r["category"],
                r["date"],
                r["username"],
            ]
        )
    return rows


def export_pnl_summary_rows(date_from: str, date_to: str) -> list[list[Any]]:
    rev = total_revenue_between(date_from, date_to)
    exp = total_expenses_between(date_from, date_to)
    return [
        ["metric", "amount"],
        ["total_revenue", rev],
        ["total_expenses", exp],
        ["net_profit", rev - exp],
    ]
