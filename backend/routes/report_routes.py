"""Manager and accountant dashboards, monitoring, and CSV exports."""
from __future__ import annotations

import csv
import io
from datetime import UTC, datetime

from flask import Response, flash, redirect, render_template, request, session, url_for

from backend.models import (
    accounting_model,
    fuel_adjustment_request_model,
    fuel_sale_model,
    manager_ops_model,
    station_model,
    user_model,
)
from backend.routes.auth_routes import staff_bp
from backend.security.rbac import Permission, require_permissions
from backend.services import audit_service
from backend.services.logging_service import log_event
from backend.security.session_manager import role_required, staff_login_required


@staff_bp.route("/manager/dashboard")
@staff_login_required
@require_permissions(Permission.MANAGER_PORTAL)
def manager_dashboard():
    user = user_model.get_user_by_id(int(session["user_id"]))
    ops = manager_ops_model.get_manager_dashboard_bundle()
    return render_template(
        "manager/dashboard.html",
        user=user,
        role=session.get("role"),
        ops=ops,
        nav="dashboard",
    )


@staff_bp.get("/fuel-levels")
@staff_login_required
@role_required("manager", "sales", "accountant", "admin")
def fuel_levels_dashboard():
    user = user_model.get_user_by_id(int(session["user_id"]))
    role = (session.get("role") or "").lower()
    levels = fuel_sale_model.fuel_levels_monitoring_snapshot()
    has_critical = any(item["critical_alert"] for item in levels)
    can_request_adjustment = role == "manager"
    my_adjustment_requests: list = []
    if can_request_adjustment:
        my_adjustment_requests = fuel_adjustment_request_model.list_for_manager(
            int(session["user_id"]), limit=15
        )
    return render_template(
        "shared/fuel_levels.html",
        user=user,
        role=role,
        nav="fuel-levels",
        levels=levels,
        has_critical=has_critical,
        can_configure_thresholds=role == "admin",
        can_request_adjustment=can_request_adjustment,
        recent_adjustments=fuel_sale_model.list_recent_fuel_adjustments(limit=12),
        my_adjustment_requests=my_adjustment_requests,
    )


@staff_bp.get("/api/fuel-levels")
@staff_login_required
@role_required("manager", "sales", "accountant", "admin")
def fuel_levels_api():
    levels = fuel_sale_model.fuel_levels_monitoring_snapshot()
    return {
        "ok": True,
        "levels": levels,
        "has_critical": any(item["critical_alert"] for item in levels),
    }


@staff_bp.route("/manager/sales", methods=["GET"])
@staff_login_required
@require_permissions(Permission.MANAGER_PORTAL)
def manager_sales():
    user = user_model.get_user_by_id(int(session["user_id"]))
    q = (request.args.get("q") or "").strip() or None
    pm = (request.args.get("payment_method") or "").strip() or None
    ft = (request.args.get("fuel_type") or "").strip() or None
    sort = (request.args.get("sort") or "date_desc").strip()
    sales = fuel_sale_model.list_all_sales_for_accounting(
        search=q,
        payment_method=pm,
        fuel_type=ft,
        verified_only=None,
        unverified_only=None,
        sort=sort
        if sort in {"date_desc", "date_asc", "amount_desc", "amount_asc", "id_desc"}
        else "date_desc",
    )
    return render_template(
        "manager/sales.html",
        user=user,
        role=session.get("role"),
        sales=sales,
        nav="sales",
        filters={
            "q": q or "",
            "payment_method": pm or "",
            "fuel_type": ft or "",
            "sort": sort,
        },
    )


@staff_bp.route("/manager/shifts", methods=["GET"])
@staff_login_required
@require_permissions(Permission.MANAGER_PORTAL)
def manager_shifts():
    """Overview of all staff shifts: start details, status, and sales summary while open/closed."""
    user = user_model.get_user_by_id(int(session["user_id"]))
    rows = station_model.list_recent_shifts_with_staff(limit=120)
    shift_rows: list[dict] = []
    for sh in rows:
        d = dict(sh)
        d["summary"] = station_model.shift_sales_summary(int(sh["id"]))
        shift_rows.append(d)
    open_count = sum(1 for r in shift_rows if (r.get("status") or "").lower() == "open")
    return render_template(
        "manager/shifts.html",
        user=user,
        role=session.get("role"),
        nav="shifts",
        shifts=shift_rows,
        open_shift_count=open_count,
    )


