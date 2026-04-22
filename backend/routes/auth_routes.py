"""Public landing, registration, staff login, and logout."""
from __future__ import annotations

from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from backend.models import user_model
from backend.services import audit_service
from backend.services.auth_service import verify_password
from backend.services.logging_service import log_event
from backend.services.validation_service import (
    validate_email,
    validate_password,
    validate_registrable_role,
    validate_required_text,
    validate_username,
)
from backend.security.session_manager import (
    clear_failed_login,
    clear_session,
    is_login_locked,
    register_failed_login,
    refresh_session_activity,
    staff_login_required,
)

staff_bp = Blueprint("staff", __name__)
ROLE_LABELS = {
    "sales": "Salesperson",
    "manager": "Manager",
    "accountant": "Accountant",
}


def _redirect_staff_home(role: str) -> str:
    mapping = {
        "sales": "staff.sales_dashboard",
        "manager": "staff.manager_dashboard",
        "accountant": "staff.accountant_dashboard",
    }
    return url_for(mapping.get(role, "admin.dashboard" if role == "admin" else "staff.login"))


def _parse_role(raw_role: str) -> str:
    role = (raw_role or "").strip().lower()
    return "sales" if role == "salesperson" else role


@staff_bp.get("/")
def landing():
    return render_template("shared/landing.html")


@staff_bp.get("/register")
def register_page():
    return render_template("shared/register.html", selected_role="sales")


@staff_bp.post("/register")
def register():
    from backend.services.auth_service import hash_password

    full_name = (request.form.get("full_name") or "").strip()
    email = (request.form.get("email") or "").strip().lower()
    username = (request.form.get("username") or "").strip()
    password = request.form.get("password") or ""
    confirm_password = request.form.get("confirm_password") or ""
    phone = (request.form.get("phone") or "").strip()
    role = _parse_role(request.form.get("role") or "")

    errors: list[str] = []
    for ok, msg in (
        validate_required_text(full_name, field="Full name", max_len=120),
        validate_required_text(phone, field="Phone number", max_len=30),
        validate_email(email),
        validate_username(username),
        validate_password(password, min_length=8),
        validate_registrable_role(role),
    ):
        if not ok:
            errors.append(msg)
    if role == "admin":
        errors.append("Admin accounts cannot be registered.")
    if password != confirm_password:
        errors.append("Passwords do not match.")
    if user_model.get_user_by_email(email):
        errors.append("Email already exists.")
    if user_model.get_user_by_username(username):
        errors.append("Username already exists.")

    if errors:
        for err in errors:
            flash(err, "error")
        return render_template("shared/register.html", selected_role=role or "sales"), 400

    user_model.create_user(
        full_name,
        username,
        email,
        hash_password(password),
        role,
        phone or None,
        None,
        user_model.STATUS_PENDING,
    )
    log_event(f"User registration pending admin approval username={username!r} role={role}")
    audit_service.record(
        audit_service.ACTION_USER_CREATED,
        username=username,
        details=f"self-registration pending role={role}",
    )
    flash(
        "Your account was created and is pending administrator approval. "
        "An admin must activate your account before you can sign in.",
        "success",
    )
    return redirect(url_for("staff.role_login_page", role=role))


@staff_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        if session.get("user_id"):
            return redirect(_redirect_staff_home(session.get("role", "")))
        selected = _parse_role(request.args.get("role") or "sales")
        if selected not in ROLE_LABELS:
            selected = "sales"
        return render_template(
            "shared/login.html", selected_role=selected, role_labels=ROLE_LABELS
        )
    return _handle_login(_parse_role(request.form.get("role") or ""))


@staff_bp.get("/<role>/login")
def role_login_page(role: str):
    selected = _parse_role(role)
    if selected not in ROLE_LABELS:
        return redirect(url_for("staff.login"))
    return render_template(
        "shared/login.html", selected_role=selected, role_labels=ROLE_LABELS
    )


