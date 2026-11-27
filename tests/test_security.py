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


def _create_red_kpi_result(app):
    from datetime import date
    from app.models import Service, KPIDefinition, KPIResult
    with app.app_context():
        service = Service(code="ACTION_TEST", name="Action Test House", regional_manager="Region A", service_type="Registered", active=True)
        db.session.add(service)
        db.session.flush()
        kpi = KPIDefinition(code="TEST_RISK", name="Test risk indicator", domain="Workforce", direction="lower", active=True)
        db.session.add(kpi)
        db.session.flush()
        result = KPIResult(reporting_month=date(2026, 10, 1), scope="service", service_id=service.id,
                           kpi_id=kpi.id, value_numeric=20.0, rag="Red", source="Security test")
        db.session.add(result)
        db.session.commit()
        return service.id, result.id


def test_improvement_action_create_update_and_audit(client, app):
    from app.models import ImprovementAction, ImprovementActionEvent
    from datetime import date
    provision_admin(client)
    service_id, result_id = _create_red_kpi_result(app)
    t = token(client, "/actions/new?month=2026-10")
    response = client.post("/actions/new", data={
        "csrf_token": t, "month": "2026-10", "source_ref": f"service:{result_id}",
        "title": "Reduce excessive vacancies", "description": "Review staffing capacity and recruit to approved vacancies.",
        "owner": "Registered Manager", "due_date": "2026-12-31", "priority": "High",
    })
    assert response.status_code == 302
    with app.app_context():
        action = ImprovementAction.query.one()
        action_id = action.id
        assert action.service_id == service_id
        assert action.reporting_month == date(2026, 10, 1)
        assert action.source_rag == "Red"
        assert ImprovementActionEvent.query.filter_by(action_id=action_id).count() == 1
    assert client.post(f"/actions/{action_id}/update", data={"status": "Completed"}).status_code == 400
    t = token(client, f"/actions/{action_id}")
    response = client.post(f"/actions/{action_id}/update", data={
        "csrf_token": t, "status": "Completed", "owner": "Registered Manager", "priority": "High",
        "due_date": "2026-12-31", "note": "Recruitment complete and rotas updated.",
    })
    assert response.status_code == 302
    with app.app_context():
        assert ImprovementAction.query.get(action_id).status == "Open"  # Evidence required
    response = client.post(f"/actions/{action_id}/update", data={
        "csrf_token": t, "status": "Completed", "owner": "Registered Manager", "priority": "High",
        "due_date": "2026-12-31", "note": "Recruitment complete and rotas updated.",
        "evidence_url": "https://example.org/evidence/report",
    })
    assert response.status_code == 302
    with app.app_context():
        assert ImprovementAction.query.get(action_id).status == "Completed"
        assert ImprovementActionEvent.query.filter_by(action_id=action_id).count() == 2


def test_improvement_action_viewer_cannot_mutate(client, app):
    from app.models import User
    provision_admin(client)
    service_id, result_id = _create_red_kpi_result(app)
    with app.app_context():
        viewer = User(username="scorecard-viewer", role="Viewer", active=True)
        viewer.set_password("very-long-test-passphrase")
        db.session.add(viewer)
        db.session.commit()
    t = token(client, "/")
    client.post("/logout", data={"csrf_token": t})
    t = token(client, "/login")
    client.post("/login", data={"csrf_token": t, "identity": "scorecard-viewer",
                                "password": "very-long-test-passphrase"})
    assert client.get("/actions").status_code == 200
    assert client.get("/actions/new?month=2026-10").status_code == 403
    t = token(client, "/actions")
    assert client.post("/actions/new", data={"csrf_token": t, "month": "2026-10",
        "source_ref": f"service:{result_id}"}).status_code == 403


def test_registered_manager_improvement_actions_are_scoped(client, app):
    from app.models import Service, User
    provision_admin(client)
    service_id, result_id = _create_red_kpi_result(app)
    with app.app_context():
        other = Service(code="OTHER_SITE", name="Other Site", regional_manager="Region B", active=True)
        db.session.add(other)
        db.session.flush()
        manager = User(username="scope-rm", role="Registered Manager", active=True, service_id=other.id)
        manager.set_password("very-long-test-passphrase")
        db.session.add(manager)
        db.session.commit()
    t = token(client, "/")
    client.post("/logout", data={"csrf_token": t})
    t = token(client, "/login")
    client.post("/login", data={"csrf_token": t, "identity": "scope-rm",
                                "password": "very-long-test-passphrase"})
    assert client.get("/actions").status_code == 200
    assert client.get("/actions/new?month=2026-10").status_code == 200
    t = token(client, "/actions/new?month=2026-10")
    response = client.post("/actions/new", data={
        "csrf_token": t, "month": "2026-10", "source_ref": f"service:{result_id}",
        "title": "Not authorized", "description": "Unauthorized action test details.",
        "owner": "Test", "due_date": "2026-12-31", "priority": "High",
    })
    assert response.status_code == 400


