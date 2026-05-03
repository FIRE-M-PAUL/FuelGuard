"""Fuel inventory API, stock views, and manager stock UI."""
from __future__ import annotations

import csv
import io

from flask import Blueprint, Response, flash, jsonify, redirect, render_template, request, session, url_for

from backend.models import fuel_model, fuel_sale_model, user_model
from backend.routes.auth_routes import staff_bp
from backend.security.rbac import Permission, require_permissions
from backend.services.logging_service import log_event
from backend.services.validation_service import validate_fuel_payload
from backend.security.session_manager import role_required, staff_login_required

fuel_bp = Blueprint("fuel", __name__, url_prefix="/api/fuel")


@fuel_bp.post("/records")
@staff_login_required
@role_required("sales", "manager", "accountant", "admin")
def create_record():
    payload = request.get_json(silent=True) or request.form.to_dict()
    ok, errors, cleaned = validate_fuel_payload(payload)
    if not ok:
        return jsonify({"ok": False, "errors": errors}), 400
    user_id = int(session["user_id"])
    record_id = fuel_model.create_fuel_record(cleaned, user_id)
    log_event(f"Fuel record created record_id={record_id} submitted_by={user_id}")
    return jsonify({"ok": True, "record_id": record_id, "status": "pending"}), 201


@fuel_bp.get("/records")
@staff_login_required
@role_required("sales", "manager", "accountant", "admin")
def list_records():
    role = (session.get("role") or "").lower()
    status = (request.args.get("status") or "").strip().lower() or None
    submitted_by = None
    if role == "sales":
        submitted_by = int(session["user_id"])
    records = fuel_model.list_fuel_records(status=status, submitted_by=submitted_by)
    return jsonify({"ok": True, "records": [dict(row) for row in records]})


@fuel_bp.post("/records/<int:record_id>/review")
@staff_login_required
@role_required("manager")
def review_record(record_id: int):
    payload = request.get_json(silent=True) or request.form.to_dict()
    status = (payload.get("status") or "").strip().lower()
    note = (payload.get("note") or "").strip() or None
    if status not in {"approved", "rejected"}:
        return jsonify({"ok": False, "error": "status must be approved or rejected"}), 400
    row = fuel_model.get_fuel_record(record_id)
    if not row:
        return jsonify({"ok": False, "error": "record not found"}), 404
    if (row["status"] or "").lower() != "pending":
        return jsonify({"ok": False, "error": "only pending records can be reviewed"}), 409
    fuel_model.update_fuel_status(
        record_id,
        status=status,
        reviewed_by=int(session["user_id"]),
        review_note=note,
    )
    log_event(
        f"Fuel record reviewed record_id={record_id} status={status} "
        f"reviewed_by={session.get('user_id')}"
    )
    return jsonify({"ok": True, "record_id": record_id, "status": status})


@fuel_bp.get("/dashboard")
@staff_login_required
@role_required("sales", "manager", "accountant", "admin")
def dashboard_data():
    return jsonify({"ok": True, "metrics": fuel_model.dashboard_metrics()})


@fuel_bp.get("/reports/export")
@staff_login_required
@role_required("manager", "accountant", "admin")
def export_report():
    records = fuel_model.list_fuel_records()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "id",
            "vehicle_id",
            "driver_name",
            "fuel_amount",
            "fuel_type",
            "record_date",
            "location",
            "odometer_reading",
            "cost",
            "station_name",
            "status",
            "submitted_by",
            "reviewed_by",
        ]
    )
    for row in records:
        writer.writerow(
            [
                row["id"],
                row["vehicle_id"],
                row["driver_name"],
                row["fuel_amount"],
                row["fuel_type"],
                row["record_date"],
                row["location"],
                row["odometer_reading"],
                row["cost"],
                row["station_name"],
                row["status"],
                row["submitted_by_username"],
                row["reviewed_by_username"] or "",
            ]
        )
    csv_data = output.getvalue()
    return Response(
        csv_data,
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=fuel_report.csv"},
    )


@staff_bp.route("/manager/stock", methods=["GET"])
@staff_login_required
@require_permissions(Permission.MANAGER_PORTAL)
def manager_stock():
    user = user_model.get_user_by_id(int(session["user_id"]))
    stock = fuel_sale_model.list_stock_for_manager()
    return render_template(
        "manager/inventory.html",
        user=user,
        role=session.get("role"),
        stock=stock,
        nav="stock",
    )
