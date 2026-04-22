"""Small shared helpers for routes and services."""
from __future__ import annotations


def parse_bool_flag(raw: str | None, *, true_value: str = "1") -> bool | None:
    if raw is None:
        return None
    s = raw.strip()
    if s == true_value:
        return True
    if s == "0":
        return False
    return None
