"""Iteration 66 — Confirmación de Reserva multi-hotel + Ejecutivo de agencia +
nombre completo cliente en enlace público + formato DD/Mmm/AA en PDF.

Cubre:
- BUG1: personalizado con 2 hoteles => prefill lodging con 2 hoteles; _expected.lodging
        lista 2 hoteles; refresh-amounts sincroniza los 2 conservando confirmation_number.
- BUG1 regresión paquete: cotización paquete sigue devolviendo un solo hotel.
- BUG2: agente de la agencia en Datos generales (executive_id -> client.executives),
        no created_by. Para cliente 'directo' usa datos del cliente.
- BUG3: nombre completo del cliente en GET /api/public/quotations/{token} (no split).
- AJUSTE4: PDF confirmación devuelve 200 application/pdf y contiene fechas DD/Mmm/AA.
- Verificación unitaria de _fmt_date('2026-09-26') == '26/Sep/26'.
"""
import os
import time
import re
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


# ---------------------------------------------------------------------------
# Helpers de creación / limpieza
# ---------------------------------------------------------------------------
def _mk_client(api, *, agency=False, exec_name="Ana Agente"):
    suf = str(int(time.time() * 1000))[-7:]
    name = f"TEST_ITER66_{'AG' if agency else 'DIR'}_{suf}"
    payload = {
        "name": name if not agency else "Mex Inca Viajes",
        "email": f"iter66_{suf}@test.mx",
        "phone": "3311110000",
        "channel": "agencia" if agency else "directo",
    }
    if agency:
        payload["executives"] = [{"name": exec_name, "email": f"exec_{suf}@ag.mx", "phone": "3399999999"}]
    r = api.post(f"{BASE_URL}/api/clients", json=payload)
    assert r.status_code in (200, 201), r.text
    return r.json()


def _mk_quotation_personalizado_2hotels(api, client_id, executive_id=None):
    payload = {
        "type": "personalizado",
        "client_id": client_id,
        "custom_title": "Programa Multi-hotel",
        "custom_items": [
            {"category": "hospedaje", "name": "Hotel 1",
             "checkin": "2026-01-01", "checkout": "2026-01-03", "nights": 2,
             "ocupacion": "doble", "net_price": 3000, "price_type": "neto",
             "unit": "per_person", "qty": 2},
            {"category": "hospedaje", "name": "Hotel 2",
             "checkin": "2026-01-03", "checkout": "2026-01-08", "nights": 5,
             "ocupacion": "triple", "net_price": 4000, "price_type": "neto",
             "unit": "per_person", "qty": 3},
            {"category": "extra", "name": "Grupo VIP",
             "net_price": 5000, "price_type": "neto", "unit": "per_group", "qty": 1},
        ],
        "pax": {"adultos": 2, "menores": 0, "ocupacion": "doble",
                "rooms": [{"ocupacion": "doble", "count": 1}]},
    }
    if executive_id:
        payload["executive_id"] = executive_id
    r = api.post(f"{BASE_URL}/api/quotations", json=payload)
    assert r.status_code in (200, 201), r.text
    return r.json()


def _mk_quotation_paquete(api, client_id):
    pkgs = api.get(f"{BASE_URL}/api/packages").json()
    assert isinstance(pkgs, list) and pkgs, "sin paquetes en tenant"
    pkg = pkgs[0]
    hotel = (pkg.get("hotels") or [{}])[0]
    payload = {
        "type": "paquete",
        "client_id": client_id,
        "package_id": pkg["id"],
        "hotel_name": hotel.get("name", ""),
        "dates": {"start": "2026-06-10", "end": "2026-06-13"},
        "pax": {"adultos": 2, "menores": 0, "ocupacion": "doble",
                "rooms": [{"ocupacion": "doble", "count": 1}]},
    }
    r = api.post(f"{BASE_URL}/api/quotations", json=payload)
    assert r.status_code in (200, 201), r.text
    return r.json()


