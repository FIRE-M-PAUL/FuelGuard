"""
Audit logging facade — writes structured rows to `audit_logs`.

Call `record()` from routes/services for any security-sensitive action so investigators
have user id, username, action label, optional details, client IP, and server timestamp.
"""
from __future__ import annotations

from flask import has_request_context, request

from backend.models import audit_log_model


# Normalized action names (stable for reporting)
ACTION_LOGIN_SUCCESS = "user_login"
ACTION_LOGOUT = "user_logout"
ACTION_LOGIN_FAILED = "failed_login"
ACTION_FUEL_SALE = "fuel_sale_recorded"
ACTION_USER_CREATED = "user_created"
ACTION_USER_DELETED = "user_deleted"
ACTION_FUEL_STOCK_UPDATED = "fuel_stock_updated"


def _client_ip() -> str | None:
    if not has_request_context():
        return None
    xff = request.headers.get("X-Forwarded-For")
    if xff:
        return xff.split(",")[0].strip()[:45]
    return (request.remote_addr or "")[:45] or None


def record(
    action: str,
    *,
    user_id: int | None = None,
    username: str | None = None,
    details: str | None = None,
) -> None:
    try:
        audit_log_model.insert_entry(
            action=action,
            user_id=user_id,
            username=username,
            details=details,
            ip_address=_client_ip(),
        )
    except Exception:
        pass
