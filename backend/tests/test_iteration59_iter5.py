"""Iteración 5 — backend tests

Covers:
- P0 removed: POST /api/internal/run-reminders now returns {companies, digests_sent}
- Internal digest opt-in (GET/PATCH /companies/me/integrations.internal_payment_digest)
- Manual payment follow-up endpoint POST /api/ai/quotations/{id}/follow-up-payment (503 IA no configurada expected)
- PATCH /api/quotations/{id}/notes persists notes
- Package is_private hides from public catalog/detail and internal listing includes it
"""
import os
import time
import uuid
import requests
import pytest

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://price-sync-alert.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

ADMIN = {"email": "admin@aventurate.mx", "password": "Demo2026!"}
OWNER = {"email": "owner@routiq.mx", "password": "Routiq2026!"}


def _login(creds):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json=creds, timeout=30)
    assert r.status_code == 200, f"login failed {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="module")
def admin_session():
    return _login(ADMIN)


@pytest.fixture(scope="module")
def owner_session():
    return _login(OWNER)


@pytest.fixture(scope="module")
def company_slug(admin_session):
    r = admin_session.get(f"{API}/companies/me", timeout=15)
    if r.status_code == 200:
        return r.json().get("slug")
    return "aventurate"


# ---------- P0: run-reminders returns internal digest shape ----------
def test_run_reminders_returns_internal_digest_shape(owner_session):
    r = owner_session.post(f"{API}/internal/run-reminders", timeout=60)
    assert r.status_code == 200, r.text
    data = r.json()
    assert "companies" in data and "digests_sent" in data, f"missing keys: {data}"
    assert isinstance(data["companies"], int)
    assert isinstance(data["digests_sent"], int)


def test_run_reminders_requires_super_admin(admin_session):
    r = admin_session.post(f"{API}/internal/run-reminders", timeout=30)
    assert r.status_code in (401, 403), f"expected 401/403 got {r.status_code}"


# ---------- Internal digest opt-in toggle ----------
def test_internal_digest_toggle_persists(admin_session):
    r0 = admin_session.get(f"{API}/companies/me/integrations", timeout=15)
    assert r0.status_code == 200
    initial = r0.json().get("internal_payment_digest", False)

    r1 = admin_session.patch(f"{API}/companies/me/integrations",
                             json={"internal_payment_digest": True}, timeout=15)
    assert r1.status_code == 200
    r2 = admin_session.get(f"{API}/companies/me/integrations", timeout=15)
    assert r2.json().get("internal_payment_digest") is True

    r3 = admin_session.patch(f"{API}/companies/me/integrations",
                             json={"internal_payment_digest": False}, timeout=15)
    assert r3.status_code == 200
    r4 = admin_session.get(f"{API}/companies/me/integrations", timeout=15)
    assert r4.json().get("internal_payment_digest") is False

    # restore original state
    admin_session.patch(f"{API}/companies/me/integrations",
                        json={"internal_payment_digest": bool(initial)}, timeout=15)


# ---------- Quotation notes inline + payment follow-up endpoint ----------
@pytest.fixture(scope="module")
def test_quotation(admin_session):
    """Create a client + package quotation, mark as ganada. Cleanup after tests."""
    # find any package
    pkgs = admin_session.get(f"{API}/packages", timeout=15).json()
    assert isinstance(pkgs, list) and pkgs, "need at least 1 package"
    pkg = pkgs[0]

    client_payload = {
        "name": f"TEST_ITER59_{uuid.uuid4().hex[:6]}",
        "email": f"test_{uuid.uuid4().hex[:6]}@example.com",
        "phone": "+521234567890",
        "channel": "directo",
    }
    rc = admin_session.post(f"{API}/clients", json=client_payload, timeout=15)
    assert rc.status_code in (200, 201), rc.text
    client = rc.json()

    # need at least one hotel in the package to compute pricing
    hotels = pkg.get("hotels") or []
    assert hotels, "package needs hotels for quotation compute"
    hotel_name = hotels[0].get("name", "")

    quote_payload = {
        "client_id": client["id"],
        "type": "paquete",
        "package_id": pkg["id"],
        "hotel_name": hotel_name,
        "pax": {"adults": 2, "children": 0},
        "dates": {"check_in": "2026-06-01", "check_out": "2026-06-04"},
    }
    rq = admin_session.post(f"{API}/quotations", json=quote_payload, timeout=20)
    assert rq.status_code in (200, 201), rq.text
    q = rq.json()

    # move to ganada
    rs = admin_session.patch(f"{API}/quotations/{q['id']}/state",
                             json={"state": "ganada"}, timeout=15)
    assert rs.status_code == 200

    yield q

    # cleanup
    try:
        admin_session.delete(f"{API}/quotations/{q['id']}", timeout=15)
    except Exception:
        pass
    try:
        admin_session.delete(f"{API}/clients/{client['id']}", timeout=15)
    except Exception:
        pass


