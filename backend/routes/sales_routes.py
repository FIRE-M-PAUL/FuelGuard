"""Salesperson dashboard, retail sale capture, receipts, and history."""
from __future__ import annotations

from flask import flash, redirect, render_template, request, session, url_for

from backend.models import fuel_model, fuel_sale_model, station_model, user_model
from backend.routes.auth_routes import staff_bp
from backend.security.rbac import Permission, require_permissions
from backend.services import audit_service
from backend.services.logging_service import log_event
from backend.security.session_manager import staff_login_required


@staff_bp.route("/sales/dashboard")
@staff_login_required
@require_permissions(Permission.SALES_PORTAL)
def sales_dashboard():
    user = user_model.get_user_by_id(int(session["user_id"]))
    metrics = fuel_model.dashboard_metrics()
    my_records = fuel_model.list_fuel_records(submitted_by=int(session["user_id"]))
    recent_sales = fuel_sale_model.list_sales_by_salesperson(
        int(session["user_id"]), limit=10
    )
    just_sold_id = request.args.get("just_sold", type=int)
    last_sale = None
    if just_sold_id:
        row = fuel_sale_model.get_sale_by_id(just_sold_id)
        if row and int(row["salesperson_id"]) == int(session["user_id"]):
            last_sale = row
    return render_template(
        "sales/dashboard.html",
        user=user,
        role=session.get("role"),
        metrics=metrics,
        records=my_records[:10],
        recent_sales=recent_sales,
        last_sale=last_sale,
    )


@staff_bp.route("/sales/history")
@staff_login_required
@require_permissions(Permission.SALES_PORTAL)
def sales_history():
    user = user_model.get_user_by_id(int(session["user_id"]))
    recent_sales = fuel_sale_model.list_sales_by_salesperson(
        int(session["user_id"]), limit=500
    )
    return render_template(
        "sales/sales_history.html",
        user=user,
        role=session.get("role"),
        recent_sales=recent_sales,
    )


@staff_bp.route("/sales/sell", methods=["GET", "POST"])
@staff_login_required
@require_permissions(Permission.SALES_PORTAL)
def sell_fuel():
    user = user_model.get_user_by_id(int(session["user_id"]))
    stock_rows = fuel_sale_model.get_all_stock()
    retail_prices = fuel_sale_model.get_retail_prices_dict()
    if request.method == "GET":
        return render_template(
            "sales/record_sale.html",
            user=user,
            role=session.get("role"),
            stock_rows=stock_rows,
            retail_prices=retail_prices,
        )

    fuel_type = (request.form.get("fuel_type") or "").strip()
    payment_method = (request.form.get("payment_method") or "").strip()
    customer_name = (request.form.get("customer_name") or "").strip()
    vehicle_number = (request.form.get("vehicle_number") or "").strip()
    try:
        quantity = float(request.form.get("quantity") or 0)
    except ValueError:
        flash("Quantity must be a valid number.", "error")
        return render_template(
            "sales/record_sale.html",
            user=user,
            role=session.get("role"),
            stock_rows=fuel_sale_model.get_all_stock(),
            retail_prices=fuel_sale_model.get_retail_prices_dict(),
        ), 400

    list_price = fuel_sale_model.get_retail_price_per_litre(fuel_type)
    if list_price is None:
        flash(
            "Retail price is not available for this fuel. An administrator must set selling prices.",
            "error",
        )
        return render_template(
            "sales/record_sale.html",
            user=user,
            role=session.get("role"),
            stock_rows=fuel_sale_model.get_all_stock(),
            retail_prices=fuel_sale_model.get_retail_prices_dict(),
        ), 400
    price_per_litre = list_price
    total_amount = round(quantity * price_per_litre, 2)

    if not customer_name or not vehicle_number:
        flash("Customer name and vehicle number are required.", "error")
        return render_template(
            "sales/record_sale.html",
            user=user,
            role=session.get("role"),
            stock_rows=fuel_sale_model.get_all_stock(),
            retail_prices=fuel_sale_model.get_retail_prices_dict(),
        ), 400

    sale_id, err = fuel_sale_model.record_sale(
        fuel_type=fuel_type,
        quantity=quantity,
        price_per_litre=price_per_litre,
        total_amount=total_amount,
        payment_method=payment_method,
        customer_name=customer_name,
        vehicle_number=vehicle_number,
        salesperson_id=int(session["user_id"]),
    )
    if err:
        flash(err, "error")
        return render_template(
            "sales/record_sale.html",
            user=user,
            role=session.get("role"),
            stock_rows=fuel_sale_model.get_all_stock(),
            retail_prices=fuel_sale_model.get_retail_prices_dict(),
        ), 400

    log_event(
        f"Fuel sale recorded sale_id={sale_id} salesperson_id={session['user_id']} "
        f"fuel_type={fuel_type!r} quantity={quantity} list_price={price_per_litre}"
    )
    audit_service.record(
        audit_service.ACTION_FUEL_SALE,
        user_id=int(session["user_id"]),
        username=session.get("username"),
        details=f"sale_id={sale_id} fuel_type={fuel_type!r} quantity={quantity}",
    )
    flash("Sale recorded successfully.", "success")
    return redirect(url_for("staff.sales_dashboard", just_sold=sale_id))


@staff_bp.route("/sales/receipt/<int:sale_id>")
@staff_login_required
@require_permissions(Permission.SALES_PORTAL)
def sale_receipt(sale_id: int):
    sale = fuel_sale_model.get_sale_by_id(sale_id)
    if not sale:
        flash("Sale not found.", "error")
        return redirect(url_for("staff.sales_dashboard"))
    if int(sale["salesperson_id"]) != int(session["user_id"]):
        return (
            render_template(
                "shared/error.html",
                code=403,
                title="Access denied",
                message="You can only view your own receipts.",
            ),
            403,
        )
    user = user_model.get_user_by_id(int(session["user_id"]))
    return render_template(
        "sales/receipt.html",
        sale=sale,
        user=user,
        role=session.get("role"),
        station_name=station_model.station_name(),
    )
