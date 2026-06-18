"""Iteration 34 — Backend regression for Phase 1 pricing engine rewrite (PAQUETES).

Business rules under test:
- Catalog stores TARIFAS NETAS for packages.
- Public price = neto / margin_divisor.
- Channel pricing:
    * directo / agencia -> Público (no commission, no price_note)
    * mayorista         -> Público * (1 - commissions.mayorista). price_note set.
    * operador          -> Tarifa Neta original.                   price_note set.
- Minors with minor_price > 0 add to subtotal/total (Issue 2).
- Mixed quotation (paquete + servicio): commission applies ONLY to services.
- Servicios-only quotations are unchanged (público - commission per channel).
- Public catalog endpoints expose PRECIO PÚBLICO (not neto) — Issue 1.
- Public quotation link exposes price_note.
- PDF endpoint returns 200 valid PDF for every channel.
"""
from __future__ import annotations

import os
import math
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://neto-a-publico.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

ADMIN = {"email": "admin@aventurate.mx", "password": "Demo2026!"}

# Catálogo seed (from review request + verified live)
SLUG = "aventurate"
PACK_CODE = "GDL-TEQ-3N"
HOTEL_NAME = "Hotel Riu Plaza Guadalajara"
NETO_DOBLE = 8900.0
NETO_MINOR = 4500.0
MARGIN_DIVISOR = 0.76
COMM_MAYORISTA = 0.15
COMM_AGENCIA = 0.12
COMM_OPERADOR = 0.20

PUB_DOBLE = round(NETO_DOBLE / MARGIN_DIVISOR, 2)  # 11710.53
PUB_MINOR = round(NETO_MINOR / MARGIN_DIVISOR, 2)  # 5921.05


def _approx(a: float, b: float, tol: float = 1.0) -> bool:
    # tol $1: allow rounding accumulating across line items
    return abs(float(a) - float(b)) <= tol


@pytest.fixture(scope="module")
def session():
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json=ADMIN, timeout=20)
    assert r.status_code == 200, r.text
    return s


@pytest.fixture(scope="module")
def clients(session):
    r = session.get(f"{API}/clients", timeout=20)
    assert r.status_code == 200
    cs = {c["channel"]: c for c in r.json()}
    # Make sure we have mayorista and operador (create if missing)
    for channel in ("mayorista", "operador"):
        if channel not in cs:
            payload = {
                "name": f"TEST_{channel}_iter34",
                "email": f"test_{channel}_iter34@example.com",
                "phone": "5551234567",
                "channel": channel,
            }
            rc = session.post(f"{API}/clients", json=payload, timeout=20)
            assert rc.status_code in (200, 201), rc.text
            cs[channel] = rc.json()
    return cs


@pytest.fixture(scope="module")
def package_id(session):
    r = session.get(f"{API}/packages", timeout=20)
    assert r.status_code == 200
    pack = next(p for p in r.json() if p["code"] == PACK_CODE)
    return pack["id"]


@pytest.fixture(scope="module")
def service_id(session):
    r = session.get(f"{API}/services", timeout=20)
    assert r.status_code == 200
    svcs = r.json()
    if svcs:
        return svcs[0]["id"]
    # create one if catalog is empty
    payload = {"name": "TEST_servicio_iter34", "category": "extra",
               "unit": "per_person", "public_price": 1000, "description": ""}
    rc = session.post(f"{API}/services", json=payload, timeout=20)
    assert rc.status_code in (200, 201), rc.text
    return rc.json()["id"]


def _create_quote(session, client_id, package_id, menores=0, services=None, hotel=HOTEL_NAME):
    payload = {
        "client_id": client_id,
        "type": "paquete",
        "package_id": package_id,
        "hotel_name": hotel,
        "dates": {"start": "2026-03-10", "end": "2026-03-13"},
        "pax": {"adultos": 2, "menores": menores, "rooms": [{"ocupacion": "doble", "count": 1}]},
        "services": services or [],
        "notes": "",
    }
    r = session.post(f"{API}/quotations", json=payload, timeout=30)
    assert r.status_code == 201, r.text
    q = r.json()
    # also verify GET returns same
    rg = session.get(f"{API}/quotations/{q['id']}", timeout=20)
    assert rg.status_code == 200
    assert rg.json()["id"] == q["id"]
    return q


