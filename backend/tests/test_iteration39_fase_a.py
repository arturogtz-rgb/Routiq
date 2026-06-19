"""
Iteration 39 - FASE A backend tests.

Covers:
- Quotation paquete create with show_price_breakdown=false and custom_items;
  pricing must include the custom concept as kind='custom', subtotal includes it,
  and commission applies only to 'publico' items (services + custom_publico).
- Public payload exposes show_price_breakdown.
- Public PDF endpoint returns 200 application/pdf for an existing token.
- Booking-confirmation prefill (ganada): _prefill=True with agent_name, passenger_name,
  num_persons, lodging[0] (hotel/checkin/checkout/nights/room_type), and services
  prefilled from package inclusions.
- Booking-confirmation PDF endpoints (auth + public) return 200 application/pdf.
- Package inclusions persist after create.
"""

import os
import io
import pytest
import requests

def _read_base_url():
    url = os.environ.get("REACT_APP_BACKEND_URL")
    if not url:
        env_path = "/app/frontend/.env"
        if os.path.exists(env_path):
            with open(env_path) as f:
                for line in f:
                    if line.startswith("REACT_APP_BACKEND_URL="):
                        url = line.split("=", 1)[1].strip()
                        break
    if not url:
        raise RuntimeError("REACT_APP_BACKEND_URL not configured")
    return url.rstrip("/")


BASE_URL = _read_base_url()
PUBLIC_TOKEN = "E4cWS--ucnOiioZotwHcD8OM"  # show_price_breakdown=false, show_all_occupancies=true
EXEC_EMAIL = "ejecutivo@aventurate.mx"
EXEC_PASS = "Demo2026!"


# ---------- fixtures ----------
@pytest.fixture(scope="session")
def exec_session():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login",
               json={"email": EXEC_EMAIL, "password": EXEC_PASS},
               timeout=20)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text[:200]}"
    return s


@pytest.fixture(scope="session")
def admin_session():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login",
               json={"email": "admin@aventurate.mx", "password": "Demo2026!"},
               timeout=20)
    assert r.status_code == 200, f"admin login failed: {r.status_code}"
    return s


@pytest.fixture(scope="session")
def first_client_id(exec_session):
    r = exec_session.get(f"{BASE_URL}/api/clients", timeout=20)
    assert r.status_code == 200
    data = r.json()
    items = data if isinstance(data, list) else data.get("items", [])
    assert items, "no clients available for tests"
    return items[0]["id"]


@pytest.fixture(scope="session")
def first_package(exec_session):
    r = exec_session.get(f"{BASE_URL}/api/packages", timeout=20)
    assert r.status_code == 200
    data = r.json()
    items = data if isinstance(data, list) else data.get("items", [])
    assert items, "no packages available"
    return items[0]


# ---------- pricing with custom_items ----------
class TestQuotationCustomItems:
    def test_create_paquete_with_custom_item_and_no_breakdown(self, exec_session, first_client_id, first_package):
        payload = {
            "client_id": first_client_id,
            "type": "paquete",
            "package_id": first_package["id"],
            "hotel_name": (first_package.get("hotels") or [{"name": ""}])[0].get("name", ""),
            "dates": {"start": "2026-08-10", "end": "2026-08-13"},
            "pax": {"adultos": 2, "menores": 0, "rooms": [{"ocupacion": "doble", "count": 1}]},
            "services": [],
            "show_price_breakdown": False,
            "custom_items": [{
                "category": "tour",
                "name": "Tour privado",
                "net_price": 1500,
                "price_type": "publico",
                "unit": "per_person",
                "qty": 0,
            }],
        }
        r = exec_session.post(f"{BASE_URL}/api/quotations", json=payload, timeout=30)
        assert r.status_code == 201, f"{r.status_code} {r.text[:400]}"
        q = r.json()

        # show_price_breakdown stored as false
        assert q.get("show_price_breakdown") is False
        # custom_items stored on quotation
        assert isinstance(q.get("custom_items"), list) and len(q["custom_items"]) == 1
        assert q["custom_items"][0]["name"] == "Tour privado"

        # custom concept appears in items with kind=custom
        items = q.get("items", [])
        custom = [it for it in items if it.get("kind") == "custom"]
        assert len(custom) == 1, f"expected 1 custom item, got {len(custom)}: {items}"
        cust = custom[0]
        assert cust.get("price_type") == "publico"
        # per_person * 2 adultos = 3000
        assert cust.get("subtotal") == 3000, f"subtotal={cust.get('subtotal')}"

        # subtotal includes custom amount
        sub_no_custom = sum(it["subtotal"] for it in items if it.get("kind") != "custom")
        assert q["subtotal"] >= sub_no_custom + cust["subtotal"] - 0.01

        # commission applies to publico services + custom_publico
        # since custom is publico, commission should include 3000 * rate
        commission_rate = q.get("commission_rate", 0)
        if commission_rate:
            # commission >= 3000 * rate (only custom contributes if no services)
            expected_min = round(3000 * commission_rate, 2)
            assert q["commission"] + 0.01 >= expected_min

        # cleanup
        try:
            exec_session.delete(f"{BASE_URL}/api/quotations/{q['id']}", timeout=10)
        except Exception:
            pass


