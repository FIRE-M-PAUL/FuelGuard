"""Centralized timezone helpers for Zambia (CAT, UTC+2)."""
from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

CAT_ZONE = ZoneInfo("Africa/Lusaka")


def now_cat() -> datetime:
    return datetime.now(CAT_ZONE)


def now_cat_str() -> str:
    return now_cat().strftime("%Y-%m-%d %H:%M:%S")


def today_cat_iso() -> str:
    return now_cat().date().isoformat()


def date_days_ago_cat_iso(days: int) -> str:
    return (now_cat().date() - timedelta(days=days)).isoformat()
