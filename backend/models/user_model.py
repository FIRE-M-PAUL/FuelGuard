"""SQLite user persistence with parameterized queries."""
from __future__ import annotations

import sqlite3
from typing import Any

from flask import current_app, g

ALLOWED_ROLES = frozenset({"sales", "manager", "accountant", "admin"})
REGISTRABLE_ROLES = frozenset({"sales", "manager", "accountant"})
ALLOWED_STATUS = frozenset({"active", "inactive", "pending"})
STATUS_PENDING = "pending"


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        path = current_app.config["DATABASE_PATH"]
        g.db = sqlite3.connect(path)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def close_db(_: Any = None) -> None:
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db() -> None:
    db = get_db()
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            full_name TEXT,
            username TEXT NOT NULL UNIQUE,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL,
            phone TEXT,
            department TEXT,
            status TEXT NOT NULL DEFAULT 'active',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            CHECK (role IN ('sales', 'manager', 'accountant', 'admin')),
            CHECK (status IN ('active', 'inactive', 'pending'))
        );

        CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);
        CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
        CREATE INDEX IF NOT EXISTS idx_users_role ON users(role);
        CREATE INDEX IF NOT EXISTS idx_users_status ON users(status);
        """
    )
    columns = {row["name"] for row in db.execute("PRAGMA table_info(users)").fetchall()}
    if "full_name" not in columns:
        db.execute("ALTER TABLE users ADD COLUMN full_name TEXT")
    if "phone" not in columns:
        db.execute("ALTER TABLE users ADD COLUMN phone TEXT")
    db.commit()
    _migrate_users_table_for_pending_status(db)
    _migrate_users_remove_attendant_role(db)
    _repair_users_legacy_foreign_keys(db)
    _drop_orphan_users_legacy_table(db)


# When SQLite renames ``users``, it rewrites FK clauses in other tables to reference the new
# name (e.g. ``users_legacy``). Dropping ``users_legacy`` then leaves FKs pointing at a missing
# table. Rebuild ``users`` via a temp table + ``DROP users`` + ``RENAME`` so children keep
# referencing ``users`` throughout.
_FK_CHILD_INDEX_SQL: dict[str, tuple[str, ...]] = {
    "fuel_sales": (
        "CREATE INDEX IF NOT EXISTS idx_fuel_sales_salesperson ON fuel_sales(salesperson_id)",
        "CREATE INDEX IF NOT EXISTS idx_fuel_sales_sale_date ON fuel_sales(sale_date)",
    ),
    "fuel_records": (
        "CREATE INDEX IF NOT EXISTS idx_fuel_status ON fuel_records(status)",
        "CREATE INDEX IF NOT EXISTS idx_fuel_date ON fuel_records(record_date)",
        "CREATE INDEX IF NOT EXISTS idx_fuel_submitted_by ON fuel_records(submitted_by)",
        "CREATE INDEX IF NOT EXISTS idx_fuel_vehicle_id ON fuel_records(vehicle_id)",
    ),
    "expenses": (
        "CREATE INDEX IF NOT EXISTS idx_expenses_date ON expenses(date)",
        "CREATE INDEX IF NOT EXISTS idx_expenses_recorded ON expenses(recorded_by)",
    ),
    "fuel_purchases": (
        "CREATE INDEX IF NOT EXISTS idx_purchases_date ON fuel_purchases(purchase_date)",
    ),
    "shifts": (
        "CREATE INDEX IF NOT EXISTS idx_shifts_user ON shifts(user_id)",
        "CREATE INDEX IF NOT EXISTS idx_shifts_started ON shifts(started_at)",
        "CREATE INDEX IF NOT EXISTS idx_shifts_status ON shifts(status)",
    ),
}


def _migrate_users_table_for_pending_status(db: sqlite3.Connection) -> None:
    """Rebuild users if DB was created before `pending` status (SQLite CHECK cannot be altered)."""
    cur = db.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='users'")
    row = cur.fetchone()
    if not row or not row[0]:
        return
    ddl = row[0]
    if "pending" in ddl.lower():
        return

    db.execute("PRAGMA foreign_keys=OFF")
    db.execute("BEGIN IMMEDIATE")
    try:
        db.executescript(
            """
            CREATE TABLE users__pending_migrate (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                full_name TEXT,
                username TEXT NOT NULL UNIQUE,
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL,
                phone TEXT,
                department TEXT,
                status TEXT NOT NULL DEFAULT 'active',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                CHECK (role IN ('sales', 'manager', 'accountant', 'admin')),
                CHECK (status IN ('active', 'inactive', 'pending'))
            );
            INSERT INTO users__pending_migrate (
                id, full_name, username, email, password_hash, role, phone, department, status, created_at
            )
            SELECT
                id, full_name, username, email, password_hash,
                CASE WHEN LOWER(TRIM(role)) = 'attendant' THEN 'sales' ELSE role END,
                phone, department, status, created_at
            FROM users;
            DROP TABLE users;
            ALTER TABLE users__pending_migrate RENAME TO users;
            CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);
            CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
            CREATE INDEX IF NOT EXISTS idx_users_role ON users(role);
            CREATE INDEX IF NOT EXISTS idx_users_status ON users(status);
            """
        )
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.execute("PRAGMA foreign_keys=ON")


def _migrate_users_remove_attendant_role(db: sqlite3.Connection) -> None:
    """Map attendant accounts to sales and rebuild users CHECK without attendant."""
    cur = db.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='users'")
    row = cur.fetchone()
    if not row or not row[0]:
        return
    ddl = row[0]
    if "attendant" not in ddl.lower():
        return

    db.execute("PRAGMA foreign_keys=OFF")
    db.execute("BEGIN IMMEDIATE")
    try:
        db.executescript(
            """
            CREATE TABLE users__strip_att (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                full_name TEXT,
                username TEXT NOT NULL UNIQUE,
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL,
                phone TEXT,
                department TEXT,
                status TEXT NOT NULL DEFAULT 'active',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                CHECK (role IN ('sales', 'manager', 'accountant', 'admin')),
                CHECK (status IN ('active', 'inactive', 'pending'))
            );
            INSERT INTO users__strip_att (
                id, full_name, username, email, password_hash, role, phone, department, status, created_at
            )
            SELECT
                id, full_name, username, email, password_hash,
                CASE WHEN LOWER(TRIM(role)) = 'attendant' THEN 'sales' ELSE role END,
                phone, department, status, created_at
            FROM users;
            DROP TABLE users;
            ALTER TABLE users__strip_att RENAME TO users;
            CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);
            CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
            CREATE INDEX IF NOT EXISTS idx_users_role ON users(role);
            CREATE INDEX IF NOT EXISTS idx_users_status ON users(status);
            """
        )
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.execute("PRAGMA foreign_keys=ON")


def _repair_users_legacy_foreign_keys(db: sqlite3.Connection) -> None:
    """
    Fix databases broken by an older migration that RENAMEd ``users`` to ``users_legacy``:
    child tables still reference ``users_legacy`` after it was dropped.
    """
    rows = db.execute(
        """
        SELECT name, sql FROM sqlite_master
        WHERE type='table' AND sql IS NOT NULL AND instr(sql, 'users_legacy') > 0
        """
    ).fetchall()
    if not rows:
        return

    db.execute("PRAGMA foreign_keys=OFF")
    db.execute("BEGIN IMMEDIATE")
    try:
        for row in rows:
            name = row["name"]
            if name.startswith("sqlite_"):
                continue
            old_sql = row["sql"]
            new_sql = old_sql.replace("users_legacy", "users")
            if new_sql == old_sql:
                continue
            old_tbl = f"{name}__fk_rebuild_old"
            db.execute(f'ALTER TABLE "{name}" RENAME TO "{old_tbl}"')
            db.executescript(new_sql)
            cols_new = [r["name"] for r in db.execute(f'PRAGMA table_info("{name}")').fetchall()]
            cols_old = [r["name"] for r in db.execute(f'PRAGMA table_info("{old_tbl}")').fetchall()]
            common = [c for c in cols_new if c in cols_old]
            if not common:
                raise sqlite3.OperationalError(f"FK repair: no common columns for {name}")
            cc = ", ".join(f'"{c}"' for c in common)
            db.execute(f'INSERT INTO "{name}" ({cc}) SELECT {cc} FROM "{old_tbl}"')
            db.execute(f'DROP TABLE "{old_tbl}"')
            for stmt in _FK_CHILD_INDEX_SQL.get(name, ()):
                db.execute(stmt)
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.execute("PRAGMA foreign_keys=ON")


def _drop_orphan_users_legacy_table(db: sqlite3.Connection) -> None:
    """Remove leftover ``users_legacy`` after a failed or superseded RENAME migration."""
    leg = db.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='users_legacy'"
    ).fetchone()
    if not leg:
        return
    has_users = db.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='users'"
    ).fetchone()
    if not has_users:
        return
    db.execute("PRAGMA foreign_keys=OFF")
    try:
        db.execute("DROP TABLE IF EXISTS users_legacy")
        db.commit()
    finally:
        db.execute("PRAGMA foreign_keys=ON")


def get_user_by_username(username: str) -> sqlite3.Row | None:
    db = get_db()
    cur = db.execute(
        "SELECT * FROM users WHERE lower(username) = lower(?)",
        (username.strip(),),
    )
    return cur.fetchone()


def get_user_by_id(user_id: int) -> sqlite3.Row | None:
    db = get_db()
    cur = db.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    return cur.fetchone()


def get_user_by_email(email: str) -> sqlite3.Row | None:
    db = get_db()
    cur = db.execute(
        "SELECT * FROM users WHERE lower(email) = lower(?)",
        (email.strip(),),
    )
    return cur.fetchone()


def create_user(
    full_name: str | None,
    username: str,
    email: str,
    password_hash: str,
    role: str,
    phone: str | None,
    department: str | None,
    status: str,
) -> int:
    db = get_db()
    cur = db.execute(
        """
        INSERT INTO users (full_name, username, email, password_hash, role, phone, department, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            (full_name or "").strip() or username.strip(),
            username.strip(),
            email.strip().lower(),
            password_hash,
            role,
            (phone or "").strip() or None,
            (department or "").strip() or None,
            status,
        ),
    )
    db.commit()
    return int(cur.lastrowid)


