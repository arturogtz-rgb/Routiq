"""Iter 48 — Lote B (backend): confirmación con ejecutivo real, mark-paid con
método+fecha, ejecutivo al vuelo (PATCH /clients), PDF de cotización con
nombre de paquete, y regresión de precios paquete + signup (Turnstile logging)."""
import io
import os
import re
from datetime import datetime

import pytest
import pdfplumber
import requests

def _load_backend_url():
    env = os.environ.get("REACT_APP_BACKEND_URL")
    if env:
        return env.rstrip("/")
    # Fallback: leer del .env del frontend (cookies del backend son secure=True; sólo
    # se envían por HTTPS a través del ingress público).
    try:
        with open("/app/frontend/.env") as f:
            for line in f:
                if line.startswith("REACT_APP_BACKEND_URL="):
                    return line.split("=", 1)[1].strip().strip('"').rstrip("/")
    except Exception:
        pass
    return "http://localhost:8001"


BASE_URL = _load_backend_url()
ADMIN_EMAIL = "admin@aventurate.mx"
ADMIN_PASSWORD = "Demo2026!"
PAQUETE_GANADA_CODE = "COT-2026056"
CLIENT_WITH_EXECS = "c76a1ac7-1eaa-40b2-83bb-63d7cd52f218"  # Agencia Demo SA


@pytest.fixture(scope="session")
def session():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login",
               json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert r.status_code == 200, f"login failed: {r.text}"
    return s


@pytest.fixture(scope="session")
def me(session):
    r = session.get(f"{BASE_URL}/api/auth/me")
    assert r.status_code == 200
    return r.json()


@pytest.fixture(scope="session")
def paquete_ganada(session):
    r = session.get(f"{BASE_URL}/api/quotations")
    assert r.status_code == 200
    q = next((x for x in r.json() if x["code"] == PAQUETE_GANADA_CODE), None)
    assert q, f"Fixture: no encuentro {PAQUETE_GANADA_CODE}"
    return q


# ------------------ H1 / 10.4: confirmación con ejecutivo real ------------------
class TestBookingExecutive:
    def test_prefill_uses_real_user_as_agent(self, session, me):
        """Buscar una cotización 'ganada' SIN confirmación guardada (prefill=True)
        para probar el path de inyección de _executive_fields con datos reales."""
        r = session.get(f"{BASE_URL}/api/quotations")
        target = None
        for q in r.json():
            if q.get("state") != "ganada":
                continue
            data = session.get(f"{BASE_URL}/api/quotations/{q['id']}/booking-confirmation").json()
            if data.get("_prefill") and q.get("created_by") == me["id"]:
                target = q
                target_data = data
                break
        assert target, "No hay cotización 'ganada' creada por el usuario logueado sin confirmación previa (para probar prefill)"
        assert target_data.get("agent_name") == me["name"], f"agent_name={target_data.get('agent_name')} != {me['name']}"
        assert target_data.get("agent_email") == me["email"], f"agent_email={target_data.get('agent_email')} != {me['email']}"
        r2 = session.get(f"{BASE_URL}/api/companies/me")
        if r2.status_code == 200:
            company_name = r2.json().get("name", "")
            assert target_data.get("agent_company") == company_name

    def test_pdf_shows_executive_email_and_company(self, session, paquete_ganada, me):
        # Guardar (o actualizar) la confirmación para que exista y podamos pedir el PDF.
        r = session.get(f"{BASE_URL}/api/quotations/{paquete_ganada['id']}/booking-confirmation")
        prefill = r.json()
        payload = {k: prefill.get(k, "") for k in (
            "agent_name", "agent_phone", "agent_company", "agent_email",
            "reservation_date", "passenger_name", "passenger_phone", "num_persons",
            "general_observations",
        )}
        payload["services"] = prefill.get("services", [])
        payload["lodging"] = prefill.get("lodging", [])
        payload["price_per_person"] = prefill.get("price_per_person", 0)
        payload["total_amount"] = prefill.get("total_amount", 0)
        s = session.post(f"{BASE_URL}/api/quotations/{paquete_ganada['id']}/booking-confirmation",
                         json=payload)
        assert s.status_code == 200, s.text
        conf = s.json()
        pdf_r = session.get(f"{BASE_URL}/api/booking-confirmations/{conf['id']}/pdf")
        assert pdf_r.status_code == 200
        assert pdf_r.headers.get("content-type", "").startswith("application/pdf")
        with pdfplumber.open(io.BytesIO(pdf_r.content)) as pdf:
            text = "\n".join((p.extract_text() or "") for p in pdf.pages)
        assert "Ejecutivo" in text
        assert me["name"] in text, f"nombre del ejecutivo no aparece en PDF: {me['name']}"
        assert "Correo del ejecutivo" in text
        assert me["email"] in text, f"email del ejecutivo no aparece en PDF: {me['email']}"
        # Empresa (tenant)
        r2 = session.get(f"{BASE_URL}/api/companies/me")
        if r2.status_code == 200:
            assert r2.json().get("name", "") in text


