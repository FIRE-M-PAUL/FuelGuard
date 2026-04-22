"""Compatibility shim; use :mod:`backend.security.rbac` for new code."""
from __future__ import annotations

from backend.security.rbac import Permission, require_permissions  # noqa: F401
