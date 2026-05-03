"""Fuel level adjustment requests: manager submits, admin approves (stock changes only after approval)."""
from __future__ import annotations

from datetime import UTC, datetime

from flask import flash, redirect, render_template, request, session, url_for

from backend.models import fuel_adjustment_request_model, fuel_sale_model, user_model
from backend.models.fuel_adjustment_request_model import STATUS_PENDING_VERIFICATION
from backend.routes.auth_routes import staff_bp
from backend.routes.user_routes import admin_bp
from backend.security.rbac import Permission, require_permissions
from backend.security.session_manager import admin_login_required, role_required, staff_login_required
from backend.services import audit_service
from backend.services.logging_service import log_event


def _adjustment_alert(*, alert_type: str, message: str, meta: dict | None = None) -> None:
    try:
        from backend.models import station_model

        station_model.create_alert(alert_type=alert_type, message=message, severity="info", meta=meta)
    except Exception:
        pass


@staff_bp.route("/manager/fuel-adjustment-requests/new", methods=["GET", "POST"])
@staff_login_required
@require_permissions(Permission.MANAGER_PORTAL)
def manager_fuel_adjustment_request_new():
    user = user_model.get_user_by_id(int(session["user_id"]))
    snapshot = fuel_sale_model.fuel_levels_monitoring_snapshot()
    if request.method == "POST":
        fuel_type = (request.form.get("fuel_type") or "").strip()
        reason = (request.form.get("reason") or "").strip()
        try:
            requested_new_level = float(request.form.get("requested_new_level") or 0)
        except ValueError:
            flash("Enter a valid number for the requested level.", "error")
            return redirect(url_for("staff.manager_fuel_adjustment_request_new"))

        rid, err = fuel_adjustment_request_model.create_request(
            fuel_type=fuel_type,
            requested_new_level=requested_new_level,
            reason=reason,
            requested_by=int(session["user_id"]),
        )
        if err:
            flash(err, "error")
            return redirect(url_for("staff.manager_fuel_adjustment_request_new"))

        log_event(f"Fuel adjustment request created id={rid} manager_id={session['user_id']}")
        audit_service.record(
            "fuel_adjustment_request_created",
            user_id=int(session["user_id"]),
            username=session.get("username"),
            details=f"request_id={rid} fuel_type={fuel_type!r}",
        )
        _adjustment_alert(
            alert_type="fuel_adjustment_pending",
            message=f"Fuel level adjustment request #{rid} ({fuel_type}) awaits admin approval.",
            meta={"request_id": rid},
        )
        flash("Adjustment request submitted for admin approval. Stock is unchanged until approved.", "success")
        return redirect(url_for("staff.fuel_levels_dashboard"))

    today = datetime.now(UTC).strftime("%Y-%m-%d")
    return render_template(
        "manager/fuel_adjustment_request_new.html",
        user=user,
        role=session.get("role"),
        nav="fuel-adjustment",
        levels=snapshot,
        today=today,
    )


@admin_bp.route("/fuel-adjustment-requests", methods=["GET"])
@admin_login_required
@role_required("admin")
def admin_fuel_adjustment_requests():
    users = user_model.list_users()
    rows = fuel_adjustment_request_model.list_pending_for_admin()
    return render_template(
        "admin/fuel_adjustment_requests.html",
        users=users,
        username=session.get("username"),
        role=session.get("role"),
        requests=rows,
    )


@admin_bp.route("/fuel-adjustment-requests/<int:request_id>", methods=["GET"])
@admin_login_required
@role_required("admin")
def admin_fuel_adjustment_request_detail(request_id: int):
    users = user_model.list_users()
    row = fuel_adjustment_request_model.get_request(request_id)
    if not row:
        flash("Request not found.", "error")
        return redirect(url_for("admin.admin_fuel_adjustment_requests"))
    if (row["status"] or "").upper() != STATUS_PENDING_VERIFICATION:
        flash("This request is no longer pending.", "error")
        return redirect(url_for("admin.admin_fuel_adjustment_requests"))
    return render_template(
        "admin/fuel_adjustment_request_detail.html",
        users=users,
        username=session.get("username"),
        role=session.get("role"),
        req=row,
    )


@admin_bp.post("/fuel-adjustment-requests/<int:request_id>/approve")
@admin_login_required
@role_required("admin")
def admin_fuel_adjustment_request_approve(request_id: int):
    comments = (request.form.get("admin_comments") or "").strip()
    ok, err, adj_id = fuel_adjustment_request_model.approve_request(
        request_id=request_id,
        admin_id=int(session["user_id"]),
        admin_comments=comments,
    )
    if not ok:
        flash(err or "Could not approve request.", "error")
        return redirect(url_for("admin.admin_fuel_adjustment_request_detail", request_id=request_id))

    log_event(
        f"Fuel adjustment request approved request_id={request_id} admin_id={session['user_id']} "
        f"adjustment_id={adj_id}"
    )
    audit_service.record(
        "fuel_adjustment_request_approved",
        user_id=int(session["user_id"]),
        username=session.get("username"),
        details=f"request_id={request_id} adjustment_id={adj_id}",
    )
    row = fuel_adjustment_request_model.get_request(request_id)
    mgr = row["requested_by_username"] if row else "manager"
    _adjustment_alert(
        alert_type="fuel_adjustment_decision",
        message=f"Fuel adjustment request #{request_id} APPROVED. Applied to stock. Manager: {mgr}.",
        meta={"request_id": request_id},
    )
    flash("Request approved and fuel level updated.", "success")
    return redirect(url_for("admin.admin_fuel_adjustment_requests"))


@admin_bp.post("/fuel-adjustment-requests/<int:request_id>/reject")
@admin_login_required
@role_required("admin")
def admin_fuel_adjustment_request_reject(request_id: int):
    comments = (request.form.get("admin_comments") or "").strip()
    ok, err = fuel_adjustment_request_model.reject_request(
        request_id=request_id,
        admin_id=int(session["user_id"]),
        admin_comments=comments,
    )
    if not ok:
        flash(err or "Could not reject request.", "error")
        return redirect(url_for("admin.admin_fuel_adjustment_request_detail", request_id=request_id))

    log_event(f"Fuel adjustment request rejected request_id={request_id} admin_id={session['user_id']}")
    audit_service.record(
        "fuel_adjustment_request_rejected",
        user_id=int(session["user_id"]),
        username=session.get("username"),
        details=f"request_id={request_id}",
    )
    row = fuel_adjustment_request_model.get_request(request_id)
    mgr = row["requested_by_username"] if row else "manager"
    _adjustment_alert(
        alert_type="fuel_adjustment_decision",
        message=f"Fuel adjustment request #{request_id} REJECTED. Stock unchanged. Manager: {mgr}.",
        meta={"request_id": request_id},
    )
    flash("Request rejected.", "success")
    return redirect(url_for("admin.admin_fuel_adjustment_requests"))
