"""
Role-Based Access Control for staff portals (OWASP A01).
"""
from __future__ import annotations

from enum import Enum
from functools import wraps
from typing import Callable

from flask import render_template, session


class Permission(str, Enum):
    SALES_PORTAL = "sales_portal"
    MANAGER_PORTAL = "manager_portal"
    ACCOUNTANT_PORTAL = "accountant_portal"
    STATION_INSIGHTS = "station_insights"


PERMISSION_TO_ROLES: dict[Permission, frozenset[str]] = {
    Permission.SALES_PORTAL: frozenset({"sales"}),
    Permission.MANAGER_PORTAL: frozenset({"manager"}),
    Permission.ACCOUNTANT_PORTAL: frozenset({"accountant"}),
    Permission.STATION_INSIGHTS: frozenset({"manager", "accountant"}),
}


def require_permissions(*permissions: Permission) -> Callable:
    def decorator(view: Callable) -> Callable:
        @wraps(view)
        def wrapped(*args, **kwargs):
            role = (session.get("role") or "").lower()
            allowed_roles: set[str] = set()
            for p in permissions:
                allowed_roles |= PERMISSION_TO_ROLES.get(p, frozenset())
            if role not in allowed_roles:
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
