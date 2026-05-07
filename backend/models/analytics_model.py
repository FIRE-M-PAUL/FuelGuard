"""Aggregated analytics for manager and accountant dashboards."""
from __future__ import annotations

import sqlite3
from calendar import monthrange
from typing import Any

from backend.models import accounting_model, fuel_sale_model
from backend.models.user_model import get_db
from backend.utils.timezone import date_days_ago_cat_iso, now_cat, today_cat_iso


def _month_bounds(year: int, month: int) -> tuple[str, str]:
    last = monthrange(year, month)[1]
    return f"{year:04d}-{month:02d}-01", f"{year:04d}-{month:02d}-{last:02d}"


def get_analytics_bundle() -> dict[str, Any]:
    db = get_db()
    today = today_cat_iso()
    y, m = now_cat().year, now_cat().month
    month_start, month_end = _month_bounds(y, m)
    year_start = f"{y}-01-01"
    year_end = f"{y}-12-31"

    sales_today = db.execute(
        """
        SELECT COUNT(*) AS c, COALESCE(SUM(total_amount), 0) AS rev,
               COALESCE(SUM(quantity), 0) AS litres
        FROM fuel_sales WHERE date(sale_date) = date(?)
        """,
        (today,),
    ).fetchone()

    revenue_today = float(sales_today["rev"] or 0)
    exp_today = accounting_model.total_expenses_between(today, today)
    profit_today = revenue_today - exp_today

    monthly_rev = db.execute(
        """
        SELECT COALESCE(SUM(total_amount), 0) AS s FROM fuel_sales
        WHERE date(sale_date) >= date(?) AND date(sale_date) <= date(?)
        """,
        (month_start, month_end),
    ).fetchone()
    rev_m = float(monthly_rev["s"] or 0)
    exp_m = accounting_model.total_expenses_between(month_start, month_end)
    purchase_cost_m = accounting_model.total_fuel_purchase_cost_between(month_start, month_end)
    purchase_cost_today = accounting_model.total_fuel_purchase_cost_between(today, today)
    purchase_cost_y = accounting_model.total_fuel_purchase_cost_between(year_start, year_end)

    yearly_rev = db.execute(
        """
        SELECT COALESCE(SUM(total_amount), 0) AS s FROM fuel_sales
        WHERE date(sale_date) >= date(?) AND date(sale_date) <= date(?)
        """,
        (year_start, year_end),
    ).fetchone()
    rev_y = float(yearly_rev["s"] or 0)
    exp_y = accounting_model.total_expenses_between(year_start, year_end)

    stock_rows = fuel_sale_model.list_stock_for_manager()
    low_alerts = [r for r in stock_rows if r["status"] in {"Low", "Critical"}]

    top_fuel = db.execute(
        """
        SELECT fuel_type, COALESCE(SUM(quantity), 0) AS litres
        FROM fuel_sales
        WHERE date(sale_date) >= date(?) AND date(sale_date) <= date(?)
        GROUP BY fuel_type
        ORDER BY litres DESC
        LIMIT 1
        """,
        (month_start, month_end),
    ).fetchone()

    monthly_start = date_days_ago_cat_iso(365)
    monthly_series = db.execute(
        """
        SELECT strftime('%Y-%m', sale_date) AS ym, COALESCE(SUM(total_amount), 0) AS total
        FROM fuel_sales
        WHERE date(sale_date) >= date(?)
        GROUP BY ym
        ORDER BY ym ASC
        """,
        (monthly_start,),
    ).fetchall()

    daily_start = date_days_ago_cat_iso(13)
    daily_sales_14 = db.execute(
        """
        SELECT date(sale_date) AS d, COALESCE(SUM(total_amount), 0) AS total, COUNT(*) AS cnt
        FROM fuel_sales
        WHERE date(sale_date) >= date(?)
        GROUP BY date(sale_date)
        ORDER BY d ASC
        """,
        (daily_start,),
    ).fetchall()

    fuel_dist = db.execute(
        """
        SELECT fuel_type, COALESCE(SUM(quantity), 0) AS litres
        FROM fuel_sales
        WHERE date(sale_date) >= date(?) AND date(sale_date) <= date(?)
        GROUP BY fuel_type
        """,
        (month_start, month_end),
    ).fetchall()

    return {
        "as_of": today,
        "sales_count_today": int(sales_today["c"] or 0),
        "revenue_today": revenue_today,
        "litres_sold_today": float(sales_today["litres"] or 0),
        "expenses_today": exp_today,
        "profit_today": profit_today,
        "profit_today_label": "Profit" if profit_today >= 0 else "Loss",
        "fuel_purchase_cost_today": purchase_cost_today,
        "net_after_purchases_today": profit_today,
        "fuel_purchase_cost_month": purchase_cost_m,
        "net_after_purchases_month": rev_m - exp_m,
        "fuel_purchase_cost_year": purchase_cost_y,
        "net_after_purchases_year": rev_y - exp_y,
        "monthly_revenue": rev_m,
        "monthly_expenses": exp_m,
        "monthly_profit": rev_m - exp_m,
        "yearly_revenue": rev_y,
        "yearly_expenses": exp_y,
        "yearly_profit": rev_y - exp_y,
        "stock_rows": stock_rows,
        "low_fuel_rows": low_alerts,
        "low_fuel_warning": len(low_alerts) > 0,
        "top_fuel_type": str(top_fuel["fuel_type"]) if top_fuel else None,
        "top_fuel_litres": float(top_fuel["litres"] or 0) if top_fuel else 0.0,
        "monthly_revenue_series": [{"label": r["ym"], "total": float(r["total"])} for r in monthly_series],
        "daily_sales_series": [
            {"day": r["d"], "total": float(r["total"]), "count": int(r["cnt"])} for r in daily_sales_14
        ],
        "fuel_distribution": [
            {"fuel_type": r["fuel_type"], "litres": float(r["litres"])} for r in fuel_dist
        ],
    }