# =====================================================================
# 1) Paquete · canal DIRECTO/AGENCIA -> unit_price = Público, sin commission
# =====================================================================
@pytest.mark.parametrize("channel", ["directo", "agencia"])
def test_paquete_directo_agencia_publico_sin_comision(session, clients, package_id, channel):
    q = _create_quote(session, clients[channel]["id"], package_id)
    hosp = [it for it in q["items"] if it.get("kind") == "hospedaje"]
    assert hosp, "Debe haber item hospedaje"
    h0 = hosp[0]
    assert _approx(h0["unit_price"], PUB_DOBLE), f"unit_price={h0['unit_price']} esperado {PUB_DOBLE}"
    # net_price y public_price expuestos en item
    assert _approx(h0.get("net_price", 0), NETO_DOBLE)
    assert _approx(h0.get("public_price", 0), PUB_DOBLE)
    # No comisión en paquetes
    assert _approx(q["commission"], 0.0), f"commission={q['commission']} debe ser 0"
    assert _approx(q["total"], q["subtotal"]), "total debe igualar subtotal cuando no hay servicios"
    assert (q.get("price_note") or "") == "", f"price_note debe ser vacío para {channel}"


# =====================================================================
# 2) Paquete · canal MAYORISTA -> público * (1 - comm.mayorista) + price_note
# =====================================================================
def test_paquete_mayorista_publico_menos_comision_y_nota(session, clients, package_id):
    q = _create_quote(session, clients["mayorista"]["id"], package_id)
    h = next(it for it in q["items"] if it.get("kind") == "hospedaje")
    expected = round(PUB_DOBLE * (1 - COMM_MAYORISTA), 2)
    assert _approx(h["unit_price"], expected), f"unit_price={h['unit_price']} esperado {expected}"
    assert _approx(q["commission"], 0.0), "Paquetes NO comisionables incluso para mayorista"
    assert q.get("price_note") == "Precio neto no comisionable"


# =====================================================================
# 3) Paquete · canal OPERADOR -> tarifa neta + price_note
# =====================================================================
def test_paquete_operador_tarifa_neta_y_nota(session, clients, package_id):
    q = _create_quote(session, clients["operador"]["id"], package_id)
    h = next(it for it in q["items"] if it.get("kind") == "hospedaje")
    assert _approx(h["unit_price"], NETO_DOBLE), f"unit_price={h['unit_price']} esperado {NETO_DOBLE}"
    assert _approx(q["commission"], 0.0)
    assert q.get("price_note") == "Precio neto no comisionable"


# =====================================================================
# 4) Menores suman al subtotal/total (Issue 2)
# =====================================================================
@pytest.mark.parametrize("channel,expected_minor_unit", [
    ("directo", PUB_MINOR),
    ("mayorista", round(PUB_MINOR * (1 - COMM_MAYORISTA), 2)),
    ("operador", NETO_MINOR),
])
def test_menores_se_suman_al_total(session, clients, package_id, channel, expected_minor_unit):
    q = _create_quote(session, clients[channel]["id"], package_id, menores=2)
    menor_items = [it for it in q["items"] if "Menor" in it.get("label", "")]
    assert menor_items, f"Debe existir item 'Menor' en items={[it['label'] for it in q['items']]}"
    m = menor_items[0]
    assert _approx(m["unit_price"], expected_minor_unit, tol=0.5), \
        f"menor unit_price={m['unit_price']} esperado {expected_minor_unit}"
    assert m["qty"] == 2
    # sumar todos los hospedaje y validar subtotal
    expected_sub = sum(it["subtotal"] for it in q["items"])
    assert _approx(q["subtotal"], expected_sub, tol=0.5)


# =====================================================================
# 5) Mixta: paquete + servicio -> commission solo en servicio
# =====================================================================
def test_paquete_mas_servicio_comision_solo_servicios(session, clients, package_id, service_id):
    # Use AGENCIA so commission rate is non-zero (0.12)
    services = [{"service_id": service_id, "qty": 2}]
    q = _create_quote(session, clients["agencia"]["id"], package_id, services=services)
    paq_items = [it for it in q["items"] if it.get("kind") in ("hospedaje", "noche_extra")]
    svc_items = [it for it in q["items"] if it.get("kind") == "servicio"]
    assert paq_items and svc_items, "Debe haber items de paquete y servicio"
    svc_sub = sum(it["subtotal"] for it in svc_items)
    expected_commission = round(svc_sub * COMM_AGENCIA, 2)
    assert _approx(q["commission"], expected_commission, tol=0.5), \
        f"commission={q['commission']} esperado solo servicios*rate={expected_commission}"
    expected_subtotal = sum(it["subtotal"] for it in q["items"])
    assert _approx(q["subtotal"], expected_subtotal, tol=0.5)
    assert _approx(q["total"], q["subtotal"] - q["commission"], tol=0.5)


