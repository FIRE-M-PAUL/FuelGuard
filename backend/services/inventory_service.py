"""Inventory / fuel-record use-cases."""
from __future__ import annotations

from backend.models import fuel_model


def dashboard_metrics():
    return fuel_model.dashboard_metrics()
