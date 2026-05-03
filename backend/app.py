import os
import sys
import threading
import webbrowser
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, abort, jsonify, redirect, render_template, request, send_from_directory, url_for
from flask_wtf.csrf import CSRFError
from werkzeug.utils import safe_join

BACKEND_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = BACKEND_ROOT.parent
FRONTEND_ROOT = PROJECT_ROOT / "frontend"
load_dotenv(BACKEND_ROOT / ".env")
load_dotenv(PROJECT_ROOT / ".env")

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config import Config, validate_production_config  # noqa: E402

from backend.extensions import csrf  # noqa: E402
from backend.models import user_model  # noqa: E402
from backend.models import audit_log_model  # noqa: E402
from backend.routes.api_sec_routes import api_sec_bp  # noqa: E402
from backend.routes.auth_routes import staff_bp  # noqa: E402
from backend.routes.inventory_routes import fuel_bp  # noqa: E402
from backend.routes.user_routes import admin_bp  # noqa: E402
import backend.routes.inventory_routes  # noqa: E402,F401 — staff + fuel API routes
import backend.routes.report_routes  # noqa: E402,F401
import backend.routes.sales_routes  # noqa: E402,F401
import backend.routes.station_routes  # noqa: E402,F401
import backend.routes.fuel_adjustment_routes  # noqa: E402,F401
from backend.services.auth_service import hash_password  # noqa: E402
from backend.services.logging_service import log_event  # noqa: E402


def _seed_initial_admin(app: Flask) -> None:
    if app.testing:
        return
    admin_username = (app.config.get("ADMIN_USERNAME") or "admin").strip()
    if user_model.get_user_by_username(admin_username):
        return
    raw = app.config.get("ADMIN_INITIAL_PASSWORD") or "admin#G06"
    admin_email = (app.config.get("ADMIN_EMAIL") or "admin@fuelguard.local").strip().lower()
    user_model.create_user(
        "System Administrator",
        admin_username,
        admin_email,
        hash_password(raw),
        "admin",
        None,
        None,
        "active",
    )
    log_event(f"System admin account initialized username={admin_username!r}.")


def _sync_admin_password_if_requested(app: Flask) -> None:
    """Re-hash admin password when ADMIN_SYNC_PASSWORD_AT_STARTUP=1 (local recovery)."""
    if app.testing:
        return
    if not app.config.get("ADMIN_SYNC_PASSWORD_AT_STARTUP"):
        return
    admin_username = (app.config.get("ADMIN_USERNAME") or "admin").strip()
    raw = (app.config.get("ADMIN_INITIAL_PASSWORD") or "admin#G06").strip()
    if not raw:
        return
    u = user_model.get_user_by_username(admin_username)
    if not u or (u["role"] or "").lower() != "admin":
        return
    user_model.update_user(int(u["id"]), password_hash=hash_password(raw))
    log_event(
        "Admin password re-hashed from ADMIN_INITIAL_PASSWORD (ADMIN_SYNC_PASSWORD_AT_STARTUP was set). "
        "Remove that env var after a successful login.",
        level="warning",
    )


def create_app(config_object: type | None = None) -> Flask:
    config_object = config_object or Config
    app = Flask(
        __name__,
        template_folder=str(FRONTEND_ROOT),
        static_folder=str(FRONTEND_ROOT / "assets"),
        static_url_path="/static",
    )
    app.config.from_object(config_object)
    app.config["PROJECT_ROOT"] = str(PROJECT_ROOT)

    if not app.testing:
        validate_production_config(config_object)

    csrf.init_app(app)

    app.register_blueprint(staff_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(fuel_bp)
    app.register_blueprint(api_sec_bp)

    @app.get("/<path:filename>")
    def project_static_files(filename: str):
        reserved = (
            "login",
            "logout",
            "register",
            "sales",
            "manager",
            "accountant",
            "admin",
            "static",
            "api",
        )
        first = filename.split("/")[0]
        if first in reserved:
            abort(404)

        for base_dir in (FRONTEND_ROOT, PROJECT_ROOT):
            safe_path = safe_join(str(base_dir), filename)
            if not safe_path:
                continue
            file_path = Path(safe_path)
            if file_path.is_file():
                return send_from_directory(base_dir, filename)

        abort(404)

    @app.teardown_appcontext
    def _close_db(_exc):
        user_model.close_db()

    def _wants_json() -> bool:
        return request.path.startswith("/api/") or "application/json" in (request.headers.get("Accept") or "")

    @app.errorhandler(CSRFError)
    def _handle_csrf_error(err: CSRFError):
        log_event(f"CSRF validation failed path={request.path} reason={err.description}", level="warning")
        if _wants_json():
            return jsonify({"ok": False, "error": "Invalid CSRF token"}), 400
        return (
            render_template(
                "shared/error.html",
                code=400,
                title="Invalid CSRF token",
                message="Invalid CSRF token",
            ),
            400,
        )

    @app.errorhandler(400)
    def _bad_request(_err):
        if _wants_json():
            return jsonify({"ok": False, "error": "bad request"}), 400
        return render_template("shared/error.html", code=400, title="Bad request", message="Your request is invalid."), 400

    @app.errorhandler(401)
    def _unauthorized(_err):
        if _wants_json():
            return jsonify({"ok": False, "error": "unauthorized"}), 401
        return render_template("shared/error.html", code=401, title="Unauthorized", message="Please sign in first."), 401

    @app.errorhandler(403)
    def _forbidden(_err):
        if _wants_json():
            return jsonify({"ok": False, "error": "forbidden"}), 403
        return render_template("shared/error.html", code=403, title="Access denied", message="You do not have permission."), 403

    @app.errorhandler(404)
    def _not_found(_err):
        if _wants_json():
            return jsonify({"ok": False, "error": "not found"}), 404
        return render_template("shared/error.html", code=404, title="Not found", message="Page or resource was not found."), 404

    @app.errorhandler(500)
    def _internal_error(err):
        log_event(f"Unhandled server error path={request.path} error={err!r}", level="error")
        if _wants_json():
            return jsonify({"ok": False, "error": "internal server error"}), 500
        return render_template("shared/error.html", code=500, title="Server error", message="An unexpected error occurred."), 500

    with app.app_context():
        user_model.init_db()
        from backend.models import fuel_model

        fuel_model.init_db()
        from backend.models import fuel_sale_model

        fuel_sale_model.init_db()
        from backend.models import accounting_model

        accounting_model.init_db()
        audit_log_model.init_db()
        from backend.models import station_model

        station_model.init_db()
        from backend.models import fuel_adjustment_request_model

        fuel_adjustment_request_model.init_db()
        _seed_initial_admin(app)
        _sync_admin_password_if_requested(app)

    return app


def _should_open_browser() -> bool:
    open_browser = os.environ.get("OPEN_BROWSER", "1").strip().lower()
    return open_browser in {"1", "true", "yes", "on"}


def _open_browser(url: str) -> None:
    webbrowser.open(url, new=2)


def main() -> None:
    app = create_app()
    host = os.environ.get("FLASK_HOST", "127.0.0.1")
    port = int(os.environ.get("FLASK_PORT", "5000"))
    debug = os.environ.get("FLASK_DEBUG", "1").strip().lower() in {"1", "true", "yes", "on"}

    is_reloader_process = os.environ.get("WERKZEUG_RUN_MAIN") == "true"
    should_open = _should_open_browser() and (not debug or is_reloader_process)
    if should_open:
        url = f"http://{host}:{port}/"
        threading.Timer(1.0, _open_browser, args=(url,)).start()

    app.run(host=host, port=port, debug=debug)


if __name__ == "__main__":
    main()