@staff_bp.post("/login/<role>")
def login_for_role(role: str):
    normalized = _parse_role(role)
    if normalized not in ROLE_LABELS:
        flash("Invalid role selection.", "error")
        return redirect(url_for("staff.login"))
    return _handle_login(normalized)


def _handle_login(selected_role: str):
    selected_role = _parse_role(selected_role)
    if selected_role not in ROLE_LABELS:
        selected_role = ""

    username = (request.form.get("username") or "").strip().lower()
    password = request.form.get("password") or ""

    if not username or not password:
        flash("Missing credentials.", "error")
        return (
            render_template(
                "shared/login.html",
                selected_role=selected_role,
                role_labels=ROLE_LABELS,
            ),
            400,
        )
    if is_login_locked(username):
        log_event(f"Locked staff login attempt username={username!r}", level="warning")
        audit_service.record(
            audit_service.ACTION_LOGIN_FAILED,
            username=username,
            details="staff portal: account locked",
        )
        flash("Too many failed attempts. Try again later.", "error")
        return (
            render_template(
                "shared/login.html",
                selected_role=selected_role,
                role_labels=ROLE_LABELS,
            ),
            429,
        )

    user = user_model.get_user_by_username(username) or user_model.get_user_by_email(username)
    if not user or not verify_password(password, user["password_hash"]):
        register_failed_login(username)
        log_event(f"Failed staff login attempt username={username!r}")
        audit_service.record(
            audit_service.ACTION_LOGIN_FAILED,
            username=username,
            details="staff portal: invalid credentials",
        )
        flash("Invalid username or password.", "error")
        return (
            render_template(
                "shared/login.html",
                selected_role=selected_role,
                role_labels=ROLE_LABELS,
            ),
            401,
        )
    clear_failed_login(username)

    st = (user["status"] or "").lower()
    if st == "pending":
        log_event(f"Pending account login attempt username={username!r}")
        flash(
            "Your account is pending administrator approval. "
            "You will be able to use the system after an admin activates your account.",
            "error",
        )
        return (
            render_template(
                "shared/login.html",
                selected_role=selected_role,
                role_labels=ROLE_LABELS,
            ),
            403,
        )
    if st != "active":
        log_event(f"Disabled account login attempt username={username!r}")
        flash("Account disabled.", "error")
        return (
            render_template(
                "shared/login.html",
                selected_role=selected_role,
                role_labels=ROLE_LABELS,
            ),
            403,
        )

    role = (user["role"] or "").lower()
    if role == "admin":
        log_event(f"Blocked admin login on shared portal username={username!r}", level="warning")
        flash("Admin must sign in from the dedicated admin portal.", "error")
        return (
            render_template(
                "shared/login.html",
                selected_role=selected_role or "sales",
                role_labels=ROLE_LABELS,
            ),
            403,
        )
    if selected_role and role != selected_role:
        flash("Selected role does not match this account.", "error")
        return (
            render_template(
                "shared/login.html",
                selected_role=selected_role,
                role_labels=ROLE_LABELS,
            ),
            403,
        )

    session.clear()
    session.permanent = True
    session["user_id"] = user["id"]
    session["username"] = user["username"]
    session["role"] = role
    refresh_session_activity()

    log_event(f"Login success user_id={user['id']} role={role}")
    audit_service.record(
        audit_service.ACTION_LOGIN_SUCCESS,
        user_id=int(user["id"]),
        username=user["username"],
        details=f"staff portal role={role}",
    )
    nxt = request.args.get("next")
    if nxt and nxt.startswith("/") and not nxt.startswith("//"):
        return redirect(nxt)
    return redirect(_redirect_staff_home(role))


@staff_bp.route("/logout", methods=["POST"])
def logout():
    uid = session.get("user_id")
    uname = session.get("username")
    clear_session()
    if uid:
        log_event(f"User logout user_id={uid}")
        audit_service.record(
            audit_service.ACTION_LOGOUT,
            user_id=int(uid),
            username=uname,
            details="staff portal",
        )
    flash("You have been signed out.")
    return redirect(url_for("staff.login"))