def test_patch_quotation_notes(admin_session, test_quotation):
    qid = test_quotation["id"]
    text = f"Nota interna iter5 {uuid.uuid4().hex[:6]}"
    r = admin_session.patch(f"{API}/quotations/{qid}/notes", json={"notes": text}, timeout=15)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("ok") is True
    assert body.get("notes") == text

    # verify persistence via GET
    g = admin_session.get(f"{API}/quotations/{qid}", timeout=15)
    assert g.status_code == 200
    assert g.json().get("notes") == text


def test_follow_up_payment_endpoint_wired(admin_session, test_quotation):
    """AI is not configured in preview → expect 503 with 'IA no configurada' or 'IA no disponible' (wiring OK, not 404)."""
    qid = test_quotation["id"]
    r = admin_session.post(f"{API}/ai/quotations/{qid}/follow-up-payment", timeout=30)
    assert r.status_code != 404, "endpoint missing (should exist)"
    # Expected 503 because BYOK AI not configured in this env
    assert r.status_code in (200, 503), f"unexpected status {r.status_code}: {r.text}"
    if r.status_code == 503:
        detail = (r.json() or {}).get("detail", "")
        assert "IA" in detail or "AI" in detail or "no" in detail.lower()


# ---------- Package is_private ----------
def test_package_is_private_hides_from_public_catalog(admin_session, company_slug):
    # find a public (not private) package to toggle
    pkgs = admin_session.get(f"{API}/packages", timeout=15).json()
    target = next((p for p in pkgs if p.get("status") != "inactive" and not p.get("is_private")), None)
    assert target is not None, "need at least 1 public active package"
    code = target.get("code")
    pid = target["id"]

    # public catalog endpoint is /api/public/company/{slug}
    cat = requests.get(f"{API}/public/company/{company_slug}", timeout=15).json()
    codes_before = {p.get("code") for p in (cat.get("packages") or [])}
    assert code in codes_before, f"package {code} not in public catalog initially; got {codes_before}"

    det_before = requests.get(f"{API}/public/package/{company_slug}/{code}", timeout=15)
    assert det_before.status_code == 200

    # mark private
    r = admin_session.patch(f"{API}/packages/{pid}", json={"is_private": True}, timeout=15)
    assert r.status_code == 200, r.text

    try:
        cat2 = requests.get(f"{API}/public/company/{company_slug}", timeout=15).json()
        codes_after = {p.get("code") for p in (cat2.get("packages") or [])}
        assert code not in codes_after, "private package should be hidden from public catalog"

        det_after = requests.get(f"{API}/public/package/{company_slug}/{code}", timeout=15)
        assert det_after.status_code == 404, f"expected 404 got {det_after.status_code}"

        # still visible internally
        pkgs2 = admin_session.get(f"{API}/packages", timeout=15).json()
        internal_codes = {p.get("code") for p in pkgs2}
        assert code in internal_codes, "private package should still show internally"
    finally:
        admin_session.patch(f"{API}/packages/{pid}", json={"is_private": False}, timeout=15)
