"""
Session lifecycle, idle timeout, login lockout, and role decorators (OWASP A07).
"""
from __future__ import annotations

import time
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

IDLE_SECONDS = 10 * 60
MAX_FAILED_ATTEMPTS = 5
LOCKOUT_SECONDS = 15 * 60
_FAILED_LOGIN_STATE: dict[str, dict[str, float | int]] = {}


def _now() -> float:
    return time.time()


def refresh_session_activity() -> None:
    session["last_activity"] = _now()
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
        if session.get("user_id") and session_idle_expired():
            clear_session()
            flash("Session expired. Please log in again.")
            return redirect(url_for("staff.login"))

        if not session.get("user_id"):
            flash("Please sign in to continue.")
            return redirect(url_for("staff.login", next=request.url))

        row = user_model.get_user_by_id(int(session["user_id"]))
        if not row:
            clear_session()
            flash("Please sign in to continue.")
            return redirect(url_for("staff.login", next=request.url))
        st = (row["status"] or "").lower()
        if st != "active":
            clear_session()
            if st == "pending":
                flash(
                    "Your account is still pending administrator approval. "
                    "You can sign in after an admin activates your account."
                )
            else:
                flash("Your account is disabled.")
            return redirect(url_for("staff.login", next=request.url))

        refresh_session_activity()
        return view(*args, **kwargs)

    return wrapped


def admin_login_required(view: Callable) -> Callable:
    @wraps(view)
    def wrapped(*args, **kwargs):
        if session.get("user_id") and session_idle_expired():
            clear_session()
            flash("Session expired. Please log in again.")
            return redirect(url_for("admin.login"))

        if not session.get("user_id"):
            flash("Please sign in to continue.")
            return redirect(url_for("admin.login", next=request.url))

        if (session.get("role") or "").lower() != "admin":
            log_event(
                f"Unauthorized admin area access attempt "
                f"user_id={session.get('user_id')} role={session.get('role')} path={request.path}",
                level="warning",
            )
            flash("Access denied. Admin privileges required.")
            return redirect(url_for("admin.login"))

        refresh_session_activity()
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