# ---------- public payload + PDF ----------
class TestPublic:
    def test_public_payload_exposes_show_price_breakdown(self):
        r = requests.get(f"{BASE_URL}/api/public/quotations/{PUBLIC_TOKEN}", timeout=20)
        assert r.status_code == 200, r.text[:300]
        data = r.json()
        q = data.get("quotation") or data
        assert "show_price_breakdown" in q, f"keys={list(q.keys())[:30]}"
        # we know this token was set to false
        assert q["show_price_breakdown"] is False

    def test_public_pdf_returns_200_pdf(self):
        r = requests.get(f"{BASE_URL}/api/public/quotations/{PUBLIC_TOKEN}/pdf", timeout=30)
        assert r.status_code == 200
        ctype = r.headers.get("content-type", "")
        assert "application/pdf" in ctype, ctype
        assert r.content[:5] == b"%PDF-", r.content[:20]


# ---------- booking confirmation prefill ----------
class TestBookingPrefill:
    def test_prefill_ganada(self, exec_session, admin_session, first_client_id, first_package):
        # 1) Create paquete quotation with package having inclusions
        # First, ensure the package has at least one inclusion - patch if needed (admin role)
        pkg = first_package
        inc = pkg.get("inclusions") or {}
        need_patch = not any([inc.get("arrival_transfer"), inc.get("departure_transfer"),
                              inc.get("tours"), inc.get("venue_access"), inc.get("lodging")])
        if need_patch:
            r = admin_session.patch(
                f"{BASE_URL}/api/packages/{pkg['id']}",
                json={"inclusions": {"arrival_transfer": True, "departure_transfer": True,
                                     "lodging": True, "tours": True, "venue_access": False,
                                     "extras": "Coctel de bienvenida"}},
                timeout=20)
            assert r.status_code in (200, 204), f"package update failed: {r.status_code} {r.text[:200]}"

        payload = {
            "client_id": first_client_id,
            "type": "paquete",
            "package_id": pkg["id"],
            "hotel_name": (pkg.get("hotels") or [{"name": ""}])[0].get("name", "Hotel Demo"),
            "dates": {"start": "2026-09-10", "end": "2026-09-13"},
            "pax": {"adultos": 2, "menores": 0, "rooms": [{"ocupacion": "doble", "count": 1}]},
            "services": [],
            "contacts": {
                "agency": {"name": "Mi Agencia", "contact": "Agente Demo", "phone": "+523310000000"},
                "traveler": {"name": "Pasajero Demo", "phone": "+523320000000"},
            },
            "show_price_breakdown": True,
            "custom_items": [],
        }
        r = exec_session.post(f"{BASE_URL}/api/quotations", json=payload, timeout=30)
        assert r.status_code == 201, r.text[:300]
        q = r.json()
        qid = q["id"]

        # 2) move state to ganada
        r = exec_session.patch(f"{BASE_URL}/api/quotations/{qid}/state",
                               json={"state": "ganada"}, timeout=15)
        assert r.status_code in (200, 204), r.text[:300]

        # 3) fetch booking-confirmation (no previous)
        r = exec_session.get(f"{BASE_URL}/api/quotations/{qid}/booking-confirmation", timeout=20)
        assert r.status_code == 200, r.text[:300]
        bc = r.json()

        assert bc.get("_prefill") is True, f"_prefill missing: {list(bc.keys())[:20]}"
        assert bc.get("agent_name"), "agent_name empty"
        assert bc.get("passenger_name") == "Pasajero Demo"
        # 2 adultos
        assert str(bc.get("num_persons")) == "2"

        lodging = bc.get("lodging") or []
        assert lodging, "lodging not prefilled"
        l0 = lodging[0]
        assert l0.get("hotel"), "lodging[0].hotel empty"
        assert l0.get("checkin") == "2026-09-10"
        assert l0.get("checkout") == "2026-09-13"
        assert str(l0.get("nights")) in ("3", "")  # may be 3
        assert l0.get("room_type") == "Doble"

        # services prefilled from inclusions
        services = bc.get("services") or []
        names = [s.get("service", "") for s in services]
        # we set arrival_transfer, departure_transfer, lodging, tours, extras above
        assert any("Traslado de llegada" in n for n in names), names
        assert any("Tours" in n for n in names), names

        # 4) POST a confirmation and then test both PDFs (auth + public)
        # First make sure it doesn't error
        save_payload = {
            "agent_name": bc["agent_name"],
            "agent_phone": bc.get("agent_phone", ""),
            "agent_company": bc.get("agent_company", ""),
            "reservation_date": bc["reservation_date"],
            "passenger_name": bc["passenger_name"],
            "passenger_phone": bc.get("passenger_phone", ""),
            "num_persons": bc["num_persons"],
            "services": bc["services"],
            "lodging": bc["lodging"],
            "general_observations": "",
            "price_per_person": bc["price_per_person"],
            "total_amount": bc["total_amount"],
        }
        r = exec_session.post(f"{BASE_URL}/api/quotations/{qid}/booking-confirmation",
                              json=save_payload, timeout=20)
        assert r.status_code in (200, 201), r.text[:300]
        conf = r.json()
        conf_id = conf.get("id")
        token = conf.get("token")
        assert conf_id and token, conf

        # auth PDF
        r = exec_session.get(f"{BASE_URL}/api/booking-confirmations/{conf_id}/pdf", timeout=30)
        assert r.status_code == 200, r.text[:200]
        assert "application/pdf" in r.headers.get("content-type", "")
        assert r.content[:5] == b"%PDF-"

        # public PDF
        r2 = requests.get(f"{BASE_URL}/api/public/booking-confirmation/{token}/pdf", timeout=30)
        assert r2.status_code == 200
        assert "application/pdf" in r2.headers.get("content-type", "")
        assert r2.content[:5] == b"%PDF-"

        # cleanup
        try:
            exec_session.delete(f"{BASE_URL}/api/quotations/{qid}", timeout=10)
        except Exception:
            pass