# =====================================================================
# 6) Servicios-only -> commission sobre todo el subtotal (sin paquete)
# =====================================================================
def test_servicios_only_commission_sobre_subtotal(session, clients, service_id):
    payload = {
        "client_id": clients["agencia"]["id"],
        "type": "servicios",
        "dates": {"start": "2026-03-10", "end": "2026-03-13"},
        "pax": {"adultos": 2, "menores": 0},
        "services": [{"service_id": service_id, "qty": 3}],
        "notes": "",
    }
    r = session.post(f"{API}/quotations", json=payload, timeout=20)
    assert r.status_code == 201, r.text
    q = r.json()
    assert q["type"] == "servicios"
    expected_commission = round(q["subtotal"] * COMM_AGENCIA, 2)
    assert _approx(q["commission"], expected_commission, tol=0.5)
    assert _approx(q["total"], q["subtotal"] - q["commission"], tol=0.5)
    assert (q.get("price_note") or "") == ""


# =====================================================================
# 7) Catálogo público -> base_price = neto/divisor (Issue 1)
# =====================================================================
def test_public_company_catalog_muestra_precio_publico():
    r = requests.get(f"{API}/public/company/{SLUG}", timeout=20)
    assert r.status_code == 200, r.text
    data = r.json()
    pack = next(p for p in data["packages"] if p["code"] == PACK_CODE)
    # min neto en GDL-TEQ-3N = 5800 (Demetria cuadruple) -> público = 5800/0.76 = 7631.58
    expected = round(5800.0 / MARGIN_DIVISOR, 2)
    assert _approx(pack["base_price"], expected, tol=0.5), \
        f"base_price={pack['base_price']} esperado neto-min/divisor={expected}"
    # debe ser MAYOR al neto mínimo (confirma que ya NO publica el neto crudo)
    assert pack["base_price"] > 5800.0


def test_public_package_muestra_precio_publico():
    r = requests.get(f"{API}/public/package/{SLUG}/{PACK_CODE}", timeout=20)
    assert r.status_code == 200, r.text
    pack = r.json()["package"]
    expected = round(5800.0 / MARGIN_DIVISOR, 2)
    assert _approx(pack["base_price"], expected, tol=0.5)
    assert pack["base_price"] > 5800.0


# =====================================================================
# 8) Enlace público de cotización expone price_note y items con unit_price canal
# =====================================================================
def test_public_link_quotation_expone_price_note(session, clients, package_id):
    q = _create_quote(session, clients["mayorista"]["id"], package_id)
    r = session.post(f"{API}/quotations/{q['id']}/public-link", timeout=20)
    assert r.status_code == 200, r.text
    token = r.json()["token"]
    rp = requests.get(f"{API}/public/quotations/{token}", timeout=20)
    assert rp.status_code == 200, rp.text
    pub_q = rp.json()["quotation"]
    assert pub_q.get("price_note") == "Precio neto no comisionable"
    hosp = next(it for it in pub_q["items"] if it.get("kind") == "hospedaje")
    expected = round(PUB_DOBLE * (1 - COMM_MAYORISTA), 2)
    assert _approx(hosp["unit_price"], expected, tol=0.5)


# =====================================================================
# 9) PDF returns 200 for every channel
# =====================================================================
@pytest.mark.parametrize("channel", ["directo", "agencia", "mayorista", "operador"])
def test_pdf_descarga_ok_todos_los_canales(session, clients, package_id, channel):
    q = _create_quote(session, clients[channel]["id"], package_id, menores=1)
    r = session.get(f"{API}/quotations/{q['id']}/pdf", timeout=30)
    assert r.status_code == 200, f"PDF {channel} failed: {r.status_code} {r.text[:200]}"
    assert r.content[:4] == b"%PDF", "Respuesta no es un PDF válido"
    assert len(r.content) > 1000, "PDF demasiado pequeño"


# =====================================================================
# 10) Cleanup TEST_ clients
# =====================================================================
def test_cleanup_test_clients(session, clients):
    for ch in ("mayorista", "operador"):
        c = clients.get(ch)
        if c and c.get("name", "").startswith("TEST_"):
            session.delete(f"{API}/clients/{c['id']}", timeout=20)
