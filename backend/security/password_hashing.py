"""
Password hashing and verification (OWASP A02 — Cryptographic Failures).

New passwords use **bcrypt**; legacy ``pbkdf2:`` / ``scrypt:`` hashes remain verifiable.
"""
from __future__ import annotations

import bcrypt
from werkzeug.security import check_password_hash


def hash_password(plain: str) -> str:
    """Hash a password for storage using bcrypt (cost factor 12)."""
    digest = bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt(rounds=12))
    return digest.decode("ascii")


def verify_password(plain: str, password_hash: str) -> bool:
    """Verify plaintext against stored bcrypt or legacy Werkzeug hash."""
    if not plain or not password_hash:
        return False
    try:
        h = password_hash.strip()
        if h.startswith("pbkdf2:") or h.startswith("scrypt:"):
            return check_password_hash(h, plain)
        return bcrypt.checkpw(plain.encode("utf-8"), h.encode("ascii"))
    except (ValueError, TypeError):
        return False