# ---------- inclusions persistence ----------
class TestPackageInclusions:
    def test_create_package_with_inclusions_and_reread(self, admin_session):
        payload = {
            "code": "TEST-INC-39",
            "name": "TEST Pack Inclusions iter39",
            "nights": 2,
            "description": "test",
            "inclusions": {
                "arrival_transfer": True,
                "departure_transfer": False,
                "lodging": True,
                "tours": True,
                "venue_access": False,
                "extras": "Welcome drink",
            },
        }
        r = admin_session.post(f"{BASE_URL}/api/packages", json=payload, timeout=20)
        if r.status_code == 400:
            # already exists; find and patch
            r2 = admin_session.get(f"{BASE_URL}/api/packages", timeout=20)
            data = r2.json()
            items = data if isinstance(data, list) else data.get("items", [])
            existing = next((p for p in items if p.get("code") == "TEST-INC-39"), None)
            assert existing is not None
            pkg_id = existing["id"]
            r = admin_session.patch(f"{BASE_URL}/api/packages/{pkg_id}",
                                    json={"inclusions": payload["inclusions"]}, timeout=20)
            assert r.status_code in (200, 204), r.text[:200]
        else:
            assert r.status_code in (200, 201), r.text[:300]
            pkg = r.json()
            pkg_id = pkg["id"]

        # GET and verify
        r = admin_session.get(f"{BASE_URL}/api/packages/{pkg_id}", timeout=20)
        assert r.status_code == 200
        pkg = r.json()
        inc = pkg.get("inclusions") or {}
        assert inc.get("arrival_transfer") is True
        assert inc.get("departure_transfer") is False
        assert inc.get("lodging") is True
        assert inc.get("tours") is True
        assert inc.get("venue_access") is False
        assert inc.get("extras") == "Welcome drink"

        # cleanup
        try:
            admin_session.delete(f"{BASE_URL}/api/packages/{pkg_id}", timeout=10)
        except Exception:
            pass