def _cleanup(api, quotation_id=None, client_id=None):
    for url in filter(None, [
        f"{BASE_URL}/api/quotations/{quotation_id}" if quotation_id else None,
        f"{BASE_URL}/api/clients/{client_id}" if client_id else None,
    ]):
        try:
            api.delete(url)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Unit: _fmt_date directo (import backend)
# ---------------------------------------------------------------------------
def test_fmt_date_produces_dd_mmm_aa():
    import sys
    sys.path.insert(0, "/app/backend")
    from pdf_generator import _fmt_date
    assert _fmt_date("2026-09-26") == "26/Sep/26"
    assert _fmt_date("2026-01-01") == "01/Ene/26"
    assert _fmt_date("") == ""


# ---------------------------------------------------------------------------
# BUG1: personalizado 2 hoteles - prefill + save + _expected + refresh
# ---------------------------------------------------------------------------
def test_personalizado_2_hotels_full_flow(api_client):
    cl = _mk_client(api_client, agency=False)
    q = _mk_quotation_personalizado_2hotels(api_client, cl["id"])
    qid = q["id"]
    try:
        # ganada
        r = api_client.patch(f"{BASE_URL}/api/quotations/{qid}/state", json={"state": "ganada"})
        assert r.status_code in (200, 204), r.text

        # 1) prefill (draft) debe listar 2 hoteles
        draft = api_client.get(f"{BASE_URL}/api/quotations/{qid}/booking-confirmation").json()
        assert draft.get("_prefill") is True
        lodging = draft.get("lodging") or []
        assert len(lodging) == 2, f"expected 2 hoteles en prefill, got {len(lodging)}: {lodging}"
        assert lodging[0]["hotel"] == "Hotel 1"
        assert lodging[0]["checkin"] == "2026-01-01"
        assert lodging[0]["checkout"] == "2026-01-03"
        assert lodging[0]["room_type"] == "Doble"
        assert lodging[1]["hotel"] == "Hotel 2"
        assert lodging[1]["checkin"] == "2026-01-03"
        assert lodging[1]["checkout"] == "2026-01-08"
        assert lodging[1]["room_type"] == "Triple"

        # 2) guardar la confirmación con datos por-fila conservables
        lodging_payload = [
            {**lodging[0], "confirmation_number": "H1-ABC", "guest_name": "Pepito Perez", "plan": "EP"},
            {**lodging[1], "confirmation_number": "H2-XYZ", "guest_name": "Pepito Perez", "plan": "AI"},
        ]
        payload = {
            "agent_name": draft.get("agent_name", ""),
            "agent_phone": draft.get("agent_phone", ""),
            "agent_company": draft.get("agent_company", ""),
            "agent_email": draft.get("agent_email", ""),
            "reservation_date": draft.get("reservation_date", "2026-01-15"),
            "passenger_name": draft.get("passenger_name", "Pepito Perez"),
            "passenger_phone": draft.get("passenger_phone", ""),
            "num_persons": draft.get("num_persons", "2"),
            "services": draft.get("services", []),
            "lodging": lodging_payload,
            "itinerary": draft.get("itinerary", []),
            "general_observations": "",
            "price_per_person": draft["price_per_person"],
            "total_amount": draft["total_amount"],
        }
        r = api_client.post(f"{BASE_URL}/api/quotations/{qid}/booking-confirmation", json=payload)
        assert r.status_code in (200, 201), r.text
        conf = r.json()
        assert len(conf["lodging"]) == 2
        assert conf["lodging"][0]["confirmation_number"] == "H1-ABC"

        # 3) GET debe exponer _expected.lodging con los 2 hoteles y SIN falso desfase
        got = api_client.get(f"{BASE_URL}/api/quotations/{qid}/booking-confirmation").json()
        assert "_expected" in got, f"keys={list(got.keys())}"
        exp_lod = got["_expected"].get("lodging") or []
        assert len(exp_lod) == 2, f"_expected.lodging debe tener 2 hoteles, got {exp_lod}"
        # cada hotel expected coincide con el guardado
        for i in (0, 1):
            for k in ("hotel", "checkin", "checkout", "room_type"):
                assert exp_lod[i][k] == got["lodging"][i][k], (
                    f"desfase falso en hotel {i} campo {k}: expected={exp_lod[i][k]} saved={got['lodging'][i][k]}"
                )

        # 4) refresh-amounts sincroniza los 2 hoteles y conserva confirmation_number/guest_name/plan
        rf = api_client.post(f"{BASE_URL}/api/quotations/{qid}/booking-confirmation/refresh-amounts")
        assert rf.status_code == 200, rf.text
        upd = rf.json()
        assert len(upd["lodging"]) == 2
        assert upd["lodging"][0]["confirmation_number"] == "H1-ABC"
        assert upd["lodging"][0]["guest_name"] == "Pepito Perez"
        assert upd["lodging"][0]["plan"] == "EP"
        assert upd["lodging"][1]["confirmation_number"] == "H2-XYZ"
        assert upd["lodging"][1]["plan"] == "AI"
        assert upd["lodging"][0]["hotel"] == "Hotel 1"
        assert upd["lodging"][1]["hotel"] == "Hotel 2"

        # 5) PDF válido con application/pdf 200
        pdfr = api_client.get(f"{BASE_URL}/api/booking-confirmations/{conf['id']}/pdf")
        assert pdfr.status_code == 200, pdfr.text[:200]
        assert "application/pdf" in pdfr.headers.get("content-type", "")
        assert pdfr.content[:4] == b"%PDF"
        # Extraer texto del PDF y buscar formato DD/Mmm/AA
        import io as _io
        try:
            import pdfplumber
            with pdfplumber.open(_io.BytesIO(pdfr.content)) as pdf:
                text = "\n".join((p.extract_text() or "") for p in pdf.pages)
        except Exception:
            from pypdf import PdfReader
            reader = PdfReader(_io.BytesIO(pdfr.content))
            text = "\n".join((p.extract_text() or "") for p in reader.pages)
        assert "01/Ene/26" in text, f"PDF no contiene 01/Ene/26. muestra:\n{text[:800]}"
        assert "08/Ene/26" in text, f"PDF no contiene 08/Ene/26. muestra:\n{text[:800]}"
        assert "2026-01-01" not in text, "PDF sigue mostrando fecha cruda 2026-01-01"
    finally:
        _cleanup(api_client, qid, cl["id"])