def test_performance_trends_comparison_excludes_unmatched_kpis(client, app):
    from datetime import date
    from app.models import Service, KPIDefinition
    from app.services.performance_trends import compare_performance
    provision_admin(client)
    with app.app_context():
        service = Service(code='TREND_A', name='Trend Test Site', regional_manager='Region A', active=True)
        db.session.add(service)
        db.session.flush()
        metric = KPIDefinition(code='TREND_METRIC', name='Monthly trend metric', domain='Quality', active=True)
        unmatched = KPIDefinition(code='TREND_NEW', name='New metric', domain='Quality', active=True)
        db.session.add_all([metric, unmatched])
        db.session.flush()
        db.session.add_all([
            KPIResult(reporting_month=date(2026, 9, 1), scope='service', service_id=service.id, kpi_id=metric.id, rag='Red'),
            KPIResult(reporting_month=date(2026, 10, 1), scope='service', service_id=service.id, kpi_id=metric.id, rag='Green'),
            KPIResult(reporting_month=date(2026, 10, 1), scope='service', service_id=service.id, kpi_id=unmatched.id, rag='Amber'),
        ])
        db.session.commit()
        report = compare_performance(date(2026, 10, 1), date(2026, 9, 1))
        assert report['comparable'] == 1
        assert report['improving'] == 1
        assert len(report['transitions']) == 1
        assert report['transitions'][0]['direction'] == 'Improved'
    response = client.get('/performance-trends?month=2026-10')
    assert response.status_code == 200
    assert b'Trend Test Site' in response.data
    assert b'Monthly trend metric' in response.data


def test_performance_trends_restricts_registered_manager_and_region(client, app):
    from datetime import date
    from app.models import Service, KPIDefinition, User
    provision_admin(client)
    with app.app_context():
        a = Service(code='T_SCOPE_A', name='Scoped Trend A', regional_manager='Region A', active=True)
        b = Service(code='T_SCOPE_B', name='Scoped Trend B', regional_manager='Region B', active=True)
        db.session.add_all([a, b])
        db.session.flush()
        kpi = KPIDefinition(code='SCOPE_TREND', name='Scoped KPI', domain='Quality', active=True)
        db.session.add(kpi)
        db.session.flush()
        for item in (a, b):
            db.session.add(KPIResult(reporting_month=date(2026, 10, 1), scope='service',
                                     service_id=item.id, kpi_id=kpi.id, rag='Amber'))
        manager = User(username='trend-site-manager', role='Registered Manager', active=True, service_id=a.id)
        manager.set_password('very-long-test-passphrase')
        regional = User(username='trend-regional-manager', role='Regional Manager', active=True, regional_manager='Region B')
        regional.set_password('very-long-test-passphrase')
        db.session.add_all([manager, regional]); db.session.commit()
    t = token(client, '/'); client.post('/logout', data={'csrf_token': t})
    for username, visible, hidden in [('trend-site-manager', b'Scoped Trend A', b'Scoped Trend B'),
                                       ('trend-regional-manager', b'Scoped Trend B', b'Scoped Trend A')]:
        t = token(client, '/login')
        client.post('/login', data={'csrf_token': t, 'identity': username,
                                    'password': 'very-long-test-passphrase'})
        response = client.get('/performance-trends?month=2026-10&regional_manager=Region%20A')
        assert response.status_code == 200
        assert visible in response.data
        assert hidden not in response.data
        t = token(client, '/performance-trends')
        client.post('/logout', data={'csrf_token': t})


