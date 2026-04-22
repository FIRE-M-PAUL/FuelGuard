"""
Compatibility shim for imports of ``backend.utils.security``.

Prefer :mod:`backend.security.session_manager` or :mod:`backend.security` for new code.
"""
from __future__ import annotations

from backend.security.session_manager import (  # noqa: F401
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
