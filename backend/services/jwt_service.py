"""
JWT access tokens (OWASP A07 — Identification and Authentication Failures).

Issues short-lived signed tokens (HS256) after credential verification.
Tokens carry user id and role claims; the secret MUST live in environment variables
in production (see config.JWT_SECRET_KEY / JWT_SECRET).
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from flask import Flask
from jwt.exceptions import ExpiredSignatureError, InvalidTokenError

JWT_ALGORITHM = "HS256"
# Spec: 1 hour access token lifetime
ACCESS_TOKEN_TTL = timedelta(hours=1)


def create_access_token(
    app: Flask,
    *,
    user_id: int,
    username: str,
    role: str,
) -> str:
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "username": username,
        "role": role.lower(),
        "iat": now,
        "exp": now + ACCESS_TOKEN_TTL,
    }
    secret = app.config.get("JWT_SECRET_KEY")
    if not secret:
        raise RuntimeError("JWT_SECRET_KEY is not configured.")
    return jwt.encode(payload, secret, algorithm=JWT_ALGORITHM)


def decode_access_token(app: Flask, token: str) -> dict[str, Any]:
    secret = app.config.get("JWT_SECRET_KEY")
    if not secret:
        raise RuntimeError("JWT_SECRET_KEY is not configured.")
    return jwt.decode(token, secret, algorithms=[JWT_ALGORITHM])


def decode_access_token_safe(app: Flask, token: str) -> tuple[dict[str, Any] | None, str | None]:
    try:
        return decode_access_token(app, token), None
    except ExpiredSignatureError:
        return None, "token_expired"
    except InvalidTokenError:
        return None, "invalid_token"
