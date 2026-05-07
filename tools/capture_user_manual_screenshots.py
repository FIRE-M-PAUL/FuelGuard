from pathlib import Path
from time import sleep
import shutil
import sqlite3
import sys

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backend.security.password_hashing import hash_password

BASE_URL = "http://127.0.0.1:5000"
OUT_DIR = Path("user_manual_screenshots")
DB_PATH = Path("fuelguard.db")
DB_BACKUP = OUT_DIR / "_fuelguard_backup_for_screenshots.db"
TEMP_CAPTURE_PASSWORD = "ManualCap#2026"


def ensure_out_dir() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)


def save_shot(page, filename: str) -> None:
    page.screenshot(path=str(OUT_DIR / filename), full_page=True)


def get_username_for_role(role: str) -> str:
    conn = sqlite3.connect(DB_PATH)
    try:
        row = conn.execute(
            "SELECT username FROM users WHERE role = ? AND LOWER(status) = 'active' ORDER BY id LIMIT 1",
            (role,),
        ).fetchone()
        if not row:
            raise RuntimeError(f"No active user found for role: {role}")
        return row[0]
    finally:
        conn.close()


def set_temp_password(username: str) -> None:
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute(
            "UPDATE users SET password_hash = ?, status = 'active' WHERE username = ?",
            (hash_password(TEMP_CAPTURE_PASSWORD), username),
        )
        conn.commit()
    finally:
        conn.close()


def login_staff(page, username: str, role: str) -> None:
    page.goto(f"{BASE_URL}/login", wait_until="networkidle")
    page.fill("#username", username)
    page.fill("#password", TEMP_CAPTURE_PASSWORD)
    page.select_option("#role", role)
    page.click("button[type='submit']")
    page.wait_for_load_state("networkidle")
    if "/login" in page.url:
        raise RuntimeError(f"Staff login failed for {username} ({role}).")


def login_admin(page) -> bool:
    page.goto(f"{BASE_URL}/admin/login", wait_until="networkidle")
    page.fill("#username", "admin")
    page.fill("#password", "admin#G06")
    page.click("button[type='submit']")
    page.wait_for_load_state("networkidle")
    return "/admin/login" not in page.url


def capture_flow() -> None:
    ensure_out_dir()
    if DB_PATH.exists():
        shutil.copy2(DB_PATH, DB_BACKUP)
    manager_username = get_username_for_role("manager")
    sales_username = get_username_for_role("sales")
    set_temp_password(manager_username)
    set_temp_password(sales_username)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1920, "height": 1080})
        page = context.new_page()

        # 1) Login page
        page.goto(f"{BASE_URL}/login", wait_until="networkidle")
        save_shot(page, "login_page.png")

        # 2) Login as manager (dashboard/reports)
        login_staff(page, manager_username, "manager")
        page.goto(f"{BASE_URL}/manager/dashboard", wait_until="networkidle")
        save_shot(page, "dashboard_page.png")
        page.goto(f"{BASE_URL}/manager/reports", wait_until="networkidle")
        save_shot(page, "reports_page.png")

        # Logout screenshot from manager session
        try:
            page.click("button:has-text('Logout')", timeout=3000)
        except PlaywrightTimeoutError:
            page.goto(f"{BASE_URL}/manager/dashboard", wait_until="networkidle")
            page.click("button:has-text('Logout')")
        page.wait_for_load_state("networkidle")
        sleep(0.3)
        save_shot(page, "logout_page.png")

        # Record Fuel Sale page from sales role
        login_staff(page, sales_username, "sales")
        page.goto(f"{BASE_URL}/sales/sell", wait_until="networkidle")
        save_shot(page, "sales_page.png")

        # User Management (Administrator)
        admin_page = context.new_page()
        if login_admin(admin_page):
            admin_page.goto(f"{BASE_URL}/admin/register_user", wait_until="networkidle")
            save_shot(admin_page, "user_management_page.png")
        else:
            save_shot(admin_page, "user_management_page.png")

        admin_page.close()
        page.close()
        context.close()
        browser.close()
    if DB_BACKUP.exists():
        shutil.copy2(DB_BACKUP, DB_PATH)
        DB_BACKUP.unlink(missing_ok=True)


if __name__ == "__main__":
    capture_flow()
