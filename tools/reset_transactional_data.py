"""
Clear all transactional / operational data from the FuelGuard SQLite database.

Preserves: users, system_settings (e.g. station name).

Resets: fuel_stock to default levels and retail prices (see fuel_sale_model defaults).

Usage:
  python tools/reset_transactional_data.py --confirm RESET

Optional:
  python tools/reset_transactional_data.py --database "C:\\path\\to\\fuelguard.db" --confirm RESET
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.config.settings import Config  # noqa: E402
from backend.models import fuel_sale_model  # noqa: E402


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
        (name,),
    ).fetchone()
    return row is not None


def _clear_sequence(conn: sqlite3.Connection, table: str) -> None:
    if not _table_exists(conn, "sqlite_sequence"):
        return
    conn.execute("DELETE FROM sqlite_sequence WHERE name = ?", (table,))


def reset_database(db_path: Path) -> None:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        conn.execute("BEGIN IMMEDIATE")
        tables = [
            "fuel_sales",
            "fuel_records",
            "fuel_purchases",
            "expenses",
            "fuel_adjustments",
            "fuel_adjustment_requests",
            "shifts",
            "alerts",
            "audit_logs",
            "approval_requests",
            "fuel_orders",
        ]
        for t in tables:
            if _table_exists(conn, t):
                conn.execute(f"DELETE FROM {t}")
                _clear_sequence(conn, t)

        if not _table_exists(conn, "fuel_stock"):
            raise RuntimeError("fuel_stock table missing; run the app once to initialize the schema.")

        stock_cols = {r["name"] for r in conn.execute("PRAGMA table_info(fuel_stock)").fetchall()}
        sets = [
            "available_litres = ?",
            "last_updated = CURRENT_TIMESTAMP",
        ]
        params: list[float | int] = [fuel_sale_model.DEFAULT_STOCK_LITRES]
        if "minimum_level" in stock_cols:
            sets.append("minimum_level = ?")
            params.append(fuel_sale_model.DEFAULT_MINIMUM_LITRES)
        if "minimum_threshold" in stock_cols:
            sets.append("minimum_threshold = ?")
            params.append(fuel_sale_model.DEFAULT_MINIMUM_LITRES)
        if "tank_capacity" in stock_cols:
            sets.append("tank_capacity = ?")
            params.append(fuel_sale_model.DEFAULT_TANK_CAPACITY_LITRES)
        if "selling_price_per_litre" in stock_cols:
            sets.append("selling_price_per_litre = ?")
            params.append(fuel_sale_model.DEFAULT_RETAIL_PRICE_PER_LITRE)

        sql = f"UPDATE fuel_stock SET {', '.join(sets)}"
        conn.execute(sql, params)

        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--database",
        type=str,
        default=None,
        help=f"SQLite file (default: Config.DATABASE_PATH = {Config.DATABASE_PATH!r})",
    )
    p.add_argument(
        "--confirm",
        type=str,
        required=True,
        help='Must be exactly "RESET" to run destructive deletes.',
    )
    args = p.parse_args()
    if args.confirm != "RESET":
        print('Error: pass --confirm RESET to acknowledge clearing all transactional data.', file=sys.stderr)
        return 2

    path = Path(args.database or Config.DATABASE_PATH).resolve()
    if not path.is_file():
        print(f"Error: database file not found: {path}", file=sys.stderr)
        return 1

    reset_database(path)
    print(f"OK: cleared transactional tables and reset fuel_stock defaults on {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
