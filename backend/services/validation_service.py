"""
Input validation and lightweight sanitization (OWASP A03 — Injection).

* Rejects malformed identifiers and out-of-range numbers (reduces SQL injection when
  paired with parameterized queries — see models).
* Strips control characters and obvious script probes from free-text fields to
  mitigate stored XSS when data is echoed in templates or JSON APIs.
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from backend.models.user_model import ALLOWED_ROLES, ALLOWED_STATUS, REGISTRABLE_ROLES

EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
USERNAME_RE = re.compile(r"^[a-zA-Z0-9._-]{3,32}$")
PWD_UPPER = re.compile(r"[A-Z]")
PWD_DIGIT = re.compile(r"[0-9]")
PWD_SPECIAL = re.compile(r"[^A-Za-z0-9]")


def validate_username(username: str) -> tuple[bool, str]:
    u = (username or "").strip()
    if not u:
        return False, "Username is required."
    if not USERNAME_RE.match(u):
        return False, "Username must be 3–32 characters (letters, digits, . _ -)."
    return True, ""


def validate_email(email: str) -> tuple[bool, str]:
    e = (email or "").strip()
    if not e:
        return False, "Email is required."
    if not EMAIL_RE.match(e):
        return False, "Invalid email format."
    return True, ""


def validate_password(password: str, *, min_length: int = 8) -> tuple[bool, str]:
    """
    Password policy: length, uppercase, digit, special character.
    Aligns with OWASP guidance to increase entropy and resist guessing attacks.
    """
    p = password or ""
    if len(p) < min_length:
        return False, f"Password must be at least {min_length} characters."
    if not PWD_UPPER.search(p):
        return False, "Password must contain at least one uppercase letter."
    if not PWD_DIGIT.search(p):
        return False, "Password must contain at least one number."
    if not PWD_SPECIAL.search(p):
        return False, "Password must contain at least one special character."
    return True, ""


def sanitize_untrusted_text(value: Any, *, max_len: int = 500) -> str:
    """
    Normalize user-supplied text: trim, drop NULs, strip angle brackets (blocks HTML),
    and cap length. Pair with parameterized SQL and Jinja auto-escape for XSS/SQLi defense.
    """
    if value is None:
        return ""
    s = str(value).strip().replace("\x00", "")
    s = re.sub(r"[<>]", "", s)
    if "javascript:" in s.lower():
        s = re.sub(r"(?i)javascript:", "", s)
    return s[:max_len]


def validate_role(role: str) -> tuple[bool, str]:
    r = (role or "").strip().lower()
    if r not in ALLOWED_ROLES:
        return False, "Invalid role."
    return True, ""


def validate_registrable_role(role: str) -> tuple[bool, str]:
    r = (role or "").strip().lower()
    if r not in REGISTRABLE_ROLES:
        return False, "Invalid registration role."
    return True, ""


def validate_status(status: str) -> tuple[bool, str]:
    s = (status or "").strip().lower()
    if s not in ALLOWED_STATUS:
        return False, "Invalid status."
    return True, ""


def sanitize_optional_str(value: Any, *, max_len: int = 120) -> str:
    if value is None:
        return ""
    s = str(value).strip()
    return s[:max_len]


def validate_positive_number(value: Any, *, field: str, allow_zero: bool = True) -> tuple[bool, str]:
    try:
        num = float(value)
    except (TypeError, ValueError):
        return False, f"{field} must be numeric."
    if allow_zero and num < 0:
        return False, f"{field} cannot be negative."
    if not allow_zero and num <= 0:
        return False, f"{field} must be greater than zero."
    return True, ""


def validate_date(value: str, *, field: str = "Date") -> tuple[bool, str]:
    text = (value or "").strip()
    if not text:
        return False, f"{field} is required."
    try:
        datetime.strptime(text, "%Y-%m-%d")
    except ValueError:
        return False, f"{field} must use YYYY-MM-DD format."
    return True, ""


def validate_required_text(value: str, *, field: str, max_len: int = 120) -> tuple[bool, str]:
    text = (value or "").strip()
    if not text:
        return False, f"{field} is required."
    if len(text) > max_len:
        return False, f"{field} must be at most {max_len} characters."
    return True, ""


def validate_fuel_payload(payload: dict[str, Any]) -> tuple[bool, list[str], dict[str, Any]]:
    cleaned = {
        "vehicle_id": sanitize_untrusted_text(payload.get("vehicle_id"), max_len=60),
        "driver_name": sanitize_untrusted_text(payload.get("driver_name"), max_len=120),
        "fuel_amount": payload.get("fuel_amount"),
        "fuel_type": sanitize_untrusted_text(payload.get("fuel_type"), max_len=50),
        "record_date": sanitize_optional_str(payload.get("record_date"), max_len=20),
        "location": sanitize_untrusted_text(payload.get("location"), max_len=120),
        "odometer_reading": payload.get("odometer_reading"),
        "cost": payload.get("cost"),
        "station_name": sanitize_untrusted_text(payload.get("station_name"), max_len=120),
    }
    errors: list[str] = []
    checks = [
        validate_required_text(cleaned["vehicle_id"], field="Vehicle ID"),
        validate_required_text(cleaned["driver_name"], field="Driver name"),
        validate_required_text(cleaned["fuel_type"], field="Fuel type"),
        validate_required_text(cleaned["location"], field="Location"),
        validate_required_text(cleaned["station_name"], field="Station name"),
        validate_positive_number(cleaned["fuel_amount"], field="Fuel amount"),
        validate_positive_number(cleaned["odometer_reading"], field="Odometer reading"),
        validate_positive_number(cleaned["cost"], field="Cost"),
        validate_date(cleaned["record_date"], field="Date"),
    ]
    for ok, msg in checks:
        if not ok:
            errors.append(msg)
    if not errors:
        cleaned["fuel_amount"] = float(cleaned["fuel_amount"])
        cleaned["odometer_reading"] = float(cleaned["odometer_reading"])
        cleaned["cost"] = float(cleaned["cost"])
    return len(errors) == 0, errors, cleaned