def list_users() -> list[sqlite3.Row]:
    db = get_db()
    cur = db.execute(
        "SELECT id, username, email, role, department, status, created_at "
        "FROM users ORDER BY username COLLATE NOCASE"
    )
    return cur.fetchall()


def update_user(
    user_id: int,
    *,
    email: str | None = None,
    role: str | None = None,
    department: str | None = None,
    status: str | None = None,
    password_hash: str | None = None,
) -> None:
    db = get_db()
    fields: list[str] = []
    values: list[Any] = []
    if email is not None:
        fields.append("email = ?")
        values.append(email.strip().lower())
    if role is not None:
        fields.append("role = ?")
        values.append(role)
    if department is not None:
        fields.append("department = ?")
        values.append(department.strip() or None)
    if status is not None:
        fields.append("status = ?")
        values.append(status)
    if password_hash is not None:
        fields.append("password_hash = ?")
        values.append(password_hash)
    if not fields:
        return
    values.append(user_id)
    db.execute(f"UPDATE users SET {', '.join(fields)} WHERE id = ?", values)
    db.commit()


def delete_user(user_id: int) -> None:
    db = get_db()
    db.execute("DELETE FROM users WHERE id = ?", (user_id,))
    db.commit()


def count_users() -> int:
    db = get_db()
    cur = db.execute("SELECT COUNT(*) AS c FROM users")
    row = cur.fetchone()
    return int(row["c"]) if row else 0
