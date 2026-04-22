"""
Security feature tests (OWASP-aligned behaviors implemented in FuelGuard).
"""
from __future__ import annotations

import json

from werkzeug.security import generate_password_hash

from backend.app import create_app
from backend.models import audit_log_model, user_model
from backend.services import audit_service, auth_service, validation_service
from backend.services.auth_service import hash_password
from backend.services.jwt_service import create_access_token, decode_access_token
from config import TestConfig


def test_password_complexity_enforced():
    ok, _msg = validation_service.validate_password("short")
    assert not ok
    ok, msg = validation_service.validate_password("nouppercase1!")
    assert not ok and "uppercase" in msg.lower()
    ok, msg = validation_service.validate_password("NoDigitHere!!")
    assert not ok and "number" in msg.lower()
    ok, msg = validation_service.validate_password("NoSpecial123")
    assert not ok and "special" in msg.lower()
    ok, _msg = validation_service.validate_password("ValidPass1!")
    assert ok


def test_bcrypt_hash_and_verify_roundtrip():
    h = auth_service.hash_password("SamplePass9$")
    assert "$2" in h
    assert auth_service.verify_password("SamplePass9$", h)
    assert not auth_service.verify_password("WrongPass9$", h)


def test_legacy_pbkdf2_hash_still_verifies():
    legacy = generate_password_hash("LegacyPass1!", method="pbkdf2:sha256", salt_length=16)
    assert auth_service.verify_password("LegacyPass1!", legacy)


def test_sanitize_untrusted_text_strips_angle_brackets():
    raw = "<script>x</script>AB"
    out = validation_service.sanitize_untrusted_text(raw, max_len=50)
    assert "<" not in out and ">" not in out


def test_jwt_create_and_decode(app, sales_user):
    with app.app_context():
        tok = create_access_token(
            app,
            user_id=1,
            username="sales1",
            role="sales",
        )
        payload = decode_access_token(app, tok)
        assert payload["sub"] == "1"
        assert payload["role"] == "sales"


def test_jwt_api_login_and_protected_sales(client, sales_user):
    lo = client.post(
        "/api/auth/login",
        data=json.dumps({"username": "sales1", "password": "SalesPass123!"}),
        content_type="application/json",
    )
    assert lo.status_code == 200
    body = lo.get_json()
    assert body.get("ok") and body.get("access_token")
    tok = body["access_token"]
    assert client.get("/api/sales").status_code == 401
    ok = client.get("/api/sales", headers={"Authorization": f"Bearer {tok}"})
    assert ok.status_code == 200
    data = ok.get_json()
    assert data.get("ok") and isinstance(data.get("sales"), list)


def test_rbac_manager_blocked_from_sales_portal(client, manager_user):
    client.post(
        "/login",
        data={"username": "manager1", "password": "ManagerPass123!"},
        follow_redirects=True,
    )
    resp = client.get("/sales/dashboard")
    assert resp.status_code == 403
    assert b"Access Denied" in resp.data


def test_audit_log_persists_admin_login(client, app, admin_user):
    client.post(
        "/admin/login",
        data={"username": "admin", "password": "admin#G06"},
        follow_redirects=True,
    )
    with app.app_context():
        rows = audit_log_model.list_recent(limit=80)
        assert any(r["action"] == audit_service.ACTION_LOGIN_SUCCESS for r in rows)


def test_session_idle_is_at_least_ten_minutes(app):
    assert app.config["SESSION_IDLE_SECONDS"] == 10 * 60
    assert app.config["SESSION_COOKIE_MAX_AGE_MINUTES"] >= app.config["SESSION_IDLE_MINUTES"]


def test_csrf_rejects_admin_login_without_token(tmp_path):
    class StrictCSRF(TestConfig):
        WTF_CSRF_ENABLED = True
        DATABASE_PATH = str(tmp_path / "csrf.sqlite")

    application = create_app(StrictCSRF)
    with application.app_context():
        user_model.create_user(
            "Admin User",
            "admin",
            "admin@test.local",
            hash_password("admin#G06"),
            "admin",
            None,
            None,
            "active",
        )
    with application.test_client() as c:
        resp = c.post("/admin/login", data={"username": "admin", "password": "admin#G06"})
        assert resp.status_code == 400
        assert b"csrf" in resp.data.lower()
