from __future__ import annotations

from backend.models import fuel_sale_model


def _sell_form(**overrides):
    data = {
        "fuel_type": "Petrol",
        "quantity": "10.5",
        "price_per_litre": "2.50",
        "total_amount": "26.25",
        "payment_method": "Cash",
        "customer_name": "Jane Customer",
        "vehicle_number": "AB-123-GP",
    }
    data.update(overrides)
    return data


def test_salesperson_can_complete_sale(client, sales_user):
    client.post("/login", data={"username": "sales1", "password": "SalesPass123!"})
    resp = client.post("/sales/sell", data=_sell_form(), follow_redirects=False)
    assert resp.status_code == 302
    loc = resp.headers.get("Location", "")
    assert "just_sold=" in loc


def test_manager_cannot_access_sell_fuel(client, manager_user):
    client.post("/login", data={"username": "manager1", "password": "ManagerPass123!"})
    resp = client.get("/sales/sell", follow_redirects=False)
    assert resp.status_code == 403


def test_sale_rejects_insufficient_stock(client, sales_user):
    client.post("/login", data={"username": "sales1", "password": "SalesPass123!"})
    resp = client.post(
        "/sales/sell",
        data=_sell_form(quantity="999999", total_amount=str(999999 * 2.5)),
        follow_redirects=False,
    )
    assert resp.status_code == 400


def test_sale_uses_admin_list_price_not_form(client, sales_user, app):
    with app.app_context():
        fuel_sale_model.set_retail_price_per_litre("Petrol", 9.99)
    client.post("/login", data={"username": "sales1", "password": "SalesPass123!"})
    resp = client.post(
        "/sales/sell",
        data=_sell_form(
            price_per_litre="0.01",
            total_amount="0.11",
        ),
        follow_redirects=False,
    )
    assert resp.status_code == 302
    with app.app_context():
        row = fuel_sale_model.get_sale_by_id(1)
        assert row is not None
        assert float(row["price_per_litre"]) == 9.99
        assert float(row["total_amount"]) == round(10.5 * 9.99, 2)


def test_sales_staff_redirected_from_admin_retail_prices(client, sales_user):
    client.post("/login", data={"username": "sales1", "password": "SalesPass123!"}, follow_redirects=True)
    resp = client.get("/admin/retail_prices", follow_redirects=False)
    assert resp.status_code == 302


def test_admin_can_set_retail_prices_and_sale_uses_them(client, admin_user, sales_user, app):
    client.post(
        "/admin/login",
        data={"username": "admin", "password": "admin#G06"},
        follow_redirects=True,
    )
    upd = client.post(
        "/admin/retail_prices",
        data={"petrol_price": "4", "diesel_price": "3.1"},
    )
    assert upd.status_code == 302
    client.post("/logout")
    client.post("/login", data={"username": "sales1", "password": "SalesPass123!"}, follow_redirects=True)
    resp = client.post(
        "/sales/sell",
        data={
            "fuel_type": "Petrol",
            "quantity": "2",
            "price_per_litre": "1",
            "total_amount": "2",
            "payment_method": "Cash",
            "customer_name": "List Price Check",
            "vehicle_number": "LP-99",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 302
    with app.app_context():
        row = fuel_sale_model.get_sale_by_id(1)
        assert row is not None
        assert float(row["price_per_litre"]) == 4.0
        assert float(row["total_amount"]) == 8.0