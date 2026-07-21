"""Iteration 56 — Verifica el BUG P0 del PDF/página de Confirmación de Reserva:
- GET /api/quotations/{id}/booking-confirmation expone `_expected` recalculado.
- POST /api/quotations/{id}/booking-confirmation/refresh-amounts actualiza montos + lodging[0]
  conservando confirmation_number/guest_name/plan.
- La actualización agrega history entry action='confirmation_updated'.
- E2E: crear cotización -> ganada -> confirmación -> cambiar precio -> _expected difiere ->
  refresh -> quedan iguales."""
import os
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
ADMIN_EMAIL = "admin@aventurate.mx"
ADMIN_PASSWORD = "Demo2026!"


@pytest.fixture(scope="module")
def api_client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    yield s


def _make_quotation(api_client):
    """Crea una cotización de tipo paquete usando el primer paquete disponible."""
    # Buscar un paquete existente
    pkgs = api_client.get(f"{BASE_URL}/api/packages").json()
    assert isinstance(pkgs, list) and len(pkgs) > 0, "No hay paquetes en el tenant"
    pkg = pkgs[0]
    # Crear cliente
    suf = str(int(time.time() * 1000))[-6:]
    cl = api_client.post(f"{BASE_URL}/api/clients", json={
        "name": f"TEST_ITER56_{suf}", "email": f"iter56_{suf}@test.mx", "phone": "3300000000"
    })
    assert cl.status_code in (200, 201), cl.text
    client_id = cl.json()["id"]

    # Crear cotización paquete
    hotel = (pkg.get("hotels") or [{}])[0]
    hotel_name = hotel.get("name") or "Hotel Demo"
    payload = {
        "type": "paquete",
        "client_id": client_id,
        "package_id": pkg["id"],
        "hotel_name": hotel_name,
        "dates": {"start": "2026-06-10", "end": "2026-06-13"},
        "pax": {"adultos": 2, "menores": 0, "ocupacion": "doble",
                "rooms": [{"ocupacion": "doble", "count": 1}]},
    }
    r = api_client.post(f"{BASE_URL}/api/quotations", json=payload)
    assert r.status_code in (200, 201), r.text
    q = r.json()
    return q, client_id


def _cleanup(api_client, quotation_id, client_id):
    try:
        api_client.delete(f"{BASE_URL}/api/quotations/{quotation_id}")
    except Exception:
        pass
    try:
        api_client.delete(f"{BASE_URL}/api/clients/{client_id}")
    except Exception:
        pass


# ---------------------------------------------------------------------------
# TEST 1: _expected en GET (draft prellenado — sin confirmación guardada aún)
# ---------------------------------------------------------------------------
def test_get_booking_confirmation_returns_prefill(api_client):
    q, cid = _make_quotation(api_client)
    try:
        r = api_client.get(f"{BASE_URL}/api/quotations/{q['id']}/booking-confirmation")
        assert r.status_code == 200, r.text
        data = r.json()
        # No hay confirmación guardada => _prefill=True y NO tiene _expected (documented)
        assert data.get("_prefill") is True
        assert "total_amount" in data
    finally:
        _cleanup(api_client, q["id"], cid)


