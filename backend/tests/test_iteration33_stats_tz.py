"""Iteration 33 — period-over-period deltas in /api/stats/sales + report_timezone persistence."""
import os
import pytest
import requests

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
ADMIN = {"email": "admin@aventurate.mx", "password": "Demo2026!"}
EXEC = {"email": "ejecutivo@aventurate.mx", "password": "Demo2026!"}


@pytest.fixture(scope="module")
def admin_session():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json=ADMIN, timeout=15)
    assert r.status_code == 200, r.text
    return s


@pytest.fixture(scope="module")
def exec_session():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json=EXEC, timeout=15)
    assert r.status_code == 200, r.text
    return s


# ---------- Stats deltas ----------
@pytest.mark.parametrize("period", ["week", "month", "quarter", "year"])
def test_stats_has_previous_and_deltas(admin_session, period):
    r = admin_session.get(f"{BASE_URL}/api/stats/sales", params={"period": period}, timeout=30)
    assert r.status_code == 200, r.text
    data = r.json()
    # previous block
    assert "previous" in data, "missing 'previous' key"
    prev = data["previous"]
    for k in ("revenue_total", "collected_total", "conversion"):
        assert k in prev, f"previous.{k} missing"
    for k in ("total", "won", "lost", "rate"):
        assert k in prev["conversion"], f"previous.conversion.{k} missing"
    # deltas block
    assert "deltas" in data
    deltas = data["deltas"]
    for k in ("revenue", "collected", "created", "won", "rate"):
        assert k in deltas, f"deltas.{k} missing"
        v = deltas[k]
        assert v is None or isinstance(v, (int, float)), f"deltas.{k} must be number|null, got {type(v)}"


def test_executive_cannot_access_stats(exec_session):
    r = exec_session.get(f"{BASE_URL}/api/stats/sales", params={"period": "month"}, timeout=15)
    assert r.status_code == 403


# ---------- Report timezone ----------
def test_get_integrations_default_timezone(admin_session):
    r = admin_session.get(f"{BASE_URL}/api/companies/me/integrations", timeout=15)
    assert r.status_code == 200
    data = r.json()
    assert "report_timezone" in data
    # default or whatever was set before; must be a non-empty string
    assert isinstance(data["report_timezone"], str) and data["report_timezone"]


def test_patch_valid_timezone_persists(admin_session):
    r = admin_session.patch(f"{BASE_URL}/api/companies/me/integrations",
                            json={"report_timezone": "America/Cancun"}, timeout=15)
    assert r.status_code == 200
    assert r.json().get("report_timezone") == "America/Cancun"
    # re-GET confirms persistence
    g = admin_session.get(f"{BASE_URL}/api/companies/me/integrations", timeout=15).json()
    assert g["report_timezone"] == "America/Cancun"


def test_patch_invalid_timezone_ignored(admin_session):
    r = admin_session.patch(f"{BASE_URL}/api/companies/me/integrations",
                            json={"report_timezone": "Foo/Bar"}, timeout=15)
    assert r.status_code == 200, r.text  # not 500
    # value retained as Cancun (from previous test)
    assert r.json().get("report_timezone") == "America/Cancun"


def test_restore_timezone_cdmx(admin_session):
    r = admin_session.patch(f"{BASE_URL}/api/companies/me/integrations",
                            json={"report_timezone": "America/Mexico_City"}, timeout=15)
    assert r.status_code == 200
    assert r.json().get("report_timezone") == "America/Mexico_City"


# ---------- Regressions ----------
def test_send_report_graceful_no_provider(admin_session):
    r = admin_session.post(f"{BASE_URL}/api/stats/sales/send-report",
                           params={"period": "week"}, timeout=30)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("ok") is False
    assert "detail" in body and isinstance(body["detail"], str) and body["detail"]


def test_export_xlsx_ok(admin_session):
    r = admin_session.get(f"{BASE_URL}/api/stats/sales/export", params={"period": "week"}, timeout=30)
    assert r.status_code == 200
    assert "spreadsheet" in r.headers.get("content-type", "")
    assert len(r.content) > 1000  # non-empty xlsx
    assert r.content[:2] == b"PK"  # xlsx is a zip


def test_report_config_persists(admin_session):
    r = admin_session.patch(f"{BASE_URL}/api/companies/me/integrations",
                            json={"report_enabled": True, "report_frequency": "weekly",
                                  "report_day": 1, "report_hour": 8}, timeout=15)
    assert r.status_code == 200
    data = r.json()
    assert data["report_enabled"] is True
    assert data["report_frequency"] == "weekly"
    assert data["report_day"] == 1
    assert data["report_hour"] == 8
