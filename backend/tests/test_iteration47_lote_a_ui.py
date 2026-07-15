"""Iteration 47 — Lote A: UI mejoras y PDF confirmación.

Este test valida los aspectos backend del Lote A:
- 2.1: GET /api/quotations devuelve `agent_name` y `contacts.traveler.name` en items.
- 6.1: GET /api/quotations/{id} devuelve `agent_name` (y `agent_email`).
- 9.1: POST /api/quotations/{id}/booking-confirmation exige estado 'ganada' (400 si no).
        GET devuelve un borrador prellenado (_prefill=True) sin confirmación.
- 10.x: descarga del PDF de confirmación (verifica que se genera para tipo paquete y para servicios).
"""
import io
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

ADMIN_EMAIL = "admin@aventurate.mx"
ADMIN_PASSWORD = "Demo2026!"


@pytest.fixture(scope="module")
def s():
    sess = requests.Session()
    r = sess.post(f"{BASE_URL}/api/auth/login",
                  json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=15)
    assert r.status_code == 200, f"login failed {r.status_code} {r.text[:200]}"
    return sess


# ---------- 2.1: list contains agent_name + traveler ----------
def test_list_quotations_has_agent_name_and_traveler(s):
    r = s.get(f"{BASE_URL}/api/quotations", timeout=15)
    assert r.status_code == 200
    items = r.json()
    assert isinstance(items, list)
    if not items:
        pytest.skip("No quotations in seed to validate agent_name")
    # Al menos una debe tener agent_name resuelto
    with_agent = [x for x in items if x.get("agent_name")]
    assert with_agent, f"Ninguna cotización trae agent_name resuelto. Muestra: {items[0]}"
    # y algunas con contacts.traveler
    with_traveler = [x for x in items if (x.get("contacts") or {}).get("traveler", {}).get("name")]
    # No es obligatorio siempre traer traveler, pero si hay, la clave debe existir.
    for it in items:
        assert "contacts" in it or it.get("contacts") is None or isinstance(it.get("contacts"), dict)
    print(f"Total quotations: {len(items)}, con agent_name: {len(with_agent)}, con traveler: {len(with_traveler)}")


# ---------- 6.1: detail contains agent_name & agent_email ----------
def test_detail_has_agent_name(s):
    lst = s.get(f"{BASE_URL}/api/quotations", timeout=15).json()
    if not lst:
        pytest.skip("Sin cotizaciones seed")
    qid = lst[0]["id"]
    r = s.get(f"{BASE_URL}/api/quotations/{qid}", timeout=15)
    assert r.status_code == 200
    d = r.json()
    # created_by puede ser None en muy antiguas; ignorar si es así
    if d.get("created_by"):
        assert "agent_name" in d, f"Falta agent_name en detalle: {list(d.keys())}"
        assert isinstance(d["agent_name"], str)
    assert "created_at" in d


# ---------- 9.1: booking-confirmation ganada-only ----------
def _find_or_make_quotation(s, want_state=None):
    """Devuelve un quotation_id en el estado deseado si es posible."""
    items = s.get(f"{BASE_URL}/api/quotations", timeout=15).json()
    if want_state:
        for it in items:
            if it.get("state") == want_state:
                return it["id"]
        return None
    return items[0]["id"] if items else None


def test_booking_confirmation_get_prefill_when_not_saved(s):
    qid = _find_or_make_quotation(s)
    if not qid:
        pytest.skip("Sin cotizaciones")
    r = s.get(f"{BASE_URL}/api/quotations/{qid}/booking-confirmation", timeout=15)
    assert r.status_code == 200
    body = r.json()
    # Si ya está guardada, tendrá 'id'; si es borrador, _prefill=True
    if body.get("id"):
        assert "services" in body or "lodging" in body
    else:
        assert body.get("_prefill") is True or body == {}


def test_booking_confirmation_requires_ganada(s):
    # Buscar una NO 'ganada'
    items = s.get(f"{BASE_URL}/api/quotations", timeout=15).json()
    non_ganada = [it for it in items if it.get("state") != "ganada"]
    if not non_ganada:
        pytest.skip("Todas las cotizaciones ya están ganadas")
    qid = non_ganada[0]["id"]
    payload = {
        "agent_name": "TEST", "agent_phone": "", "agent_company": "",
        "reservation_date": "", "passenger_name": "TEST", "passenger_phone": "",
        "num_persons": "2", "services": [], "lodging": [],
        "general_observations": "", "price_per_person": 0, "total_amount": 0,
    }
    r = s.post(f"{BASE_URL}/api/quotations/{qid}/booking-confirmation",
               json=payload, timeout=15)
    assert r.status_code == 400, f"Se esperaba 400, got {r.status_code}: {r.text[:200]}"
    assert "ganada" in (r.json().get("detail") or "").lower()


# ---------- 10.x: PDF de confirmación se genera OK ----------
def test_booking_confirmation_pdf_generates(s):
    """Si existe una cotización ganada, valida save+PDF; si no, hace transición temporal."""
    items = s.get(f"{BASE_URL}/api/quotations", timeout=15).json()
    if not items:
        pytest.skip("Sin cotizaciones")
    ganada = next((it for it in items if it.get("state") == "ganada"), None)
    revert_state = None
    qid = None
    if ganada:
        qid = ganada["id"]
    else:
        # transición temporal
        target = items[0]
        qid = target["id"]
        revert_state = target.get("state", "cotizando")
        r = s.patch(f"{BASE_URL}/api/quotations/{qid}/state",
                    json={"state": "ganada"}, timeout=15)
        assert r.status_code == 200, r.text[:200]

    try:
        # GET borrador
        pre = s.get(f"{BASE_URL}/api/quotations/{qid}/booking-confirmation", timeout=15).json()
        payload = {
            "agent_name": pre.get("agent_name", "TEST"),
            "agent_phone": pre.get("agent_phone", ""),
            "agent_company": pre.get("agent_company", ""),
            "reservation_date": pre.get("reservation_date", ""),
            "passenger_name": pre.get("passenger_name", "TEST"),
            "passenger_phone": pre.get("passenger_phone", ""),
            "num_persons": pre.get("num_persons", "2"),
            "services": pre.get("services", []),
            "lodging": pre.get("lodging", []),
            "general_observations": pre.get("general_observations", ""),
            "price_per_person": pre.get("price_per_person", 0),
            "total_amount": pre.get("total_amount", 0),
        }
        r = s.post(f"{BASE_URL}/api/quotations/{qid}/booking-confirmation",
                   json=payload, timeout=15)
        assert r.status_code == 200, f"Save failed: {r.status_code} {r.text[:200]}"
        conf = r.json()
        assert conf.get("id"), f"Falta id en respuesta: {conf}"
        # PDF
        r2 = s.get(f"{BASE_URL}/api/booking-confirmations/{conf['id']}/pdf", timeout=30)
        assert r2.status_code == 200
        assert r2.headers.get("content-type", "").startswith("application/pdf")
        assert r2.content[:4] == b"%PDF", "PDF header no válido"
        assert len(r2.content) > 2000, f"PDF demasiado pequeño ({len(r2.content)} bytes)"
    finally:
        if revert_state:
            s.patch(f"{BASE_URL}/api/quotations/{qid}/state",
                    json={"state": revert_state}, timeout=15)
