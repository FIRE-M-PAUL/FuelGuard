"""Reporting and export helpers (delegates to accounting / ops models)."""
from __future__ import annotations

from backend.models import accounting_model, manager_ops_model


def daily_sales_rows(day: str):
    return accounting_model.export_daily_sales_rows(day)


def stock_report_rows():
    return manager_ops_model.export_stock_report_rows()