def test_data_quality_missing_zero_and_not_applicable(client, app):
    from datetime import date
    from app.models import Service, KPIDefinition
    from app.services.data_quality import classify_result, quality_report
    provision_admin(client)
    with app.app_context():
        service = Service(code='DQ_A', name='Quality Check House', active=True)
        db.session.add(service); db.session.flush()
        metrics = [KPIDefinition(code=f'DQ_{i}', name=f'Quality indicator {i}', domain='Quality', active=True)
                   for i in range(4)]
        db.session.add_all(metrics); db.session.flush()
        db.session.add_all([
            KPIResult(reporting_month=date(2026, 10, 1), scope='service', service_id=service.id,
                      kpi_id=metrics[0].id, value_numeric=0, rag='Green'),
            KPIResult(reporting_month=date(2026, 10, 1), scope='service', service_id=service.id,
                      kpi_id=metrics[1].id, value_text='N/A', rag='Unscored'),
            KPIResult(reporting_month=date(2026, 10, 1), scope='service', service_id=service.id,
                      kpi_id=metrics[2].id, rag='Unscored'),
        ])
        db.session.commit()
        report = quality_report(date(2026, 10, 1))
        assert report['totals'] == dict(expected=4, present=1, missing=1, blank=1, na=1, zero=1)
        assert classify_result(None) == 'Missing'
        assert classify_result(KPIResult(value_numeric=0)) == 'Zero'
    response = client.get('/data-quality?month=2026-10')
    assert response.status_code == 200
    assert b'Quality Check House' in response.data


def test_data_quality_flags_and_preserves_values(client, app):
    from datetime import date
    from app.models import Service, SLSubService, KPIDefinition, SLSubServiceKPIResult
    from app.services.data_quality import quality_report
    provision_admin(client)
    with app.app_context():
        parent = Service(code='DQ_PARENT', name='Quality SL Parent', service_type='Supported Living', active=True)
        db.session.add(parent); db.session.flush()
        child_a = SLSubService(parent_service_id=parent.id, name='DQ Child A', active=True)
        child_b = SLSubService(parent_service_id=parent.id, name='DQ Child B', active=True)
        vacancy = KPIDefinition(code='VACANCY_PCT', name='Vacancy rate', domain='People', active=True)
        nps = KPIDefinition(code='NPS_SCORE', name='NPS score', domain='People', active=True)
        db.session.add_all([child_a, child_b, vacancy, nps]); db.session.flush()
        db.session.add_all([
            KPIResult(reporting_month=date(2026, 10, 1), scope='service', service_id=parent.id,
                      kpi_id=vacancy.id, value_numeric=-5, rag='Green', source='SL aggregate'),
            KPIResult(reporting_month=date(2026, 10, 1), scope='service', service_id=parent.id,
                      kpi_id=nps.id, value_numeric=100, rag='Green', source='NPS'),
            SLSubServiceKPIResult(reporting_month=date(2026, 10, 1), sub_service_id=child_a.id,
                                 kpi_id=vacancy.id, value_numeric=-5, rag='Green'),
        ])
        db.session.commit()
        report = quality_report(date(2026, 10, 1))
        kinds = {flag['kind'] for flag in report['flags']}
        assert {'Negative vacancy', 'Low NPS sample', 'SL roll-up coverage'} <= kinds
        assert KPIResult.query.filter_by(service_id=parent.id, kpi_id=vacancy.id).one().value_numeric == -5
        assert len(report['child_rows']) == 2


def test_data_quality_registered_and_regional_manager_scope(client, app):
    from datetime import date
    from app.models import Service, KPIDefinition, User
    provision_admin(client)
    with app.app_context():
        a = Service(code='DQ_SCOPE_A', name='Quality Scoped A', regional_manager='Region A', active=True)
        b = Service(code='DQ_SCOPE_B', name='Quality Scoped B', regional_manager='Region B', active=True)
        kpi = KPIDefinition(code='DQ_SCOPE_KPI', name='Quality Scope KPI', domain='Quality', active=True)
        db.session.add_all([a, b, kpi]); db.session.flush()
        for svc in (a, b):
            db.session.add(KPIResult(reporting_month=date(2026, 10, 1), scope='service',
                                    service_id=svc.id, kpi_id=kpi.id, value_numeric=0, rag='Green'))
        manager = User(username='dq-site-manager', role='Registered Manager', active=True, service_id=a.id)
        manager.set_password('very-long-test-passphrase')
        regional = User(username='dq-region-manager', role='Regional Manager', active=True, regional_manager='Region B')
        regional.set_password('very-long-test-passphrase')
        db.session.add_all([manager, regional]); db.session.commit()
    t = token(client, '/'); client.post('/logout', data={'csrf_token': t})
    for username, visible, hidden in [('dq-site-manager', b'Quality Scoped A', b'Quality Scoped B'),
                                       ('dq-region-manager', b'Quality Scoped B', b'Quality Scoped A')]:
        t = token(client, '/login')
        client.post('/login', data={'csrf_token': t, 'identity': username,
                                    'password': 'very-long-test-passphrase'})
        response = client.get('/data-quality?month=2026-10&regional_manager=Region%20A')
        assert response.status_code == 200
        assert visible in response.data
        assert hidden not in response.data
        t = token(client, '/data-quality')
        client.post('/logout', data={'csrf_token': t})

