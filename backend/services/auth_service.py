"""Authentication helpers (password operations)."""
from __future__ import annotations

from backend.security.password_hashing import hash_password, verify_password

__all__ = ["hash_password", "verify_password"]
