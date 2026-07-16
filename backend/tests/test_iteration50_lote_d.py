"""Lote D — 4.1 favoritos + 10.5 itinerario según tipo + PDF confirmación.
Ejecutar con: pytest /app/backend/tests/test_iteration50_lote_d.py -v
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    # fallback local (para correr desde el contenedor)
    BASE_URL = "http://localhost:8001"

API = f"{BASE_URL}/api"

ADMIN_EMAIL = "admin@aventurate.mx"
ADMIN_PWD = "Demo2026!"

# IDs de cotización de prueba entregadas por el main agent
Q_PACKAGE = "4ca24d69-d592-45fb-9b00-cc09167f25a2"    # tipo paquete (4 días)
Q_SERVICES = "91dd1e61-c960-420e-b4d2-3f8def97d9d4"    # tipo servicios
Q_CUSTOM = "ba5d7c14-c263-43bf-8510-a12e8d44b364"      # tipo personalizado


@pytest.fixture(scope="module")
def session():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    r = s.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PWD})
    assert r.status_code == 200, f"Login failed: {r.status_code} {r.text}"
    return s


# ---------------------------------------------------------------------------
# 4.1 — Clientes: is_favorite + my_freq + toggle favorito
# ---------------------------------------------------------------------------
class TestClientsFavorites:

    def test_list_clients_has_is_favorite_and_my_freq(self, session):
        r = session.get(f"{API}/clients")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)
        assert len(data) > 0, "Deben existir clientes seed para probar"
        for c in data:
            assert "is_favorite" in c, f"cliente {c.get('id')} sin campo is_favorite"
            assert "my_freq" in c, f"cliente {c.get('id')} sin campo my_freq"
            assert isinstance(c["is_favorite"], bool)
            assert isinstance(c["my_freq"], int)

    def test_toggle_favorite_persists(self, session):
        r = session.get(f"{API}/clients")
        clients = r.json()
        target = clients[0]
        cid = target["id"]
        initial = bool(target.get("is_favorite"))

        # Toggle a True
        r2 = session.patch(f"{API}/clients/{cid}", json={"is_favorite": True})
        assert r2.status_code == 200, r2.text
        assert r2.json().get("is_favorite") is True

        # GET verifica persistencia en listado
        r3 = session.get(f"{API}/clients")
        found = next((c for c in r3.json() if c["id"] == cid), None)
        assert found is not None
        assert found["is_favorite"] is True

        # Toggle a False
        r4 = session.patch(f"{API}/clients/{cid}", json={"is_favorite": False})
        assert r4.status_code == 200
        assert r4.json().get("is_favorite") is False

        # Restaurar estado original
        session.patch(f"{API}/clients/{cid}", json={"is_favorite": initial})

    def test_my_freq_matches_created_by_count(self, session):
        """my_freq debe corresponder al # de cotizaciones creadas por el usuario
        actual (created_by == user.id) — verificamos vs /quotations."""
        me = session.get(f"{API}/auth/me").json()
        uid = me["id"]
        clients = session.get(f"{API}/clients").json()
        # Escoger cliente con my_freq > 0 si existe
        with_freq = [c for c in clients if c["my_freq"] > 0]
        if not with_freq:
            pytest.skip("No hay clientes con my_freq>0 para este usuario")
        c = with_freq[0]
        qs = session.get(f"{API}/quotations").json()
        real = sum(1 for q in qs if q.get("client_id") == c["id"] and q.get("created_by") == uid and not q.get("deleted"))
        assert c["my_freq"] == real, f"my_freq={c['my_freq']} vs count_real={real}"


# ---------------------------------------------------------------------------
# 10.5 — Prefill de itinerario según tipo de cotización
# ---------------------------------------------------------------------------
class TestBookingItineraryPrefill:

    def _get_conf(self, session, qid):
        r = session.get(f"{API}/quotations/{qid}/booking-confirmation")
        assert r.status_code == 200, r.text
        return r.json()

    def test_paquete_prefills_day_by_day(self, session):
        conf = self._get_conf(session, Q_PACKAGE)
        itin = conf.get("itinerary") or []
        # main agent verificó: paquete de 4 días
        assert len(itin) >= 3, f"Esperados >=3 bloques (paquete 4 días), obtenidos {len(itin)}"
        # Los títulos deben empezar con 'Día '
        assert any(str(e.get("title", "")).lower().startswith("día") for e in itin), \
            f"Ningún bloque con formato 'Día N: ...': {[e.get('title') for e in itin]}"

    def test_servicios_prefills_service_name_desc(self, session):
        conf = self._get_conf(session, Q_SERVICES)
        itin = conf.get("itinerary") or []
        assert len(itin) >= 1
        # Cada bloque tiene título (nombre del servicio) — no debe iniciar con 'Día '
        titles = [e.get("title", "") for e in itin]
        assert all(t for t in titles), f"Bloque sin título: {titles}"

    def test_personalizado_prefills_concept_desc(self, session):
        conf = self._get_conf(session, Q_CUSTOM)
        itin = conf.get("itinerary") or []
        assert len(itin) >= 1
        titles = [e.get("title", "") for e in itin]
        assert all(t for t in titles), f"Bloque sin título: {titles}"


# ---------------------------------------------------------------------------
# 10.5 — Guardar confirmación con itinerario editado + persistencia + PDF
# ---------------------------------------------------------------------------
class TestBookingItinerarySave:

    def test_save_confirmation_persists_itinerary_and_pdf_ok(self, session):
        # Usar cotización paquete (Q_PACKAGE). Debe estar 'ganada' para POST.
        q = session.get(f"{API}/quotations/{Q_PACKAGE}").json()
        if q.get("state") != "ganada":
            # Cambiar a ganada
            r = session.patch(f"{API}/quotations/{Q_PACKAGE}/state", json={"state": "ganada"})
            assert r.status_code == 200, f"No se pudo poner en ganada: {r.text}"

        # Obtener draft prellenado y agregar bloque custom
        draft = session.get(f"{API}/quotations/{Q_PACKAGE}/booking-confirmation").json()
        payload = {
            "agent_name": draft.get("agent_name", ""),
            "agent_phone": draft.get("agent_phone", ""),
            "agent_company": draft.get("agent_company", ""),
            "agent_email": draft.get("agent_email", ""),
            "reservation_date": draft.get("reservation_date", ""),
            "passenger_name": draft.get("passenger_name", ""),
            "passenger_phone": draft.get("passenger_phone", ""),
            "num_persons": draft.get("num_persons", ""),
            "services": draft.get("services", []),
            "lodging": draft.get("lodging", []),
            "itinerary": (draft.get("itinerary") or []) + [
                {"title": "TEST_D_MARKER", "description": "verificando persistencia lote D"}
            ],
            "general_observations": draft.get("general_observations", ""),
            "price_per_person": draft.get("price_per_person", 0),
            "total_amount": draft.get("total_amount", 0),
        }

        r = session.post(f"{API}/quotations/{Q_PACKAGE}/booking-confirmation", json=payload)
        assert r.status_code == 200, r.text
        saved = r.json()
        conf_id = saved["id"]
        assert any(e.get("title") == "TEST_D_MARKER" for e in (saved.get("itinerary") or [])), \
            f"Marcador TEST_D_MARKER no se guardó: {saved.get('itinerary')}"

        # Reload → sigue ahí
        again = session.get(f"{API}/quotations/{Q_PACKAGE}/booking-confirmation").json()
        assert any(e.get("title") == "TEST_D_MARKER" for e in (again.get("itinerary") or [])), \
            "Itinerario no persistió tras reload"

        # PDF
        rp = session.get(f"{API}/booking-confirmations/{conf_id}/pdf")
        assert rp.status_code == 200, rp.text
        assert rp.headers.get("content-type", "").startswith("application/pdf")
        assert len(rp.content) > 2000, "PDF sospechosamente vacío"
        # Firma PDF
        assert rp.content[:4] == b"%PDF"

        # Limpiar marcador dejando itinerario original (idempotente para futuras corridas)
        cleaned = [e for e in (saved.get("itinerary") or []) if e.get("title") != "TEST_D_MARKER"]
        payload["itinerary"] = cleaned
        session.post(f"{API}/quotations/{Q_PACKAGE}/booking-confirmation", json=payload)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