# Phase 3.36 - Monthly Board Reporting

def test_board_reporting_summary_and_saved_commentary(client, app):
    from datetime import date
    from app.models import BoardReportNarrative, AuditEvent
    from app.services.board_reporting import build_summary
    provision_admin(client)
    service_id, result_id = _create_red_kpi_result(app)
    with app.app_context():
        report = build_summary(date(2026, 10, 1), None)
        assert report["rag_counts"]["Red"] == 1
        assert report["scored_services"] == 1
        assert report["quality"]["totals"]["expected"] > 0
    page = client.get("/board-report?month=2026-10")
    assert page.status_code == 200
    assert b"Monthly Board Performance Report" in page.data
    t = token(client, "/board-report?month=2026-10")
    assert client.post("/board-report/commentary", data={
        "csrf_token": t, "month": "2026-10", "highlights": "Recruitment improved",
        "concerns": "Workforce pressures", "priorities": "Review vacancies",
    }).status_code == 302
    with app.app_context():
        record = BoardReportNarrative.query.filter_by(reporting_month=date(2026, 10, 1)).one()
        assert record.highlights == "Recruitment improved"
        assert AuditEvent.query.filter_by(entity_type="BoardReportNarrative").count() >= 1
    page = client.get("/board-report?month=2026-10")
    assert b"Recruitment improved" in page.data


def test_board_pptx_and_commentary_escaping(client, app):
    provision_admin(client)
    _create_red_kpi_result(app)
    t = token(client, "/board-report?month=2026-10")
    response = client.post("/board-report/commentary", data={
        "csrf_token": t, "month": "2026-10", "highlights": "<script>alert('x')</script>",
        "concerns": "A & B", "priorities": "Check <important> information",
    })
    assert response.status_code == 302
    page = client.get("/board-report?month=2026-10")
    assert b"&lt;script&gt;" in page.data
    response = client.get("/board-report/pptx?month=2026-10")
    assert response.status_code == 200
    assert response.mimetype == "application/vnd.openxmlformats-officedocument.presentationml.presentation"
    assert response.data.startswith(b"PK")
    assert len(response.data) > 1000
    from pptx import Presentation
    from io import BytesIO
    prs = Presentation(BytesIO(response.data))
    assert len(prs.slides) == 6
    text = " ".join(shape.text for slide in prs.slides for shape in slide.shapes if shape.has_text_frame)
    assert "Board Performance Overview" in text
    assert "<script>alert('x')</script>" in text


def test_board_reporting_is_restricted_to_portfolio_roles(client, app):
    from app.models import User
    provision_admin(client)
    service_id, _ = _create_red_kpi_result(app)
    with app.app_context():
        manager = User(username="board-scoped-manager", role="Registered Manager", active=True, service_id=service_id)
        manager.set_password("very-long-test-passphrase")
        viewer = User(username="board-report-viewer", role="Viewer", active=True)
        viewer.set_password("very-long-test-passphrase")
        db.session.add_all([manager, viewer])
        db.session.commit()
    t = token(client, "/")
    client.post("/logout", data={"csrf_token": t})
    for username in ("board-scoped-manager", "board-report-viewer"):
        t = token(client, "/login")
        client.post("/login", data={"csrf_token": t, "identity": username,
                                    "password": "very-long-test-passphrase"})
        status = 403 if username == "board-scoped-manager" else 200
        assert client.get("/board-report?month=2026-10").status_code == status
        assert client.get("/board-report/pptx?month=2026-10").status_code == status
        t = token(client, "/board-report?month=2026-10") if status == 200 else token(client, "/service/" + str(service_id))
        assert client.post("/board-report/commentary", data={
            "csrf_token": t, "month": "2026-10", "highlights": "Not permitted",
        }).status_code == 403
        client.post("/logout", data={"csrf_token": t})
