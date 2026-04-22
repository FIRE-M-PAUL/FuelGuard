from __future__ import annotations

from backend.utils.security import clear_failed_login


def test_staff_login_lockout_after_failures(client, sales_user):
    try:
        for _ in range(5):
            resp = client.post(
                "/login",
                data={"username": "sales1", "password": "WrongPassword"},
                follow_redirects=False,
            )
            assert resp.status_code == 401

        locked = client.post(
            "/login",
            data={"username": "sales1", "password": "SalesPass123!"},
            follow_redirects=False,
        )
        assert locked.status_code == 429
    finally:
        clear_failed_login("sales1")
