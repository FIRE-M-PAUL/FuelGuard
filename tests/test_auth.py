from __future__ import annotations

from backend.models import user_model


def test_staff_login_redirects_sales(client, sales_user):
    resp = client.post(
        "/login",
        data={"username": "sales1", "password": "SalesPass123!"},
        follow_redirects=False,
    )
    assert resp.status_code == 302
    assert "/sales/dashboard" in resp.headers.get("Location", "")


def test_admin_rejected_on_staff_login(client, admin_user):
    resp = client.post(
        "/login",
        data={"username": "admin", "password": "admin#G06"},
        follow_redirects=False,
    )
    assert resp.status_code == 403


def test_admin_login_success(client, admin_user):
    resp = client.post(
        "/admin/login",
        data={"username": "admin", "password": "admin#G06"},
        follow_redirects=False,
    )
    assert resp.status_code == 302
    assert "/admin/dashboard" in resp.headers.get("Location", "")


def test_non_admin_rejected_on_admin_login(client, sales_user):
    resp = client.post(
        "/admin/login",
        data={"username": "sales1", "password": "SalesPass123!"},
        follow_redirects=False,
    )
    assert resp.status_code == 403


def test_sales_blocked_from_manager_dashboard(client, sales_user):
    client.post(
        "/login",
        data={"username": "sales1", "password": "SalesPass123!"},
        follow_redirects=True,
    )
    resp = client.get("/manager/dashboard")
    assert resp.status_code == 403


def test_role_mismatch_rejected(client, sales_user):
    resp = client.post(
        "/login/manager",
        data={"username": "sales1", "password": "SalesPass123!"},
        follow_redirects=False,
    )
    assert resp.status_code == 403


def test_admin_registration_blocked(client):
    resp = client.post(
        "/register",
        data={
            "full_name": "Admin Attempt",
            "email": "evil-admin@test.local",
            "username": "eviladmin",
            "password": "SecurePass99!",
            "confirm_password": "SecurePass99!",
            "phone": "1234567890",
            "role": "admin",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 400


def test_self_register_is_pending_until_admin_approves(client, app, admin_user):
    reg = client.post(
        "/register",
        data={
            "full_name": "New Sales",
            "email": "newsales@test.local",
            "username": "newsales",
            "password": "SecurePass99!",
            "confirm_password": "SecurePass99!",
            "phone": "1234567890",
            "role": "sales",
        },
        follow_redirects=False,
    )
    assert reg.status_code == 302
    blocked = client.post(
        "/login",
        data={"username": "newsales", "password": "SecurePass99!"},
        follow_redirects=False,
    )
    assert blocked.status_code == 403

    with app.app_context():
        row = user_model.get_user_by_username("newsales")
        assert row is not None
        assert (row["status"] or "").lower() == "pending"
        new_id = int(row["id"])

    client.post(
        "/admin/login",
        data={"username": "admin", "password": "admin#G06"},
        follow_redirects=True,
    )
    approve = client.post(
        f"/admin/users/{new_id}/toggle_status",
        data={},
        follow_redirects=False,
    )
    assert approve.status_code == 302

    ok = client.post(
        "/login",
        data={"username": "newsales", "password": "SecurePass99!"},
        follow_redirects=False,
    )
    assert ok.status_code == 302
    assert "/sales/dashboard" in ok.headers.get("Location", "")


def test_admin_creates_user(client, admin_user):
    client.post(
        "/admin/login",
        data={"username": "admin", "password": "admin#G06"},
        follow_redirects=True,
    )
    resp = client.post(
        "/admin/register_user",
        data={
            "username": "acct1",
            "email": "acct1@test.local",
            "password": "SecurePass99!",
            "role": "accountant",
            "department": "Finance",
            "status": "active",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 302
