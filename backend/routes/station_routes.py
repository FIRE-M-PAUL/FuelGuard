"""Station operations: analytics, shifts, shift CSV export, alerts, and extended expense tools."""
from __future__ import annotations

import csv
import io
from datetime import UTC, datetime
from typing import Any

from flask import Response, flash, redirect, render_template, request, session, url_for

from backend.models import accounting_model, analytics_model, fuel_sale_model, station_model, user_model
from backend.routes.auth_routes import staff_bp
from backend.security.rbac import Permission, require_permissions
from backend.services import audit_service
from backend.services.logging_service import log_event
from backend.security.session_manager import staff_login_required


@staff_bp.get("/analytics")
@staff_login_required
@require_permissions(Permission.STATION_INSIGHTS)
def station_analytics():
    user = user_model.get_user_by_id(int(session["user_id"]))
    data = analytics_model.get_analytics_bundle()
    alerts = station_model.list_recent_alerts(limit=12)
    role = (session.get("role") or "").lower()
    return render_template(
        "station/analytics.html",
        user=user,
        role=role,
        nav="analytics",
        data=data,
        alerts=alerts,
    )


@staff_bp.get("/sales/shifts")
@staff_login_required
@require_permissions(Permission.SALES_PORTAL)
def sales_shifts():
    user = user_model.get_user_by_id(int(session["user_id"]))
    uid = int(session["user_id"])
    open_shift = station_model.get_open_shift(uid)
    history = station_model.list_shifts_for_user(uid, limit=20)
    history_rows: list[dict[str, Any]] = []
    for sh in history:
        d = dict(sh)
        if (sh["status"] or "").lower() == "closed":
            d["summary"] = station_model.shift_sales_summary(int(sh["id"]))
        else:
            d["summary"] = {"litres": 0.0, "revenue": 0.0, "transactions": 0}
        history_rows.append(d)
    role = (session.get("role") or "").lower()
    return render_template(
        "sales/shifts.html",
        user=user,
        role=role,
        nav="shifts",
        open_shift=open_shift,
        history_rows=history_rows,
    )


@staff_bp.post("/sales/shifts/start")
@staff_login_required
@require_permissions(Permission.SALES_PORTAL)
def sales_shift_start():
    try:
        opening_meter = float(request.form.get("opening_meter") or 0)
        opening_cash = float(request.form.get("opening_cash") or 0)
    except ValueError:
        flash("Enter valid numbers for meter and cash.", "error")
        return redirect(url_for("staff.sales_shifts"))
    notes = (request.form.get("notes") or "").strip() or None
    sid, err = station_model.start_shift(
        user_id=int(session["user_id"]),
        opening_meter=opening_meter,
        opening_cash=opening_cash,
        notes=notes,
    )
    if err:
        flash(err, "error")
    else:
        log_event(f"Shift started shift_id={sid} user_id={session['user_id']}")
        audit_service.record(
            "shift_started",
            user_id=int(session["user_id"]),
            username=session.get("username"),
            details=f"shift_id={sid}",
        )
        flash("Shift started.", "success")
    return redirect(url_for("staff.sales_shifts"))


@staff_bp.post("/sales/shifts/<int:shift_id>/end")
@staff_login_required
@require_permissions(Permission.SALES_PORTAL)
def sales_shift_end(shift_id: int):
    try:
        closing_meter = float(request.form.get("closing_meter") or 0)
        cash_collected = float(request.form.get("cash_collected") or 0)
    except ValueError:
        flash("Enter valid numbers.", "error")
        return redirect(url_for("staff.sales_shifts"))
    notes = (request.form.get("notes") or "").strip() or None
    ok, err = station_model.end_shift(
        shift_id=shift_id,
        user_id=int(session["user_id"]),
        closing_meter=closing_meter,
        cash_collected=cash_collected,
        notes=notes,
    )
    if not ok:
        flash(err or "Could not close shift.", "error")
    else:
        log_event(f"Shift ended shift_id={shift_id} user_id={session['user_id']}")
        audit_service.record(
            "shift_ended",
            user_id=int(session["user_id"]),
            username=session.get("username"),
            details=f"shift_id={shift_id}",
        )
        flash("Shift closed.", "success")
    return redirect(url_for("staff.sales_shifts"))


