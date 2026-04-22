from __future__ import annotations


def _fuel_payload() -> dict[str, object]:
    return {
        "vehicle_id": "VG-102",
        "driver_name": "John Doe",
        "fuel_amount": 45.5,
        "fuel_type": "Diesel",
        "record_date": "2026-04-21",
        "location": "Station A",
        "odometer_reading": 120450,
        "cost": 98.6,
        "station_name": "Fuel Depot",
    }


def test_sales_can_submit_fuel_record(client, sales_user):
    client.post("/login", data={"username": "sales1", "password": "SalesPass123!"})
    resp = client.post("/api/fuel/records", json=_fuel_payload())
    assert resp.status_code == 201
    body = resp.get_json()
    assert body["ok"] is True
    assert body["status"] == "pending"


def test_manager_can_approve_pending_record(client, sales_user, manager_user):
    client.post("/login", data={"username": "sales1", "password": "SalesPass123!"})
    create_resp = client.post("/api/fuel/records", json=_fuel_payload())
    record_id = create_resp.get_json()["record_id"]
    client.post("/logout")

    client.post("/login", data={"username": "manager1", "password": "ManagerPass123!"})
    review_resp = client.post(
        f"/api/fuel/records/{record_id}/review",
        json={"status": "approved", "note": "Looks valid"},
    )
    assert review_resp.status_code == 200
    assert review_resp.get_json()["status"] == "approved"


def test_sales_cannot_review_records(client, sales_user):
    client.post("/login", data={"username": "sales1", "password": "SalesPass123!"})
    create_resp = client.post("/api/fuel/records", json=_fuel_payload())
    record_id = create_resp.get_json()["record_id"]
    review_resp = client.post(
        f"/api/fuel/records/{record_id}/review",
        json={"status": "rejected"},
    )
    assert review_resp.status_code == 403


def test_report_export_csv_for_manager(client, sales_user, manager_user):
    client.post("/login", data={"username": "sales1", "password": "SalesPass123!"})
    client.post("/api/fuel/records", json=_fuel_payload())
    client.post("/logout")
    client.post("/login", data={"username": "manager1", "password": "ManagerPass123!"})
    resp = client.get("/api/fuel/reports/export")
    assert resp.status_code == 200
    assert "text/csv" in resp.content_type