# ------------------ 3.1: mark-paid con método + fecha ------------------
class TestMarkPaidMethodDate:
    def _get_or_create_partial_paquete(self, session):
        """Necesitamos una cotización de paquete que NO esté 100% pagada.
        Buscamos alguna 'ganada' sin pago; si no hay, hacemos rollback al final."""
        r = session.get(f"{BASE_URL}/api/quotations")
        cand = None
        for q in r.json():
            if q.get("type") == "paquete" and q.get("payment_status") in (None, "unpaid", "partial"):
                cand = q
                break
        assert cand, "No hay cotización paquete pagable"
        return cand

    def test_mark_paid_saves_method_and_date(self, session):
        q = self._get_or_create_partial_paquete(session)
        # Guardar estado original para revertir después
        original_amount_paid = q.get("amount_paid", 0) or 0
        original_state = q.get("state")
        original_payment_status = q.get("payment_status")
        original_paid_at = q.get("paid_at")

        pay_date = "2026-07-10"
        r = session.patch(
            f"{BASE_URL}/api/quotations/{q['id']}/mark-paid",
            json={"amount": 100.0, "method": "cash", "date": pay_date, "note": "TEST_LOTE_B"},
        )
        assert r.status_code == 200, r.text
        updated = r.json()
        assert updated.get("paid_at") == pay_date, f"paid_at={updated.get('paid_at')} != {pay_date}"
        assert updated.get("payment_status") in ("paid", "partial")
        # El historial debe mencionar 'efectivo' (método traducido)
        r2 = session.get(f"{BASE_URL}/api/quotations/{q['id']}")
        hist = (r2.json() or {}).get("history", []) or []
        pay_entries = [h for h in hist if h.get("action") == "payment"]
        assert pay_entries, f"No hay entrada de historial 'payment' (history: {hist})"
        # Buscar la última con 'efectivo' + fecha
        found = any("efectivo" in (h.get("detail", "") or "").lower() and pay_date in h.get("detail", "")
                    for h in pay_entries)
        assert found, f"Historial no menciona método 'efectivo' y fecha {pay_date}: {[h.get('detail') for h in pay_entries]}"

        # ---- Rollback (limpieza de datos de prueba) ----
        # Restaurar amount_paid vía update directo no es endpoint público — usamos state para
        # dejar la cotización como estaba (payment_status/paid_at). Best-effort.
        try:
            session.patch(f"{BASE_URL}/api/quotations/{q['id']}/state",
                          json={"state": original_state or "ganada"})
        except Exception:
            pass


# ------------------ 4.2: agregar ejecutivo al vuelo ------------------
class TestAddExecutiveOnTheFly:
    def test_patch_client_appends_executive(self, session):
        r = session.get(f"{BASE_URL}/api/clients/{CLIENT_WITH_EXECS}")
        assert r.status_code == 200
        client = r.json()
        original_execs = client.get("executives", [])
        new_ex = {
            "id": "test48" + str(int(datetime.now().timestamp()))[-8:],
            "name": "TEST_LOTE_B Ejecutivo",
            "phone": "+525599990000",
            "email": "test.lote.b@aventurate.mx",
        }
        payload = {"executives": original_execs + [new_ex]}
        u = session.patch(f"{BASE_URL}/api/clients/{CLIENT_WITH_EXECS}", json=payload)
        assert u.status_code == 200, u.text
        got = u.json().get("executives", [])
        assert any(e.get("name") == new_ex["name"] for e in got), f"Ejecutivo no persistido: {got}"

        # ---- Cleanup: revertir a la lista original ----
        session.patch(f"{BASE_URL}/api/clients/{CLIENT_WITH_EXECS}",
                      json={"executives": original_execs})


