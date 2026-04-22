from __future__ import annotations

import pytest

from backend.app import create_app
from backend.models import user_model
from backend.services.auth_service import hash_password
from config import TestConfig


@pytest.fixture()
def app(tmp_path):
    class LocalTestConfig(TestConfig):
        DATABASE_PATH = str(tmp_path / "fuelguard_test.sqlite")

    application = create_app(LocalTestConfig)
    yield application


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def admin_user(app):
    with app.app_context():
        user_model.create_user(
            "Admin User",
            "admin",
            "admin@test.local",
            hash_password("admin#G06"),
            "admin",
            None,
            None,
            "active",
        )


@pytest.fixture()
def sales_user(app):
    with app.app_context():
        user_model.create_user(
            "Sales User",
            "sales1",
            "sales@test.local",
            hash_password("SalesPass123!"),
            "sales",
            None,
            "Front counter",
            "active",
        )


@pytest.fixture()
def manager_user(app):
    with app.app_context():
        user_model.create_user(
            "Manager User",
            "manager1",
            "manager@test.local",
            hash_password("ManagerPass123!"),
            "manager",
            None,
            "Ops",
            "active",
        )


@pytest.fixture()
def accountant_user(app):
    with app.app_context():
        user_model.create_user(
            "Accountant User",
            "acct1",
            "acct@test.local",
            hash_password("AccountantPass123!"),
            "accountant",
            None,
            "Finance",
            "active",
        )
