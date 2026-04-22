"""Sales use-cases (delegates to :mod:`backend.models.fuel_sale_model`)."""
from __future__ import annotations

from backend.models import fuel_sale_model


def get_stock_and_prices():
    return fuel_sale_model.get_all_stock(), fuel_sale_model.get_retail_prices_dict()
