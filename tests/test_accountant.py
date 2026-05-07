from __future__ import annotations

import pytest

from backend.models import accounting_model, analytics_model, user_model
from backend.utils.timezone import today_cat_iso


def test_normalize_fuel_purchase_calendar_date():
    d, err = accounting_model.normalize_fuel_purchase_calendar_date("2026-05-04T22:30")
    assert err is None
    assert d == "2026-05-04"


def test_total_expenses_includes_fuel_purchases(app, accountant_user):
    with app.app_context():
        row = user_model.get_user_by_username("acct1")
        assert row is not None
        uid = int(row["id"])
        day = today_cat_iso()
        accounting_model.add_expense(
            expense_name="Supplies",
            description="Paper",
            amount=50.0,
            category="Other",
            date_str=day,
            recorded_by=uid,
        )
        _, err = accounting_model.record_fuel_purchase(
            supplier_name="Shell",
            fuel_type="Petrol",
            quantity=100.0,
            price_per_litre=2.0,
            total_cost=200.0,
            purchase_date=day,
            recorded_by=uid,
        )
        assert err is None
        assert accounting_model.total_expenses_between(day, day) == pytest.approx(250.0)

        bundle = analytics_model.get_analytics_bundle()
        assert bundle["expenses_today"] == pytest.approx(250.0)
        assert bundle["net_after_purchases_today"] == pytest.approx(bundle["profit_today"])


def test_accountant_login_redirect(client, accountant_user):
    resp = client.post(
        "/login",
        data={"username": "acct1", "password": "AccountantPass123!"},
        follow_redirects=False,
    )
    assert resp.status_code == 302
    assert "/accountant/dashboard" in resp.headers.get("Location", "")


def test_sales_blocked_from_accountant_dashboard(client, sales_user):
    client.post(
        "/login",
        data={"username": "sales1", "password": "SalesPass123!"},
        follow_redirects=True,
    )
    assert client.get("/accountant/dashboard").status_code == 403


def test_accountant_cannot_access_sell_fuel(client, accountant_user):
    client.post(
        "/login",
        data={"username": "acct1", "password": "AccountantPass123!"},
        follow_redirects=True,
    )
    assert client.get("/sales/sell").status_code == 403


def test_accountant_dashboard_ok(client, accountant_user):
    client.post(
        "/login",
        data={"username": "acct1", "password": "AccountantPass123!"},
        follow_redirects=True,
    )
    resp = client.get("/accountant/dashboard")
    assert resp.status_code == 200
    assert b"Financial Control Center" in resp.data


def test_accountant_records_expense(client, accountant_user):
    client.post(
        "/login",
        data={"username": "acct1", "password": "AccountantPass123!"},
        follow_redirects=True,
    )
    resp = client.post(
        "/accountant/expenses",
        data={
            "description": "Station signage",
            "amount": "120.50",
            "category": "Other",
            "date": "2026-04-21",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 302
    loc = resp.headers.get("Location", "")
    assert "/accountant/expenses" in loc
    list_resp = client.get("/accountant/expenses")
    assert list_resp.status_code == 200
    assert b"Station signage" in list_resp.data


def test_accountant_reports_export_csv(client, accountant_user):
    client.post(
        "/login",
        data={"username": "acct1", "password": "AccountantPass123!"},
        follow_redirects=True,
    )
    resp = client.get("/accountant/reports/export?kind=daily_sales&date=2026-04-21")
    assert resp.status_code == 200
    assert "csv" in (resp.mimetype or "")
    assert b"fuel_type" in resp.data