# ---------------------------------------------------------------------------
# BUG1 regresión — paquete sigue con 1 hotel
# ---------------------------------------------------------------------------
def test_paquete_single_hotel_regression(api_client):
    cl = _mk_client(api_client, agency=False)
    q = _mk_quotation_paquete(api_client, cl["id"])
    qid = q["id"]
    try:
        api_client.patch(f"{BASE_URL}/api/quotations/{qid}/state", json={"state": "ganada"})
        draft = api_client.get(f"{BASE_URL}/api/quotations/{qid}/booking-confirmation").json()
        lod = draft.get("lodging") or []
        assert len(lod) == 1, f"paquete debe tener 1 hotel, got {len(lod)}"
        # Guardar y verificar _expected.lodging con 1 elemento
        payload = {
            **{k: draft.get(k, "") for k in ("agent_name", "agent_phone", "agent_company", "agent_email",
                                              "reservation_date", "passenger_name", "passenger_phone",
                                              "num_persons")},
            "services": draft.get("services", []),
            "lodging": lod, "itinerary": draft.get("itinerary", []),
            "general_observations": "",
            "price_per_person": draft["price_per_person"], "total_amount": draft["total_amount"],
        }
        r = api_client.post(f"{BASE_URL}/api/quotations/{qid}/booking-confirmation", json=payload)
        assert r.status_code in (200, 201), r.text
        got = api_client.get(f"{BASE_URL}/api/quotations/{qid}/booking-confirmation").json()
        assert len(got["_expected"]["lodging"]) == 1
    finally:
        _cleanup(api_client, qid, cl["id"])


