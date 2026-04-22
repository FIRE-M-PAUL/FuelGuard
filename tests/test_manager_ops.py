from __future__ import annotations


def test_manager_dashboard_ok(client, manager_user):
    client.post(
        "/login",
        data={"username": "manager1", "password": "ManagerPass123!"},
        follow_redirects=True,
    )
    resp = client.get("/manager/dashboard")
    assert resp.status_code == 200
    assert b"Operational command" in resp.data


def test_manager_cannot_access_accountant_routes(client, manager_user):
    client.post(
        "/login",
        data={"username": "manager1", "password": "ManagerPass123!"},
        follow_redirects=True,
    )
    assert client.get("/accountant/dashboard").status_code == 403


def test_manager_approvals_page_ok(client, manager_user):
    client.post(
        "/login",
        data={"username": "manager1", "password": "ManagerPass123!"},
        follow_redirects=True,
    )
    resp = client.get("/manager/approvals")
    assert resp.status_code == 200
    assert b"Approval requests" in resp.data


def test_manager_web_approve_updates_fuel_record(client, sales_user, manager_user):
    client.post("/login", data={"username": "sales1", "password": "SalesPass123!"})
    create_resp = client.post(
        "/api/fuel/records",
        json={
            "vehicle_id": "WEB-1",
            "driver_name": "Approver Test",
            "fuel_amount": 10.0,
            "fuel_type": "Diesel",
            "record_date": "2026-04-21",
            "location": "Station B",
            "odometer_reading": 1.0,
            "cost": 20.0,
            "station_name": "Main",
        },
    )
    assert create_resp.status_code == 201
    client.post("/logout")

    client.post("/login", data={"username": "manager1", "password": "ManagerPass123!"}, follow_redirects=True)
    apr = client.post("/manager/approve/1", follow_redirects=False)
    assert apr.status_code == 302

    client.post("/login", data={"username": "sales1", "password": "SalesPass123!"}, follow_redirects=True)
    lst = client.get("/api/fuel/records").get_json()
    assert lst["ok"] is True
    rec = next(r for r in lst["records"] if r["vehicle_id"] == "WEB-1")
    assert rec["status"] == "approved"