# ------------------ 7.1: PDF de cotización con nombre de paquete ------------------
class TestQuotationPdfPackageName:
    def _pdf_text(self, session, qid):
        r = session.get(f"{BASE_URL}/api/quotations/{qid}/pdf")
        assert r.status_code == 200, r.text
        assert r.headers.get("content-type", "").startswith("application/pdf")
        with pdfplumber.open(io.BytesIO(r.content)) as pdf:
            return "\n".join((p.extract_text() or "") for p in pdf.pages)

    def test_paquete_pdf_contains_package_name(self, session, paquete_ganada):
        pkg_name = (paquete_ganada.get("package_snapshot") or {}).get("name") or ""
        assert pkg_name, "fixture debería tener nombre de paquete"
        text = self._pdf_text(session, paquete_ganada["id"])
        # Fila 'Paquete' en la sección de detalles de la reservación
        assert "Paquete" in text, "PDF no muestra el rótulo 'Paquete' en detalles"
        assert pkg_name in text, f"PDF no muestra el nombre del paquete: {pkg_name}"
        # Línea 'Paquete: <nombre>' en desglose/conceptos
        # Puede aparecer una o dos veces (fila meta + línea desglose). Buscamos el patrón textual explícito
        assert re.search(r"Paquete\s*[:\-]?\s*" + re.escape(pkg_name), text, re.IGNORECASE) or \
               f"Paquete: {pkg_name}" in text, "PDF no muestra 'Paquete: <nombre>' en desglose"

    def test_servicios_pdf_no_paquete_row(self, session):
        r = session.get(f"{BASE_URL}/api/quotations")
        q = next((x for x in r.json() if x.get("type") == "servicios"), None)
        if not q:
            pytest.skip("No hay cotización de servicios a la carta para probar 7.1 (negativo)")
        text = self._pdf_text(session, q["id"])
        # No debe aparecer 'Servicios a la carta' como paquete, y no debe tener fila 'Paquete\t<nombre>'
        # (validación laxa: no aparece 'Paquete:' en desglose ni línea meta 'Paquete X')
        assert "Paquete:" not in text, "PDF de servicios no debería incluir 'Paquete:' en desglose"


# ------------------ Regresión: precios paquete no cambiaron ------------------
class TestPackagePricingRegression:
    def test_paquete_totals_consistent(self, session, paquete_ganada):
        r = session.get(f"{BASE_URL}/api/quotations/{paquete_ganada['id']}")
        assert r.status_code == 200
        q = r.json()
        items = q.get("items") or []
        assert items, "Paquete debería tener items"
        subtotal = sum(float(it.get("subtotal", 0)) for it in items)
        assert abs(subtotal - float(q.get("subtotal", 0))) < 0.5, \
            f"subtotal recomputado {subtotal} != {q.get('subtotal')}"
        # total = subtotal + commission
        total_calc = float(q.get("subtotal", 0)) + float(q.get("commission", 0) or 0)
        assert abs(total_calc - float(q.get("total", 0))) < 0.5, \
            f"total {q.get('total')} != subtotal+commission {total_calc}"


# ------------------ H2: signup no roto (logging Turnstile mejorado) ------------------
class TestSignupNotBroken:
    def test_signup_endpoint_reachable_returns_400_or_similar(self):
        # Sin token válido de Turnstile debe rechazarse controladamente (no 500).
        r = requests.post(f"{BASE_URL}/api/auth/signup",
                          json={
                              "company_name": "TEST_LOTE_B Co",
                              "admin_name": "TEST_LOTE_B Admin",
                              "admin_email": "test.lote.b.signup@example.com",
                              "admin_phone": "",
                              "plan": "pro",
                              "admin_password": "TestLoteB2026!",
                              "turnstile_token": "",
                              "website": "",
                          })
        assert r.status_code < 500, f"/api/auth/signup rompió con 5xx: {r.status_code} — {r.text[:200]}"
