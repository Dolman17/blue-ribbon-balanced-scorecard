"""Security regression checks. Run: python -m pytest -q tests/test_security.py

Uses a new temporary SQLite file: never touches /data/bsc.db.
"""
import os
import tempfile
from io import BytesIO
from pathlib import Path

# Config is evaluated at import, so supply isolated test settings first.
_TEST_FOLDER = tempfile.TemporaryDirectory(prefix="bsc-security-test-")
os.environ["DATABASE_PATH"] = str(Path(_TEST_FOLDER.name) / "security_test.db")
os.environ["SECRET_KEY"] = "test-only-session-secret-01234567890123456789012345"
os.environ["ADMIN_SETUP_TOKEN"] = "test-only-setup-token-01234567890123456789012345"
os.environ["BSC_DEV_MODE"] = "1"

import pytest
from openpyxl import Workbook
from app import create_app
from app.extensions import db
from app.models import User, KPIResult
from app.services.importer import import_workbook
from app.services.exporter import _safe_excel_text


@pytest.fixture()
def app():
    instance = create_app()
    instance.config.update(TESTING=True)
    with instance.app_context():
        db.drop_all()
        db.create_all()
    yield instance
    with instance.app_context():
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


def token(client, path):
    client.get(path)
    with client.session_transaction() as sess:
        return sess["_csrf_token"]


def provision_admin(client):
    t = token(client, "/setup")
    return client.post("/setup", data={
        "csrf_token": t,
        "setup_token": os.environ["ADMIN_SETUP_TOKEN"],
        "username": "test-admin", "password": "very-long-test-passphrase",
        "confirm_password": "very-long-test-passphrase",
    })


def test_setup_cannot_bypass_csrf_or_token(client):
    assert client.post("/setup", data={"username": "x"}).status_code == 400
    t = token(client, "/setup")
    assert client.post("/setup", data={"csrf_token": t, "setup_token": "incorrect"}).status_code == 403
    assert provision_admin(client).status_code == 302


def test_login_csrf_and_external_redirect(client):
    provision_admin(client)
    t = token(client, "/")
    client.post("/logout", data={"csrf_token": t})
    assert client.post("/login", data={"identity": "test-admin", "password": "very-long-test-passphrase"}).status_code == 400
    t = token(client, "/login")
    response = client.post("/login?next=//evil.example/", data={
        "csrf_token": t, "identity": "test-admin", "password": "very-long-test-passphrase",
    })
    assert response.status_code == 302
    assert response.location.endswith("/")
    assert "evil.example" not in response.location


def test_login_rate_limit(client):
    provision_admin(client)
    t = token(client, "/")
    client.post("/logout", data={"csrf_token": t})
    t = token(client, "/login")
    for _ in range(8):
        assert client.post("/login", data={"csrf_token": t, "identity": "test-admin", "password": "bad"}).status_code == 200
    assert client.post("/login", data={"csrf_token": t, "identity": "test-admin", "password": "bad"}).status_code == 429


def test_dashboard_ajax_requires_csrf(client):
    provision_admin(client)
    assert client.post("/dashboard/layout/reset").status_code == 400
    t = token(client, "/")
    assert client.post("/dashboard/layout/reset", headers={"X-CSRF-Token": t}).status_code == 200


def test_export_formula_safety():
    assert _safe_excel_text("=1+1") == "'=1+1"
    assert _safe_excel_text("@SUM(A1)") == "'@SUM(A1)"
    assert _safe_excel_text("Some comment") == "Some comment"


def test_failed_import_is_atomic(app):
    with app.app_context():
        wb = Workbook()
        services = wb.active
        services.title = "Services"
        services.append(["Service Code", "Service Name"])
        services.append(["NEW_SERVICE", "Should not be saved"])
        kpi = wb.create_sheet("KPI_Data")
        kpi.append(["Reporting Month", "Scope", "Service Code", "KPI Code", "Value"])
        kpi.append(["2026-10-01", "Service", "NOT_A_SERVICE", "SAF E", 1])
        data = BytesIO()
        wb.save(data)
        data.seek(0)
        result = import_workbook(data, "test.xlsx")
        assert result["rows_rejected"] == 1
        assert result["rows_imported"] == 0
        from app.models import Service
        assert Service.query.filter_by(code="NEW_SERVICE").first() is None
