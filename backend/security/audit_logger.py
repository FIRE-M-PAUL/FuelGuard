"""
Structured audit trail helpers (SQLite `audit_logs` + optional file log).
"""
from __future__ import annotations

from backend.services import audit_service

__all__ = ["audit_service"]
