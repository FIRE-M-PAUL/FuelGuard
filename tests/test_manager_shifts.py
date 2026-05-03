from __future__ import annotations


def test_manager_shifts_page_ok(client, manager_user):
    client.post(
        "/login",
        data={"username": "manager1", "password": "ManagerPass123!"},
        follow_redirects=True,
    )
    resp = client.get("/manager/shifts")
    assert resp.status_code == 200
    assert b"Staff shift management" in resp.data


def test_sales_cannot_open_manager_shifts(client, sales_user):
    client.post("/login", data={"username": "sales1", "password": "SalesPass123!"}, follow_redirects=True)
    assert client.get("/manager/shifts").status_code == 403
