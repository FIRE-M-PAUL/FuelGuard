from __future__ import annotations

from datetime import UTC, datetime, timedelta

from backend.models.user_model import get_db


def test_fuel_levels_page_access_by_role(client, manager_user, sales_user, accountant_user):
    client.post("/login", data={"username": "manager1", "password": "ManagerPass123!"})
    resp = client.get("/fuel-levels")
    assert resp.status_code == 200
    assert b"Fuel Tank Level Monitoring Dashboard" in resp.data
    client.post("/logout")

    client.post("/login", data={"username": "sales1", "password": "SalesPass123!"})
    sales_resp = client.get("/fuel-levels")
    assert sales_resp.status_code == 200
    assert b"Fuel Tank Level Monitoring Dashboard" in sales_resp.data
    client.post("/logout")

    client.post("/login", data={"username": "acct1", "password": "AccountantPass123!"})
    acct_resp = client.get("/fuel-levels")
    assert acct_resp.status_code == 200


def test_fuel_levels_api_returns_status_and_days_estimate(client, app, manager_user, sales_user):
    with app.app_context():
        db = get_db()
        db.execute(
            "UPDATE fuel_stock SET tank_capacity = 10000, minimum_threshold = 1200 WHERE fuel_type = 'Petrol'"
        )
        db.execute(
            "UPDATE fuel_stock SET available_litres = 6000 WHERE fuel_type = 'Petrol'"
        )
        db.execute(
            "UPDATE fuel_stock SET tank_capacity = 10000, minimum_threshold = 1200 WHERE fuel_type = 'Diesel'"
        )
        db.execute(
            "UPDATE fuel_stock SET available_litres = 2000 WHERE fuel_type = 'Diesel'"
        )
        user = db.execute(
            "SELECT id FROM users WHERE username = ?",
            ("sales1",),
        ).fetchone()
        assert user is not None

        now = datetime.now(UTC)
        for offset in range(7):
            day = (now - timedelta(days=offset)).strftime("%Y-%m-%d 10:00:00")
            db.execute(
                """
                INSERT INTO fuel_sales (
                    fuel_type, quantity, price_per_litre, total_amount, payment_method,
                    customer_name, vehicle_number, salesperson_id, sale_date
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "Petrol",
                    100.0,
                    2.5,
                    250.0,
                    "Cash",
                    "Test Customer",
                    f"CAR-{offset}",
                    int(user["id"]),
                    day,
                ),
            )
        db.commit()

    client.post("/login", data={"username": "manager1", "password": "ManagerPass123!"})
    resp = client.get("/api/fuel-levels")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["ok"] is True
    by_type = {item["fuel_type"]: item for item in body["levels"]}
    assert by_type["Petrol"]["status_color"] == "green"
    assert by_type["Diesel"]["status_color"] == "red"
    assert by_type["Petrol"]["estimated_days_remaining"] == 60.0


def test_fuel_level_adjustment_requires_admin_approval(client, app, manager_user, admin_user):
    with app.app_context():
        db = get_db()
        db.execute(
            "UPDATE fuel_stock SET available_litres = 500, tank_capacity = 10000, minimum_threshold = 1200 WHERE fuel_type = 'Diesel'"
        )
        db.commit()

    client.post("/login", data={"username": "manager1", "password": "ManagerPass123!"})
    sub = client.post(
        "/manager/fuel-adjustment-requests/new",
        data={
            "fuel_type": "Diesel",
            "requested_new_level": "3000",
            "reason": "Manual correction after confirmed tanker delivery variance",
        },
        follow_redirects=True,
    )
    assert sub.status_code == 200
    assert b"Adjustment request submitted" in sub.data

    with app.app_context():
        db = get_db()
        stock_mid = db.execute(
            "SELECT available_litres FROM fuel_stock WHERE fuel_type = 'Diesel'"
        ).fetchone()
        assert float(stock_mid["available_litres"]) == 500.0
        rid = int(
            db.execute("SELECT id FROM fuel_adjustment_requests ORDER BY id DESC LIMIT 1").fetchone()["id"]
        )

    client.post("/logout")
    client.post(
        "/admin/login",
        data={"username": "admin", "password": "admin#G06"},
        follow_redirects=True,
    )
    ap = client.post(
        f"/admin/fuel-adjustment-requests/{rid}/approve",
        data={"admin_comments": "Verified against dipstick reading and delivery docs."},
        follow_redirects=True,
    )
    assert ap.status_code == 200
    assert b"Request approved" in ap.data

    with app.app_context():
        db = get_db()
        stock = db.execute(
            "SELECT available_litres FROM fuel_stock WHERE fuel_type = 'Diesel'"
        ).fetchone()
        assert float(stock["available_litres"]) == 3000.0
        adj = db.execute(
            """
            SELECT fuel_type, previous_level, new_level, reason
            FROM fuel_adjustments
            ORDER BY id DESC LIMIT 1
            """
        ).fetchone()
        assert adj is not None
        assert adj["fuel_type"] == "Diesel"
        assert float(adj["previous_level"]) == 500.0
        assert float(adj["new_level"]) == 3000.0


def test_direct_fuel_level_adjust_route_removed(client, sales_user):
    client.post("/login", data={"username": "sales1", "password": "SalesPass123!"})
    resp = client.post(
        "/fuel-levels/adjust",
        data={"fuel_type": "Petrol", "new_level": "7000", "reason": "Not allowed"},
        follow_redirects=False,
    )
    assert resp.status_code in (404, 405)
