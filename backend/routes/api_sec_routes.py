"""
JWT-authenticated JSON API (OWASP A07 — Identification and Authentication Failures).

* ``POST /api/auth/login`` — credential check, returns JWT (CSRF-exempt: machine clients).
* ``GET /api/sales`` — example protected resource; requires ``Bearer`` token.

Browser HTML forms continue to use cookie sessions + CSRF (Flask-WTF); this blueprint
serves programmatic clients and demos stateless authentication.
"""
from __future__ import annotations

from flask import Blueprint, current_app, jsonify, request

from backend.extensions import csrf
from backend.middleware.jwt_middleware import jwt_roles_required
from backend.models import fuel_sale_model, user_model
from backend.services import audit_service
from backend.services.auth_service import verify_password
from backend.services.jwt_service import ACCESS_TOKEN_TTL, create_access_token
from backend.utils.security import clear_failed_login, is_login_locked, register_failed_login

api_sec_bp = Blueprint("api_sec", __name__, url_prefix="/api")


@api_sec_bp.post("/auth/login")
@csrf.exempt
def api_jwt_login():
    """
    Exchange username/password for a short-lived JWT.
    CSRF-exempt: JSON APIs authenticate via credentials in the body, not browser cookies.
    """
    payload = request.get_json(silent=True) or {}
    username = (payload.get("username") or "").strip()
    password = payload.get("password") or ""
    if not username or not password:
        return jsonify({"ok": False, "error": "missing_credentials"}), 400
    key = username.lower()
    if is_login_locked(key):
        return jsonify({"ok": False, "error": "locked"}), 429

    user = user_model.get_user_by_username(username) or user_model.get_user_by_email(username)
    if not user or not verify_password(password, user["password_hash"]):
        register_failed_login(key)
        return jsonify({"ok": False, "error": "invalid_credentials"}), 401
    clear_failed_login(key)

    role = (user["role"] or "").lower()
    if role == "admin":
        return jsonify({"ok": False, "error": "admin_use_admin_portal"}), 403
    if (user["status"] or "").lower() != "active":
        return jsonify({"ok": False, "error": "account_inactive"}), 403
    if role not in {"sales", "manager", "accountant"}:
        return jsonify({"ok": False, "error": "forbidden"}), 403

    token = create_access_token(
        current_app,
        user_id=int(user["id"]),
        username=user["username"],
        role=role,
    )
    audit_service.record(
        audit_service.ACTION_LOGIN_SUCCESS,
        user_id=int(user["id"]),
        username=user["username"],
        details="jwt POST /api/auth/login",
    )
    expires_in = int(ACCESS_TOKEN_TTL.total_seconds())
    return jsonify(
        {
            "ok": True,
            "access_token": token,
            "token_type": "Bearer",
            "expires_in": expires_in,
            "role": role,
            "user_id": int(user["id"]),
        }
    )


@api_sec_bp.get("/sales")
@jwt_roles_required("sales", "manager", "accountant")
def api_list_sales():
    """Example secure route: list recent retail sales (JWT only)."""
    rows = fuel_sale_model.list_recent_retail_sales(limit=50)

    def row_to_dict(r):
        return {
            "id": r["id"],
            "fuel_type": r["fuel_type"],
            "quantity": r["quantity"],
            "total_amount": r["total_amount"],
            "sale_date": r["sale_date"],
            "payment_method": r["payment_method"],
            "salesperson_username": r["salesperson_username"],
        }

    return jsonify({"ok": True, "sales": [row_to_dict(r) for r in rows]})
