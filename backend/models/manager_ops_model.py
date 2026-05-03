"""Aggregates and CSV exports for manager operational views."""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from backend.models import fuel_model, fuel_sale_model


def get_manager_dashboard_bundle() -> dict[str, Any]:
    litres_today, sales_count_today = fuel_sale_model.retail_sales_summary_today()
    stock_rows = fuel_sale_model.list_stock_for_manager()
    low_rows = [r for r in stock_rows if r["status"] in {"Low", "Critical"}]
    metrics = fuel_model.dashboard_metrics()
    recent_sales = fuel_sale_model.list_recent_retail_sales(limit=10)
    today = datetime.now(UTC).date().isoformat()
    return {
        "today": today,
        "litres_sold_today": litres_today,
        "sales_transactions_today": sales_count_today,
        "stock_rows": stock_rows,
        "low_fuel_rows": low_rows,
        "low_fuel_alert": len(low_rows) > 0,
        "metrics": metrics,
        "recent_sales": recent_sales,
    }


def export_fuel_usage_rows(date_from: str, date_to: str) -> list[list[Any]]:
    from backend.models.user_model import get_db

    db = get_db()
    cur = db.execute(
        """
        SELECT id, vehicle_id, driver_name, fuel_amount, fuel_type, record_date, status
        FROM fuel_records
        WHERE date(record_date) >= date(?) AND date(record_date) <= date(?)
        ORDER BY record_date, id
        """,
        (date_from, date_to),
    )
    rows: list[list[Any]] = [
        ["id", "vehicle_id", "driver_name", "fuel_amount", "fuel_type", "record_date", "status"],
    ]
    for r in cur.fetchall():
        rows.append(
            [
                r["id"],
                r["vehicle_id"],
                r["driver_name"],
                r["fuel_amount"],
                r["fuel_type"],
                r["record_date"],
                r["status"],
            ]
        )
    return rows


def export_stock_report_rows() -> list[list[Any]]:
    rows: list[list[Any]] = [
        ["fuel_type", "available_litres", "minimum_level", "status"],
    ]
    for r in fuel_sale_model.list_stock_for_manager():
        rows.append(
            [
                r["fuel_type"],
                r["available_litres"],
                r["minimum_level"],
                r["status"],
            ]
        )
    return rows


def export_operational_summary_rows() -> list[list[Any]]:
    bundle = get_manager_dashboard_bundle()
    m = bundle["metrics"]
    return [
        ["metric", "value"],
        ["date", bundle["today"]],
        ["retail_litres_sold_today", bundle["litres_sold_today"]],
        ["retail_sales_count_today", bundle["sales_transactions_today"]],
        ["low_fuel_alert_count", len(bundle["low_fuel_rows"])],
        ["fuel_records_total", m["total_records"]],
        ["fuel_records_pending", m["pending_requests"]],
        ["fuel_records_approved", m["approved_requests"]],
    ]