@staff_bp.get("/reports/shifts/export")
@staff_login_required
@require_permissions(Permission.STATION_INSIGHTS)
def export_shifts_csv():
    today = datetime.now(UTC).date().isoformat()
    date_from = (request.args.get("from") or today).strip()
    date_to = (request.args.get("to") or today).strip()
    rows = station_model.list_shifts_between(date_from, date_to)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(
        [
            "shift_id",
            "username",
            "status",
            "started_at",
            "ended_at",
            "opening_meter",
            "closing_meter",
            "opening_cash",
            "cash_collected",
            "litres_sold",
            "shift_revenue",
            "transactions",
        ],
    )
    for r in rows:
        summary = station_model.shift_sales_summary(int(r["id"]))
        w.writerow(
            [
                r["id"],
                r["username"],
                r["status"],
                r["started_at"],
                r["ended_at"] or "",
                r["opening_meter"],
                r["closing_meter"] or "",
                r["opening_cash"],
                r["cash_collected"] or "",
                summary["litres"],
                summary["revenue"],
                summary["transactions"],
            ],
        )
    audit_service.record(
        "report_export",
        user_id=int(session["user_id"]),
        username=session.get("username"),
        details="shifts_csv",
    )
    return Response(
        buf.getvalue(),
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="shifts_{date_from}_to_{date_to}.csv"'},
    )


@staff_bp.post("/alerts/<int:alert_id>/ack")
@staff_login_required
@require_permissions(Permission.MANAGER_PORTAL, Permission.ACCOUNTANT_PORTAL)
def acknowledge_alert_route(alert_id: int):
    if station_model.acknowledge_alert(alert_id):
        flash("Alert dismissed.", "success")
    else:
        flash("Alert not found.", "error")
    nxt = request.form.get("next") or request.referrer or url_for("staff.station_analytics")
    return redirect(nxt)


@staff_bp.route("/accountant/expenses/<int:expense_id>/edit", methods=["GET", "POST"])
@staff_login_required
@require_permissions(Permission.ACCOUNTANT_PORTAL)
def accountant_expense_edit(expense_id: int):
    user = user_model.get_user_by_id(int(session["user_id"]))
    row = accounting_model.get_expense(expense_id)
    if not row:
        flash("Expense not found.", "error")
        return redirect(url_for("staff.accountant_expenses"))
    if request.method == "POST":
        name = (request.form.get("expense_name") or "").strip()
        description = (request.form.get("description") or "").strip()
        category = (request.form.get("category") or "Other").strip()
        date_str = (request.form.get("date") or "").strip()
        try:
            amount = float(request.form.get("amount") or 0)
        except ValueError:
            flash("Invalid amount.", "error")
            return redirect(url_for("staff.accountant_expense_edit", expense_id=expense_id))
        if not description or amount <= 0:
            flash("Description and positive amount are required.", "error")
            return redirect(url_for("staff.accountant_expense_edit", expense_id=expense_id))
        if category not in accounting_model.EXPENSE_CATEGORIES:
            category = "Other"
        if not date_str:
            date_str = datetime.now(UTC).strftime("%Y-%m-%d")
        accounting_model.update_expense(
            expense_id,
            expense_name=name or description,
            description=description,
            amount=amount,
            category=category,
            date_str=date_str,
        )
        log_event(f"Expense updated id={expense_id} by={session['user_id']}")
        audit_service.record(
            "expense_updated",
            user_id=int(session["user_id"]),
            username=session.get("username"),
            details=f"expense_id={expense_id}",
        )
        flash("Expense updated.", "success")
        return redirect(url_for("staff.accountant_expenses"))
    return render_template(
        "accountant/expense_edit.html",
        user=user,
        role=session.get("role"),
        nav="expenses",
        expense=row,
        categories=sorted(accounting_model.EXPENSE_CATEGORIES),
    )


@staff_bp.post("/accountant/expenses/<int:expense_id>/delete")
@staff_login_required
@require_permissions(Permission.ACCOUNTANT_PORTAL)
def accountant_expense_delete(expense_id: int):
    if accounting_model.delete_expense(expense_id):
        log_event(f"Expense deleted id={expense_id} by={session['user_id']}")
        audit_service.record(
            "expense_deleted",
            user_id=int(session["user_id"]),
            username=session.get("username"),
            details=f"expense_id={expense_id}",
        )
        flash("Expense deleted.", "success")
    else:
        flash("Expense not found.", "error")
    return redirect(url_for("staff.accountant_expenses"))
