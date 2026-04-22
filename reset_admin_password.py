"""Set the admin user's password from ADMIN_INITIAL_PASSWORD or default admin#G06.

Use this if the database was created before you changed the default password in code,
or if you are locked out. Run from the project root:

    python reset_admin_password.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.chdir(ROOT)

from dotenv import load_dotenv

load_dotenv(ROOT / "backend" / ".env")
load_dotenv(ROOT / ".env")

from backend.app import create_app
from backend.models import user_model
from backend.services.auth_service import hash_password


def main() -> int:
    app = create_app()
    admin_username = (app.config.get("ADMIN_USERNAME") or "admin").strip()
    pwd = (app.config.get("ADMIN_INITIAL_PASSWORD") or os.environ.get("ADMIN_INITIAL_PASSWORD") or "admin#G06").strip()
    if not pwd:
        print("ADMIN_INITIAL_PASSWORD is empty and no default available.")
        return 1
    with app.app_context():
        u = user_model.get_user_by_username(admin_username)
        if not u:
            print(f"No user {admin_username!r} found. Start the app once to seed the admin, or create the user first.")
            return 1
        if (u["role"] or "").lower() != "admin":
            print(f"User {admin_username!r} exists but role is not admin.")
            return 1
        user_model.update_user(int(u["id"]), password_hash=hash_password(pwd))
        print(f"Password updated for {u['username']!r} (admin).")
        print("Sign in at: /admin/login")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
