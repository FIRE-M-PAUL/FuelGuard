"""Admin portal: authentication, user lifecycle, retail prices, logs."""
from __future__ import annotations

from pathlib import Path

from flask import Blueprint, current_app, flash, redirect, render_template, request, session, url_for

from backend.models import (
    audit_log_model,
    fuel_adjustment_request_model,
    fuel_sale_model,
    station_model,
    user_model,
)
from backend.services import audit_service
from backend.services.auth_service import hash_password, verify_password
from backend.services.logging_service import log_event
from backend.services import validation_service
from backend.security.session_manager import (
    admin_login_required,
    clear_failed_login,
    is_login_locked,
    register_failed_login,
    refresh_session_activity,
    role_required,
)

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


@admin_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        if session.get("user_id") and (session.get("role") or "").lower() == "admin":
            return redirect(url_for("admin.dashboard"))
        return render_template("shared/admin_login.html")

    username = (request.form.get("username") or "").strip()
    password = request.form.get("password") or ""

    if not username or not password:
        flash("Invalid username or password.", "error")
        return render_template("shared/admin_login.html"), 400
    if is_login_locked(username):
        log_event(f"Locked admin login attempt username={username!r}", level="warning")
        audit_service.record(
            audit_service.ACTION_LOGIN_FAILED,
            username=username.strip().lower(),
            details="admin portal: account locked",
        )
        flash("Too many failed attempts. Try again later.", "error")
        return render_template("shared/admin_login.html"), 429

    user = user_model.get_user_by_username(username)
    if not user or not verify_password(password, user["password_hash"]):
        register_failed_login(username)
        log_event(f"Failed admin login attempt username={username!r}")
        audit_service.record(
            audit_service.ACTION_LOGIN_FAILED,
            username=(username or "").strip().lower(),
            details="admin portal: invalid credentials",
        )
        flash("Invalid username or password.", "error")
        return render_template("shared/admin_login.html"), 401
    clear_failed_login(username)

    role = (user["role"] or "").lower()
    if role != "admin":
        log_event(
            f"Non-admin attempted admin portal login username={username!r} role={role!r}"
        )
        flash("Access denied. Admin privileges required.", "error")
        return render_template("shared/admin_login.html"), 403

    if (user["status"] or "").lower() != "active":
        flash("Account disabled.", "error")
        return render_template("shared/admin_login.html"), 403

    session.clear()
    session.permanent = True
    session["user_id"] = user["id"]
    session["username"] = user["username"]
    session["role"] = "admin"
    refresh_session_activity()

    log_event(f"Admin login success user_id={user['id']}")
    audit_service.record(
        audit_service.ACTION_LOGIN_SUCCESS,
        user_id=int(user["id"]),
        username=user["username"],
        details="admin portal",
    )
    nxt = request.args.get("next")
    if nxt and nxt.startswith("/") and not nxt.startswith("//"):
        return redirect(nxt)
    return redirect(url_for("admin.dashboard"))


@admin_bp.route("/dashboard")
@admin_login_required
@role_required("admin")
def dashboard():
    users = user_model.list_users()
    current_id = int(session["user_id"])
    fuel_adj_pending = fuel_adjustment_request_model.count_pending_for_admin()
    fuel_adj_preview = fuel_adjustment_request_model.list_pending_for_admin(limit=6)
    return render_template(
        "admin/dashboard.html",
        users=users,
        current_user_id=current_id,
        role=session.get("role"),
        username=session.get("username"),
        fuel_adj_pending=fuel_adj_pending,
        fuel_adj_preview=fuel_adj_preview,
    )


@admin_bp.route("/register_user", methods=["GET", "POST"])
@admin_login_required
@role_required("admin")
def register_user():
    if request.method == "GET":
        return render_template("admin/manage_users.html")

    username = request.form.get("username") or ""
    email = request.form.get("email") or ""
    password = request.form.get("password") or ""
    role = (request.form.get("role") or "").strip().lower()
    department = validation_service.sanitize_optional_str(
        request.form.get("department"), max_len=120
    )
    status = (request.form.get("status") or "active").strip().lower()

    ok_u, err_u = validation_service.validate_username(username)
    ok_e, err_e = validation_service.validate_email(email)
    ok_p, err_p = validation_service.validate_password(password)
    ok_r, err_r = validation_service.validate_role(role)
    ok_s, err_s = validation_service.validate_status(status)

    errors = []
    for ok, msg in (
        (ok_u, err_u),
        (ok_e, err_e),
        (ok_p, err_p),
        (ok_r, err_r),
        (ok_s, err_s),
    ):
        if not ok:
            errors.append(msg)

    if errors:
        for e in errors:
            flash(e)
        return render_template("admin/manage_users.html"), 400

    if user_model.get_user_by_username(username):
        flash("Username already exists.")
        return render_template("admin/manage_users.html"), 400

    if user_model.get_user_by_email(email):
        flash("Email already exists.")
        return render_template("admin/manage_users.html"), 400

    pwd_hash = hash_password(password)
    new_id = user_model.create_user(
        username.strip(),
        username.strip(),
        email.strip(),
        pwd_hash,
        role,
        None,
        department or None,
        status,
    )
    log_event(
        f"User created by admin admin_id={session.get('user_id')} new_user_id={new_id} "
        f"role={role} username={username.strip()!r}"
    )
    audit_service.record(
        audit_service.ACTION_USER_CREATED,
        user_id=int(session["user_id"]),
        username=session.get("username"),
        details=f"new_user_id={new_id} role={role} new_username={username.strip()!r}",
    )
    flash("User created successfully.")
    return redirect(url_for("admin.register_user"))


