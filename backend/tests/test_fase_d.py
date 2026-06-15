"""Fase D regression — modular routers, theme + affiliates, 48h reminders.
Run: pytest backend/tests/test_fase_d.py
"""
import os
import httpx
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))


def _api_url():
    with open(os.path.join(ROOT, "frontend", ".env")) as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL"):
                return line.split("=", 1)[1].strip() + "/api"
    raise RuntimeError("no backend url")


API = _api_url()
ADMIN = {"email": "admin@aventurate.mx", "password": "Demo2026!"}
MASTER = {"email": "owner@routiq.mx", "password": "Routiq2026!"}


@pytest.fixture(scope="module")
def admin():
    c = httpx.Client(base_url=API, timeout=30)
    assert c.post("/auth/login", json=ADMIN).status_code == 200
    yield c
    c.close()


@pytest.fixture(scope="module")
def master():
    c = httpx.Client(base_url=API, timeout=30)
    assert c.post("/auth/login", json=MASTER).status_code == 200
    yield c
    c.close()


def test_modular_routers_still_serve(admin):
    # integrations (moved to routes/integrations.py)
    assert admin.get("/companies/me/integrations").status_code == 200
    # audit (routes/audit.py)
    assert admin.get("/audit-log").status_code == 200
    assert admin.get("/metrics/audit").status_code == 200
    # quotations list (routes/quotations.py)
    assert admin.get("/quotations").status_code == 200


def test_theme_persists_and_public_exposes_it(master):
    r = master.patch("/site-settings", json={"theme": {"preset": "warm", "primary": "#C2410C"}})
    assert r.status_code == 200
    pub = httpx.get(f"{API}/site-settings/public", timeout=30).json()
    # published only changes after publish; draft holds it
    draft = master.get("/site-settings").json()["draft"]
    assert draft["theme"]["preset"] == "warm"
    # restore
    master.patch("/site-settings", json={"theme": {"preset": "corporate", "primary": "#185FA5"}})
    assert "theme" in pub


def test_affiliates_section_reconciled(master):
    pub = httpx.get(f"{API}/site-settings/public", timeout=30).json()
    keys = [s["key"] for s in pub["landing"]["sections"]]
    assert "affiliates" in keys
    assert keys[-1] == "final_cta"  # CTA stays last
    assert "affiliates_title" in pub["landing"]


def test_run_reminders_endpoint(master):
    r = master.post("/internal/run-reminders")
    assert r.status_code == 200
    data = r.json()
    assert set(["checked", "sent", "skipped"]).issubset(data.keys())


def test_reminders_requires_super_admin(admin):
    # company_admin must be forbidden
    assert admin.post("/internal/run-reminders").status_code == 403