# ---------------------------------------------------------------------------
# TEST 2 + 3 + 4 (E2E completo): crear -> ganar -> confirmación -> desfase -> refresh
# ---------------------------------------------------------------------------
def test_e2e_mismatch_refresh_and_history(api_client):
    q, cid = _make_quotation(api_client)
    qid = q["id"]
    try:
        # 1) Marcar como ganada
        r = api_client.patch(f"{BASE_URL}/api/quotations/{qid}/state", json={"state": "ganada"})
        assert r.status_code in (200, 204), r.text

        # 2) Obtener draft prefilled y guardar la confirmación con esos valores
        draft = api_client.get(f"{BASE_URL}/api/quotations/{qid}/booking-confirmation").json()
        assert draft.get("_prefill") is True
        original_total = draft["total_amount"]
        original_pp = draft["price_per_person"]

        # Guardar confirmación
        payload = {
            "agent_name": draft.get("agent_name", ""),
            "agent_phone": draft.get("agent_phone", ""),
            "agent_company": draft.get("agent_company", ""),
            "agent_email": draft.get("agent_email", ""),
            "reservation_date": draft.get("reservation_date", "2026-01-15"),
            "passenger_name": draft.get("passenger_name", "Test Pasajero"),
            "passenger_phone": draft.get("passenger_phone", ""),
            "num_persons": draft.get("num_persons", "2"),
            "services": draft.get("services", []),
            "lodging": [
                {**(draft.get("lodging") or [{}])[0],
                 "confirmation_number": "CONFIRM-123",
                 "guest_name": "Huésped VIP",
                 "plan": "Todo incluido"}
            ] if draft.get("lodging") else [],
            "itinerary": draft.get("itinerary", []),
            "general_observations": "obs",
            "price_per_person": original_pp,
            "total_amount": original_total,
        }
        r = api_client.post(f"{BASE_URL}/api/quotations/{qid}/booking-confirmation", json=payload)
        assert r.status_code in (200, 201), r.text
        conf = r.json()
        assert conf["total_amount"] == original_total
        assert conf["lodging"][0]["confirmation_number"] == "CONFIRM-123"

        # 3) Sin cambios: GET debe devolver _expected == valores guardados
        got = api_client.get(f"{BASE_URL}/api/quotations/{qid}/booking-confirmation").json()
        assert "_expected" in got, f"El endpoint no expone _expected: keys={list(got.keys())}"
        assert abs(float(got["_expected"]["total_amount"]) - float(original_total)) < 0.01

        # 4) Cambiar el precio de la cotización aplicando un descuento
        # Endpoint: PATCH /api/quotations/{id}/pricing-adjust  (Iter3, ya existente)
        adj = api_client.patch(f"{BASE_URL}/api/quotations/{qid}/pricing-adjust", json={
            "discount_type": "percent", "discount_value": 10
        })
        assert adj.status_code in (200, 204), f"pricing-adjust falló: {adj.status_code} {adj.text}"

        # 5) GET confirmation ahora debe mostrar desfase
        got2 = api_client.get(f"{BASE_URL}/api/quotations/{qid}/booking-confirmation").json()
        assert "_expected" in got2
        exp = got2["_expected"]
        saved_total = got2["total_amount"]
        assert abs(float(exp["total_amount"]) - float(saved_total)) > 0.01, \
            f"Se esperaba desfase pero _expected={exp['total_amount']} == saved={saved_total}"
        new_expected_total = exp["total_amount"]

        # 6) Llamar refresh-amounts
        rf = api_client.post(f"{BASE_URL}/api/quotations/{qid}/booking-confirmation/refresh-amounts")
        assert rf.status_code == 200, rf.text
        updated = rf.json()
        assert abs(float(updated["total_amount"]) - float(new_expected_total)) < 0.01
        # Conservar confirmation_number, guest_name, plan
        if updated.get("lodging"):
            assert updated["lodging"][0].get("confirmation_number") == "CONFIRM-123"
            assert updated["lodging"][0].get("guest_name") == "Huésped VIP"
            assert updated["lodging"][0].get("plan") == "Todo incluido"

        # 7) GET debe ya no mostrar desfase
        got3 = api_client.get(f"{BASE_URL}/api/quotations/{qid}/booking-confirmation").json()
        assert abs(float(got3["_expected"]["total_amount"]) - float(got3["total_amount"])) < 0.01

        # 8) Verificar historial: action='confirmation_updated'
        qfull = api_client.get(f"{BASE_URL}/api/quotations/{qid}").json()
        history = qfull.get("history") or []
        actions = [h.get("action") for h in history]
        assert "confirmation_updated" in actions, f"history actions={actions}"
        # Verificar que el detalle menciona monto
        entry = [h for h in history if h.get("action") == "confirmation_updated"][-1]
        assert "$" in (entry.get("detail") or "") or "monto" in (entry.get("detail") or "").lower()
    finally:
        _cleanup(api_client, qid, cid)


# ---------------------------------------------------------------------------
# TEST 5: refresh-amounts sobre cotización sin confirmación -> 404
# ---------------------------------------------------------------------------
def test_refresh_without_confirmation_returns_404(api_client):
    q, cid = _make_quotation(api_client)
    try:
        api_client.patch(f"{BASE_URL}/api/quotations/{q['id']}/state", json={"state": "ganada"})
        r = api_client.post(f"{BASE_URL}/api/quotations/{q['id']}/booking-confirmation/refresh-amounts")
        assert r.status_code == 404
    finally:
        _cleanup(api_client, q["id"], cid)


# ---------------------------------------------------------------------------
# TEST 6: refresh-amounts sobre quotation_id inválido -> 404
# ---------------------------------------------------------------------------
def test_refresh_invalid_quotation_returns_404(api_client):
    r = api_client.post(f"{BASE_URL}/api/quotations/does-not-exist-xyz/booking-confirmation/refresh-amounts")
    assert r.status_code == 404