@admin_bp.route("/users/<int:user_id>/delete", methods=["POST"])
@admin_login_required
@role_required("admin")
def delete_user(user_id: int):
    if user_id == int(session["user_id"]):
        flash("You cannot delete your own account.")
        return redirect(url_for("admin.dashboard"))

    row = user_model.get_user_by_id(user_id)
    if not row:
        flash("User not found.")
        return redirect(url_for("admin.dashboard"))

    user_model.delete_user(user_id)
    log_event(
        f"User deleted by admin admin_id={session.get('user_id')} deleted_user_id={user_id}"
    )
    audit_service.record(
        audit_service.ACTION_USER_DELETED,
        user_id=int(session["user_id"]),
        username=session.get("username"),
        details=f"deleted_user_id={user_id} deleted_username={row['username']!r}",
    )
    flash("User deleted.")
    return redirect(url_for("admin.dashboard"))


@admin_bp.route("/users/<int:user_id>/toggle_status", methods=["POST"])
@admin_login_required
@role_required("admin")
def toggle_user_status(user_id: int):
    row = user_model.get_user_by_id(user_id)
    if not row:
        flash("User not found.")
        return redirect(url_for("admin.dashboard"))
    if user_id == int(session["user_id"]):
        flash("You cannot deactivate your own account.")
        return redirect(url_for("admin.dashboard"))

    st = (row["status"] or "").lower()
    if st == "active":
        new_status = "inactive"
    else:
        new_status = "active"
    user_model.update_user(user_id, status=new_status)
    log_event(
        f"User status changed by admin admin_id={session.get('user_id')} "
        f"user_id={user_id} status={new_status}"
    )
    if st == "pending" and new_status == "active":
        flash("Account approved. The user can now sign in.")
    else:
        flash(f"User status set to {new_status}.")
    return redirect(url_for("admin.dashboard"))


@admin_bp.route("/users/<int:user_id>/reset_password", methods=["POST"])
@admin_login_required
@role_required("admin")
def reset_password(user_id: int):
    new_password = request.form.get("new_password") or ""
    ok, msg = validation_service.validate_password(new_password, min_length=8)
    if not ok:
        flash(msg)
        return redirect(url_for("admin.dashboard"))

    row = user_model.get_user_by_id(user_id)
    if not row:
        flash("User not found.")
        return redirect(url_for("admin.dashboard"))

    user_model.update_user(user_id, password_hash=hash_password(new_password))
    log_event(
        f"Password reset by admin admin_id={session.get('user_id')} target_user_id={user_id}"
    )
    flash("Password has been reset.")
    return redirect(url_for("admin.dashboard"))


@admin_bp.route("/retail_prices", methods=["GET", "POST"])
@admin_login_required
@role_required("admin")
def retail_prices():
    if request.method == "GET":
        prices = fuel_sale_model.get_retail_prices_dict()
        return render_template("admin/retail_prices.html", prices=prices)

    errors: list[str] = []
    updated: list[str] = []
    for ft in sorted(fuel_sale_model.ALLOWED_FUEL_TYPES):
        field = "petrol_price" if ft == "Petrol" else "diesel_price"
        raw = (request.form.get(field) or "").strip()
        try:
            val = float(raw)
        except ValueError:
            errors.append(f"{ft}: enter a valid price.")
            continue
        ok, err = fuel_sale_model.set_retail_price_per_litre(ft, val)
        if not ok:
            errors.append(f"{ft}: {err or 'Update failed.'}")
        else:
            updated.append(ft)

    if errors:
        for e in errors:
            flash(e, "error")
        prices = fuel_sale_model.get_retail_prices_dict()
        return render_template("admin/retail_prices.html", prices=prices), 400

    log_event(
        f"Admin updated retail selling prices admin_id={session.get('user_id')} "
        f"fuels={updated!r}"
    )
    flash(
        "Selling prices per litre saved. Counter staff will use these rates on the next sale.",
        "success",
    )
    return redirect(url_for("admin.retail_prices"))


@admin_bp.route("/settings", methods=["GET", "POST"])
@admin_login_required
@role_required("admin")
def admin_settings():
    if request.method == "POST":
        name = (request.form.get("station_name") or "").strip() or station_model.DEFAULT_STATION_NAME
        station_model.set_setting("station_name", name[:200])
        log_event(f"Admin updated station_name admin_id={session.get('user_id')}")
        audit_service.record(
            "settings_updated",
            user_id=int(session["user_id"]),
            username=session.get("username"),
            details="station_name",
        )
        flash("Station settings saved.", "success")
        return redirect(url_for("admin.admin_settings"))
    return render_template(
        "admin/settings.html",
        station_name=station_model.station_name(),
        username=session.get("username"),
        role=session.get("role"),
    )


@admin_bp.route("/audit-logs")
@admin_login_required
@role_required("admin")
def admin_audit_logs_db():
    rows = audit_log_model.list_recent(limit=500)
    return render_template(
        "admin/audit_logs.html",
        entries=rows,
        username=session.get("username"),
        role=session.get("role"),
    )


@admin_bp.route("/logs")
@admin_login_required
@role_required("admin")
def view_logs():
    logs_dir = Path(str(current_app.config.get("LOGS_DIR", "")))
    log_file = logs_dir / "system.log"
    lines: list[str] = []
    if log_file.is_file():
        text = log_file.read_text(encoding="utf-8", errors="replace").splitlines()
        lines = text[-200:]
    return render_template("admin/reports.html", lines=lines)
