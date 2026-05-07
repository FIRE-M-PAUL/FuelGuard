"""
Session lifecycle, idle timeout, login lockout, and role decorators (OWASP A07).
"""
from __future__ import annotations

import time
import secrets
from functools import wraps
from typing import Callable

from flask import (
    current_app,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from backend.models import user_model
from backend.services.logging_service import log_event
from backend.utils.timezone import now_cat_str

IDLE_SECONDS = 10 * 60
MAX_FAILED_ATTEMPTS = 5
LOCKOUT_SECONDS = 15 * 60
_FAILED_LOGIN_STATE: dict[str, dict[str, float | int]] = {}


def _now() -> float:
    return time.time()


def refresh_session_activity() -> None:
    session["last_activity"] = _now()
    session["last_activity_cat"] = now_cat_str()
    session.modified = True


def session_idle_expired() -> bool:
    last = session.get("last_activity")
    if last is None:
        return False
    try:
        limit = float(current_app.config.get("SESSION_IDLE_SECONDS", IDLE_SECONDS))
        return (_now() - float(last)) >= limit
    except (TypeError, ValueError):
        return True


def clear_session() -> None:
    session.clear()


def establish_user_session(*, user_id: int, username: str, role: str) -> None:
    """Create a fresh authenticated session payload after successful login."""
    session.clear()
    session.permanent = True
    session["user_id"] = int(user_id)
    session["username"] = username
    session["role"] = role
    # Rotate signed session payload to reduce fixation/replay risk.
    session["session_nonce"] = secrets.token_urlsafe(24)
    session["session_started_at"] = _now()
    refresh_session_activity()


def clear_session_cookie(response):
    cookie_name = current_app.config.get("SESSION_COOKIE_NAME", "session")
    response.delete_cookie(
        cookie_name,
        path=current_app.config.get("SESSION_COOKIE_PATH", "/") or "/",
        domain=current_app.config.get("SESSION_COOKIE_DOMAIN"),
        secure=bool(current_app.config.get("SESSION_COOKIE_SECURE", False)),
        httponly=bool(current_app.config.get("SESSION_COOKIE_HTTPONLY", True)),
        samesite=current_app.config.get("SESSION_COOKIE_SAMESITE", "Lax"),
    )
    return response


def _load_active_session_user():
    uid = session.get("user_id")
    if not uid:
        return None
    try:
        row = user_model.get_user_by_id(int(uid))
    except (TypeError, ValueError):
        return None
    if not row:
        return None
    st = (row["status"] or "").lower()
    if st != "active":
        return None
    return row


def enforce_session_for_request(*, admin_area: bool):
    """Global guard for direct URL access to protected pages."""
    if session.get("user_id") and session_idle_expired():
        clear_session()
        flash("Session expired. Please log in again.", "error")
        endpoint = "admin.login" if admin_area else "staff.login"
        return redirect(url_for(endpoint))

    row = _load_active_session_user()
    if not row:
        if session.get("user_id"):
            clear_session()
        flash("Please sign in to continue.", "error")
        endpoint = "admin.login" if admin_area else "staff.login"
        return redirect(url_for(endpoint, next=request.url))

    role = (session.get("role") or "").lower()
    if admin_area and role != "admin":
        clear_session()
        flash("Access denied. Admin privileges required.", "error")
        return redirect(url_for("admin.login"))

    refresh_session_activity()
    return None


def is_login_locked(identity: str) -> bool:
    key = (identity or "").strip().lower()
    if not key:
        return False
    state = _FAILED_LOGIN_STATE.get(key)
    if not state:
        return False
    locked_until = float(state.get("locked_until", 0))
    if locked_until <= 0:
        return False
    if locked_until <= _now():
        _FAILED_LOGIN_STATE.pop(key, None)
        return False
    return True


def register_failed_login(identity: str) -> None:
    key = (identity or "").strip().lower()
    if not key:
        return
    now = _now()
    state = _FAILED_LOGIN_STATE.get(key, {"count": 0, "locked_until": 0.0})
    count = int(state.get("count", 0)) + 1
    locked_until = float(state.get("locked_until", 0))
    if count >= MAX_FAILED_ATTEMPTS:
        locked_until = now + LOCKOUT_SECONDS
        count = 0
    _FAILED_LOGIN_STATE[key] = {"count": count, "locked_until": locked_until}


def clear_failed_login(identity: str) -> None:
    key = (identity or "").strip().lower()
    if key:
        _FAILED_LOGIN_STATE.pop(key, None)


def staff_login_required(view: Callable) -> Callable:
    @wraps(view)
    def wrapped(*args, **kwargs):
        guard = enforce_session_for_request(admin_area=False)
        if guard is not None:
            return guard
        return view(*args, **kwargs)

    return wrapped


def admin_login_required(view: Callable) -> Callable:
    @wraps(view)
    def wrapped(*args, **kwargs):
        guard = enforce_session_for_request(admin_area=True)
        if guard is not None:
            return guard
        return view(*args, **kwargs)

    return wrapped


def role_required(*roles: str) -> Callable:
    allowed = {r.lower() for r in roles}

    def decorator(view: Callable) -> Callable:
        @wraps(view)
        def wrapped(*args, **kwargs):
            role = (session.get("role") or "").lower()
            if role not in allowed:
                log_event(
                    f"Forbidden: role={role!r} required={sorted(allowed)} "
                    f"user_id={session.get('user_id')} path={request.path}",
                    level="warning",
                )
                return (
                    render_template(
                        "shared/error.html",
                        code=403,
                        title="Access Denied",
                        message="Access Denied",
                    ),
                    403,
                )
            return view(*args, **kwargs)

        return wrapped

    return decorator
