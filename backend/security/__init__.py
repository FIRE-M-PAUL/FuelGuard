"""Security building blocks: hashing, sessions, RBAC, CSRF, audit."""
from __future__ import annotations

from backend.security.password_hashing import hash_password, verify_password
from backend.security.rbac import Permission, require_permissions
from backend.security.session_manager import (
    admin_login_required,
    clear_failed_login,
    clear_session,
    is_login_locked,
    refresh_session_activity,
    register_failed_login,
    role_required,
    session_idle_expired,
    staff_login_required,
)

__all__ = [
    "Permission",
    "admin_login_required",
    "clear_failed_login",
    "clear_session",
    "hash_password",
    "is_login_locked",
    "refresh_session_activity",
    "register_failed_login",
    "require_permissions",
    "role_required",
    "session_idle_expired",
    "staff_login_required",
    "verify_password",
]