@staff_bp.route("/manager/reports", methods=["GET"])
@staff_login_required
@require_permissions(Permission.MANAGER_PORTAL)
def manager_reports():
    user = user_model.get_user_by_id(int(session["user_id"]))
    today = datetime.now(UTC).date().isoformat()
    return render_template(
        "manager/reports.html",
        user=user,
        role=session.get("role"),
        nav="reports-classic",
        today=today,
    )


@staff_bp.get("/manager/reports/export")
@staff_login_required
@require_permissions(Permission.MANAGER_PORTAL)
def manager_reports_export():
    kind = (request.args.get("kind") or "daily_sales").strip()
    today = datetime.now(UTC).date().isoformat()

    if kind == "daily_sales":
        day = (request.args.get("date") or today).strip()
        rows = accounting_model.export_daily_sales_rows(day)
        filename = f"manager_daily_sales_{day}.csv"
    elif kind == "fuel_usage":
        date_from = (request.args.get("from") or today).strip()
        date_to = (request.args.get("to") or today).strip()
        rows = manager_ops_model.export_fuel_usage_rows(date_from, date_to)
        filename = f"fuel_usage_{date_from}_to_{date_to}.csv"
    elif kind == "stock":
        rows = manager_ops_model.export_stock_report_rows()
        filename = "fuel_stock_report.csv"
    elif kind == "operational":
        rows = manager_ops_model.export_operational_summary_rows()
        filename = f"operational_summary_{today}.csv"
    else:
        return redirect(url_for("staff.manager_reports"))

    buf = io.StringIO()
    w = csv.writer(buf)
    for row in rows:
        w.writerow(row)
    log_event(f"Manager report export kind={kind!r} user_id={session.get('user_id')}")
    return Response(
        buf.getvalue(),
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@staff_bp.route("/accountant/dashboard")
@staff_login_required
@require_permissions(Permission.ACCOUNTANT_PORTAL)
def accountant_dashboard():
    user = user_model.get_user_by_id(int(session["user_id"]))
    finance = accounting_model.get_finance_snapshot()
    return render_template(
        "accountant/dashboard.html",
        user=user,
        role=session.get("role"),
        finance=finance,
        nav="dashboard",
    )


@staff_bp.route("/accountant/payments", methods=["GET"])
@staff_login_required
@require_permissions(Permission.ACCOUNTANT_PORTAL)
def accountant_payments():
    user = user_model.get_user_by_id(int(session["user_id"]))
    q = (request.args.get("q") or "").strip() or None
    pm = (request.args.get("payment_method") or "").strip() or None
    ft = (request.args.get("fuel_type") or "").strip() or None
    sort = (request.args.get("sort") or "date_desc").strip()
    vf = request.args.get("verified")
    verified_only = vf == "1"
    unverified_only = vf == "0"
    sales = fuel_sale_model.list_all_sales_for_accounting(
        search=q,
        payment_method=pm,
        fuel_type=ft,
        verified_only=verified_only if vf in {"0", "1"} else None,
        unverified_only=unverified_only if vf in {"0", "1"} else None,
        sort=sort if sort in {"date_desc", "date_asc", "amount_desc", "amount_asc", "id_desc"} else "date_desc",
    )
    return render_template(
        "accountant/transactions.html",
        user=user,
        role=session.get("role"),
        sales=sales,
        nav="payments",
        filters={
            "q": q or "",
            "payment_method": pm or "",
            "fuel_type": ft or "",
            "sort": sort,
            "verified": vf or "",
        },
    )


@staff_bp.post("/accountant/payments/<int:sale_id>/verify")
@staff_login_required
@require_permissions(Permission.ACCOUNTANT_PORTAL)
def accountant_verify_payment(sale_id: int):
    ok = fuel_sale_model.set_payment_verified(
        sale_id, verified_by=int(session["user_id"]), verified=True
    )
    if ok:
        log_event(
            f"Payment verified sale_id={sale_id} accountant_id={session['user_id']}"
        )
        flash("Payment marked as verified.", "success")
    else:
        flash("Sale not found.", "error")
    return redirect(url_for("staff.accountant_payments"))


@staff_bp.route("/accountant/expenses", methods=["GET", "POST"])
@staff_login_required
@require_permissions(Permission.ACCOUNTANT_PORTAL)
def accountant_expenses():
    user = user_model.get_user_by_id(int(session["user_id"]))
    if request.method == "POST":
        expense_name = (request.form.get("expense_name") or "").strip()
        description = (request.form.get("description") or "").strip()
        category = (request.form.get("category") or "Other").strip()
        date_str = (request.form.get("date") or "").strip()
        try:
            amount = float(request.form.get("amount") or 0)
        except ValueError:
            flash("Invalid amount.", "error")
            return redirect(url_for("staff.accountant_expenses_add"))
        if not description:
            flash("Description is required.", "error")
            return redirect(url_for("staff.accountant_expenses_add"))
        if amount <= 0:
            flash("Amount must be positive.", "error")
            return redirect(url_for("staff.accountant_expenses_add"))
        if category not in accounting_model.EXPENSE_CATEGORIES:
            category = "Other"
        if not date_str:
            date_str = datetime.now(UTC).strftime("%Y-%m-%d")
        eid = accounting_model.add_expense(
            expense_name=expense_name or None,
            description=description,
            amount=amount,
            category=category,
            date_str=date_str,
            recorded_by=int(session["user_id"]),
        )
        log_event(f"Expense recorded id={eid} accountant_id={session['user_id']}")
        flash("Expense recorded.", "success")
        return redirect(url_for("staff.accountant_expenses"))
    df = (request.args.get("from") or "").strip() or None
    dt = (request.args.get("to") or "").strip() or None
    cat = (request.args.get("category") or "").strip() or None
    if cat and cat not in accounting_model.EXPENSE_CATEGORIES:
        cat = None
    expenses = accounting_model.list_expenses_filtered(
        date_from=df, date_to=dt, category=cat, limit=500
    )
    total_filtered = accounting_model.total_expenses_filtered(
        date_from=df, date_to=dt, category=cat
    )
    return render_template(
        "accountant/expenses.html",
        user=user,
        role=session.get("role"),
        expenses=expenses,
        nav="expenses",
        filter_from=df or "",
        filter_to=dt or "",
        filter_category=cat or "",
        total_filtered=total_filtered,
        categories=sorted(accounting_model.EXPENSE_CATEGORIES),
    )


@staff_bp.route("/accountant/expenses/add", methods=["GET"])
@staff_login_required
@require_permissions(Permission.ACCOUNTANT_PORTAL)
def accountant_expenses_add():
    user = user_model.get_user_by_id(int(session["user_id"]))
    return render_template(
        "accountant/add_expense.html",
        user=user,
        role=session.get("role"),
        categories=sorted(accounting_model.EXPENSE_CATEGORIES),
        nav="expenses",
    )


@staff_bp.route("/accountant/purchases", methods=["GET", "POST"])
@staff_login_required
@require_permissions(Permission.ACCOUNTANT_PORTAL)
def accountant_purchases():
    user = user_model.get_user_by_id(int(session["user_id"]))
    if request.method == "POST":
        supplier = (request.form.get("supplier_name") or "").strip()
        fuel_type = (request.form.get("fuel_type") or "").strip()
        purchase_date = (request.form.get("purchase_date") or "").strip()
        try:
            quantity = float(request.form.get("quantity") or 0)
            price_per_litre = float(request.form.get("price_per_litre") or 0)
            total_cost = float(request.form.get("total_cost") or 0)
        except ValueError:
            flash("Invalid numeric values.", "error")
            return redirect(url_for("staff.accountant_purchases_add"))
        if not supplier or not purchase_date:
            flash("Supplier and purchase date are required.", "error")
            return redirect(url_for("staff.accountant_purchases_add"))
        pid, err = accounting_model.record_fuel_purchase(
            supplier_name=supplier,
            fuel_type=fuel_type,
            quantity=quantity,
            price_per_litre=price_per_litre,
            total_cost=total_cost,
            purchase_date=purchase_date,
            recorded_by=int(session["user_id"]),
        )
        if err:
            flash(err, "error")
            return redirect(url_for("staff.accountant_purchases_add"))
        log_event(f"Fuel purchase recorded id={pid} accountant_id={session['user_id']}")
        audit_service.record(
            audit_service.ACTION_FUEL_STOCK_UPDATED,
            user_id=int(session["user_id"]),
            username=session.get("username"),
            details=f"purchase_id={pid} fuel_type={fuel_type!r} quantity_litres={quantity}",
        )
        flash("Fuel purchase recorded and stock updated.", "success")
        return redirect(url_for("staff.accountant_purchases"))
    purchases = accounting_model.list_fuel_purchases()
    return render_template(
        "accountant/purchases.html",
        user=user,
        role=session.get("role"),
        purchases=purchases,
        nav="purchases",
    )


@staff_bp.route("/accountant/purchases/add", methods=["GET"])
@staff_login_required
@require_permissions(Permission.ACCOUNTANT_PORTAL)
def accountant_purchases_add():
    user = user_model.get_user_by_id(int(session["user_id"]))
    return render_template(
        "accountant/add_fuel_purchase.html",
        user=user,
        role=session.get("role"),
        nav="purchases",
    )


@staff_bp.route("/accountant/reports", methods=["GET"])
@staff_login_required
@require_permissions(Permission.ACCOUNTANT_PORTAL)
def accountant_reports():
    user = user_model.get_user_by_id(int(session["user_id"]))
    today = datetime.now(UTC).date().isoformat()
    return render_template(
        "accountant/financial_reports.html",
        user=user,
        role=session.get("role"),
        nav="reports-classic",
        today=today,
    )


@staff_bp.get("/accountant/reports/export")
@staff_login_required
@require_permissions(Permission.ACCOUNTANT_PORTAL)
def accountant_reports_export():
    kind = (request.args.get("kind") or "daily_sales").strip()
    today = datetime.now(UTC).date().isoformat()

    if kind == "daily_sales":
        day = (request.args.get("date") or today).strip()
        rows = accounting_model.export_daily_sales_rows(day)
        filename = f"daily_sales_{day}.csv"
    elif kind == "monthly_revenue":
        ym = (request.args.get("ym") or today[:7]).strip()
        try:
            y, m = int(ym[:4]), int(ym[5:7])
        except (ValueError, IndexError):
            y, m = datetime.now(UTC).year, datetime.now(UTC).month
        rows = accounting_model.export_monthly_revenue_rows(y, m)
        filename = f"monthly_revenue_{y:04d}_{m:02d}.csv"
    elif kind == "expenses":
        date_from = (request.args.get("from") or today).strip()
        date_to = (request.args.get("to") or today).strip()
        rows = accounting_model.export_expenses_rows(date_from, date_to)
        filename = f"expenses_{date_from}_to_{date_to}.csv"
    elif kind == "pnl":
        date_from = (request.args.get("from") or today).strip()
        date_to = (request.args.get("to") or today).strip()
        rows = accounting_model.export_pnl_summary_rows(date_from, date_to)
        filename = f"profit_loss_{date_from}_to_{date_to}.csv"
    else:
        return redirect(url_for("staff.accountant_reports"))

    buf = io.StringIO()
    w = csv.writer(buf)
    for row in rows:
        w.writerow(row)
    log_event(f"Accountant export kind={kind!r} user_id={session.get('user_id')}")
    return Response(
        buf.getvalue(),
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
