from __future__ import annotations


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
            "category": "Operations",
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