# ---------------------------------------------------------------------------
# BUG2 — agente de agencia (executive_id -> client.executives), no created_by
# ---------------------------------------------------------------------------
def test_agent_from_agency_executive_not_created_by(api_client):
    cl = _mk_client(api_client, agency=True, exec_name="Ana Agente")
    exec_id = cl["executives"][0]["id"]
    q = _mk_quotation_personalizado_2hotels(api_client, cl["id"], executive_id=exec_id)
    qid = q["id"]
    try:
        api_client.patch(f"{BASE_URL}/api/quotations/{qid}/state", json={"state": "ganada"})
        draft = api_client.get(f"{BASE_URL}/api/quotations/{qid}/booking-confirmation").json()
        # El agent debe ser el ejecutivo de la agencia, NO el admin Routiq
        assert draft.get("agent_name") == "Ana Agente", f"agent_name={draft.get('agent_name')}"
        assert "admin" not in (draft.get("agent_email") or "").lower(), draft.get("agent_email")
        assert draft.get("agent_email", "").startswith("exec_"), draft.get("agent_email")
        assert draft.get("agent_phone") == "3399999999"
        # agent_company = nombre de la agencia (client.name)
        assert draft.get("agent_company") == "Mex Inca Viajes"
    finally:
        _cleanup(api_client, qid, cl["id"])


def test_agent_direct_client_uses_client_data(api_client):
    cl = _mk_client(api_client, agency=False)
    q = _mk_quotation_personalizado_2hotels(api_client, cl["id"])
    qid = q["id"]
    try:
        api_client.patch(f"{BASE_URL}/api/quotations/{qid}/state", json={"state": "ganada"})
        draft = api_client.get(f"{BASE_URL}/api/quotations/{qid}/booking-confirmation").json()
        # Directo => agent = datos del cliente; agent_company = empresa (Routiq tenant)
        assert draft.get("agent_name") == cl["name"], f"agent_name={draft.get('agent_name')} vs {cl['name']}"
        assert draft.get("agent_email") == cl["email"]
        # agent_company debe ser la empresa (Aventúrate por Jalisco) NO el cliente
        assert draft.get("agent_company") and draft.get("agent_company") != cl["name"]
    finally:
        _cleanup(api_client, qid, cl["id"])


# ---------------------------------------------------------------------------
# BUG3 — nombre completo del cliente en el enlace público (no split)
# ---------------------------------------------------------------------------
def test_public_quotation_full_client_name(api_client):
    cl = _mk_client(api_client, agency=True, exec_name="Ana Agente")
    q = _mk_quotation_personalizado_2hotels(api_client, cl["id"], executive_id=cl["executives"][0]["id"])
    qid = q["id"]
    try:
        # publicar/generar enlace público
        r = api_client.post(f"{BASE_URL}/api/quotations/{qid}/public-link")
        assert r.status_code in (200, 201), r.text
        token = r.json().get("token")
        assert token, f"sin token en publish: {r.json()}"
        pub = requests.get(f"{BASE_URL}/api/public/quotations/{token}")
        assert pub.status_code == 200, pub.text[:200]
        data = pub.json()
        # El nombre completo del cliente debe estar disponible como "Mex Inca Viajes"
        cname = data.get("quotation", {}).get("client_name") or data.get("client_name", "")
        assert cname == "Mex Inca Viajes", f"esperado nombre completo, got '{cname}'"
    finally:
        _cleanup(api_client, qid, cl["id"])


# ---------------------------------------------------------------------------
# AJUSTE4 — PDF de cotización (no confirmación) sigue generando 200
# ---------------------------------------------------------------------------
def test_quotation_pdf_still_ok(api_client):
    cl = _mk_client(api_client, agency=False)
    q = _mk_quotation_personalizado_2hotels(api_client, cl["id"])
    qid = q["id"]
    try:
        r = api_client.get(f"{BASE_URL}/api/quotations/{qid}/pdf")
        assert r.status_code == 200, r.text[:200]
        assert "application/pdf" in r.headers.get("content-type", "")
        assert r.content[:4] == b"%PDF"
    finally:
        _cleanup(api_client, qid, cl["id"])
