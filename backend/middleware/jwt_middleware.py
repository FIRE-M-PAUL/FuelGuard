"""
JWT bearer authentication for JSON API routes (OWASP A07).

Validates ``Authorization: Bearer <token>`` using HS256 and the configured
``JWT_SECRET_KEY``. Tokens are issued by ``POST /api/auth/login`` and expire
after one hour (see ``jwt_service.ACCESS_TOKEN_TTL``).
"""
from __future__ import annotations

from functools import wraps
from typing import Any, Callable

from flask import current_app, jsonify, request

from backend.services.jwt_service import decode_access_token_safe


def jwt_roles_required(*allowed_roles: str) -> Callable:
    """Require a valid JWT whose ``role`` claim is one of ``allowed_roles``."""

    allowed = {r.lower() for r in allowed_roles}

    def decorator(view: Callable) -> Callable:
        @wraps(view)
        def wrapped(*args: Any, **kwargs: Any):
            auth = request.headers.get("Authorization") or ""
            if not auth.startswith("Bearer "):
                return jsonify({"ok": False, "error": "unauthorized"}), 401
            token = auth[7:].strip()
            payload, err = decode_access_token_safe(current_app, token)
            if err:
                return jsonify({"ok": False, "error": err}), 401
            role = (payload.get("role") or "").lower()
            if role not in allowed:
                return jsonify({"ok": False, "error": "forbidden"}), 403
            request.jwt_payload = payload  # type: ignore[attr-defined]
            return view(*args, **kwargs)

        return wrapped

    return decorator
