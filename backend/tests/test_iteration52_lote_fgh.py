"""
Iteración 52 — Lote F (WhatsApp), G (IA seguimiento), H (correcciones de cotizaciones).

Ámbito de pruebas:
  F6  → share/q y share/r con Open Graph por empresa
  F2  → GET /whatsapp/chats devuelve is_group/hidden/contact_name (CRM)
  F4  → POST /whatsapp/chats/hide persiste la preferencia
  G   → follow-up-prepay/postsale devuelven 503 BYOK (IA no configurada)
  G   → send-message envía correo al cliente (200 con to=email cliente)
  H1  → PATCH /quotations diff real + traducciones al español
  REGRESIÓN motor de precios → subtotal+commission == total (± 0.02)
"""
import os
import re
import pytest
import requests

def _load_backend_url():
    p = "/app/frontend/.env"
    if os.path.exists(p):
        for ln in open(p):
            if ln.startswith("REACT_APP_BACKEND_URL="):
                return ln.split("=", 1)[1].strip().rstrip("/")
    return os.environ["REACT_APP_BACKEND_URL"].rstrip("/")


BASE_URL = _load_backend_url()
ADMIN_EMAIL = "admin@aventurate.mx"
ADMIN_PASS = "Demo2026!"

QUO_PACKAGE = "4ca24d69-d592-45fb-9b00-cc09167f25a2"
QUO_CUSTOM = "ba5d7c14-c263-43bf-8510-a12e8d44b364"
QUO_SERVICES = "91dd1e61-c960-420e-b4d2-3f8def97d9d4"
WA_NUMBER_ID = "975c561c-b0ee-45f6-b59e-de2653d46f6f"


@pytest.fixture(scope="module")
def admin():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASS}, timeout=30)
    assert r.status_code == 200, r.text
    # Auth is cookie-based; session keeps cookies automatically
    r2 = s.get(f"{BASE_URL}/api/auth/me", timeout=30)
    assert r2.status_code == 200, f"auth/me failed: {r2.status_code} {r2.text}"
    return s


# ---------- F6: share/q Open Graph ----------
class TestShareOG:
    def _ensure_public_link(self, admin, qid):
        # crear public link si no existe
        r = admin.get(f"{BASE_URL}/api/quotations/{qid}", timeout=30)
        assert r.status_code == 200
        q = r.json()
        tok = (q.get("public_link") or {}).get("token")
        if not tok:
            r = admin.post(f"{BASE_URL}/api/quotations/{qid}/public-link", timeout=30)
            assert r.status_code in (200, 201), r.text
            tok = r.json()["token"]
        return tok

    def test_share_q_has_og_with_company(self, admin):
        tok = self._ensure_public_link(admin, QUO_PACKAGE)
        r = requests.get(f"{BASE_URL}/api/share/q/{tok}", timeout=30, allow_redirects=False)
        assert r.status_code == 200
        m = re.search(r'<meta property="og:title" content="([^"]+)"', r.text)
        assert m, f"og:title not present in HTML: {r.text[:400]}"
        og = m.group(1)
        # Should be '{Empresa} · Cotización {code}'
        assert "·" in og and "Cotización" in og, f"unexpected og:title: {og}"
        # sanity: redirect to /q/{token}
        assert f"/q/{tok}" in r.text

    def test_share_q_invalid_token_generic(self):
        r = requests.get(f"{BASE_URL}/api/share/q/nonexistent-xyz", timeout=30, allow_redirects=False)
        assert r.status_code == 200
        assert 'og:title' in r.text  # still has meta tags (generic)
        assert "/q/nonexistent-xyz" in r.text

    def test_share_r_confirmation_og(self, admin):
        # Buscar una cotización 'ganada' con confirmación, o generar una
        r = admin.get(f"{BASE_URL}/api/quotations", params={"state": "ganada"}, timeout=30)
        assert r.status_code == 200
        won = r.json()
        conf_token = None
        for q in won:
            r2 = admin.get(f"{BASE_URL}/api/quotations/{q['id']}/booking-confirmation", timeout=30)
            if r2.status_code == 200:
                data = r2.json()
                if data.get("token"):
                    conf_token = data["token"]
                    break
        if not conf_token:
            pytest.skip("No hay booking confirmation con token — endpoint testeado con token inválido a continuación")
        r = requests.get(f"{BASE_URL}/api/share/r/{conf_token}", timeout=30, allow_redirects=False)
        assert r.status_code == 200
        m = re.search(r'<meta property="og:title" content="([^"]+)"', r.text)
        assert m
        og = m.group(1)
        assert "Confirmación" in og and "·" in og, f"unexpected og:title: {og}"
        assert f"/r/{conf_token}" in r.text

    def test_share_r_invalid_generic(self):
        r = requests.get(f"{BASE_URL}/api/share/r/nonexistent-xyz", timeout=30, allow_redirects=False)
        assert r.status_code == 200
        m = re.search(r'<meta property="og:title" content="([^"]+)"', r.text)
        assert m
        # Genérico cuando token inválido
        assert "Confirmación de Reserva" in m.group(1) or "Confirmación" in m.group(1)


# ---------- F2/F4: WhatsApp chats + hide ----------
class TestWhatsAppChats:
    def test_list_chats_structure(self, admin):
        r = admin.get(f"{BASE_URL}/api/whatsapp/chats", params={"number_id": WA_NUMBER_ID}, timeout=30)
        assert r.status_code == 200
        chats = r.json()
        assert isinstance(chats, list)
        # si hay chats, validar estructura F2
        for c in chats:
            assert "is_group" in c and isinstance(c["is_group"], bool)
            assert "hidden" in c and isinstance(c["hidden"], bool)
            assert "contact_name" in c
            assert "chat_id" in c and "phone" in c

    def test_hide_chat_persists(self, admin):
        chat_id = "5213331234567@s.whatsapp.net"  # sintético — el endpoint hace upsert
        r = admin.post(f"{BASE_URL}/api/whatsapp/chats/hide", json={
            "number_id": WA_NUMBER_ID, "chat_id": chat_id, "hidden": True}, timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data == {"ok": True, "hidden": True}
        # unhide para dejar limpio
        r = admin.post(f"{BASE_URL}/api/whatsapp/chats/hide", json={
            "number_id": WA_NUMBER_ID, "chat_id": chat_id, "hidden": False}, timeout=30)
        assert r.status_code == 200
        assert r.json() == {"ok": True, "hidden": False}


# ---------- G: IA follow-up (BYOK 503) + send-message ----------
class TestAIFollowUp:
    def test_follow_up_prepay_503_byok(self, admin):
        r = admin.post(f"{BASE_URL}/api/ai/quotations/{QUO_PACKAGE}/follow-up-prepay", timeout=60)
        assert r.status_code == 503, f"expected 503 (IA no configurada), got {r.status_code}: {r.text}"
        detail = r.json().get("detail", "")
        assert "IA no" in detail or "no est" in detail.lower(), f"unexpected detail: {detail}"

    def test_follow_up_postsale_503_byok(self, admin):
        r = admin.post(f"{BASE_URL}/api/ai/quotations/{QUO_PACKAGE}/follow-up-postsale", timeout=60)
        assert r.status_code == 503
        detail = r.json().get("detail", "")
        assert "IA no" in detail or "no est" in detail.lower()

    def test_send_message_returns_to_email(self, admin):
        r = admin.post(f"{BASE_URL}/api/quotations/{QUO_PACKAGE}/send-message",
                       json={"text": "Hola, este es un mensaje de prueba TEST_iter52."}, timeout=60)
        # Debe responder 200 con to=email cliente (email_sent puede ser false si Resend no está configurado)
        # o 400 si el cliente no tiene email registrado — validar el caso feliz o skip
        if r.status_code == 400 and "correo" in r.json().get("detail", "").lower():
            pytest.skip("Cliente demo sin correo — comportamiento correcto (validación)")
        assert r.status_code == 200, r.text
        data = r.json()
        assert "email_sent" in data
        assert "to" in data and "@" in data["to"]


# ---------- H1: diff real + traducciones ----------
class TestQuotationHistoryDiff:
    def _get_last_edit(self, admin, qid):
        r = admin.get(f"{BASE_URL}/api/quotations/{qid}", timeout=30)
        assert r.status_code == 200
        hist = r.json().get("history", [])
        edits = [h for h in hist if h.get("action") == "edited"]
        return edits[-1] if edits else None

    def test_edit_single_field_notes_shows_only_notas(self, admin):
        # cambiar solo 'notes'
        new_notes = f"TEST_iter52 nota — {os.urandom(3).hex()}"
        r = admin.patch(f"{BASE_URL}/api/quotations/{QUO_PACKAGE}",
                        json={"notes": new_notes}, timeout=30)
        assert r.status_code == 200, r.text
        edit = self._get_last_edit(admin, QUO_PACKAGE)
        assert edit is not None, "no se registró history de edición"
        detail = edit["detail"]
        assert detail.startswith("Editó:"), detail
        # Debe listar SOLO 'notas' (no 13 campos)
        assert "notas" in detail
        # No debe contener snake_case crudo
        assert "presentation_text" not in detail
        assert "executive_id" not in detail
        # No debe listar montones de campos (chequear que no sean >2 comas → >3 campos)
        assert detail.count(",") <= 1, f"Demasiados campos listados: {detail}"

    def test_edit_same_value_no_history(self, admin):
        # leer valor actual y re-enviarlo → NO debería registrar history
        r = admin.get(f"{BASE_URL}/api/quotations/{QUO_PACKAGE}", timeout=30)
        current_notes = r.json().get("notes", "")
        hist_before = r.json().get("history", [])
        edits_before = len([h for h in hist_before if h.get("action") == "edited"])
        r = admin.patch(f"{BASE_URL}/api/quotations/{QUO_PACKAGE}",
                        json={"notes": current_notes}, timeout=30)
        assert r.status_code == 200
        r = admin.get(f"{BASE_URL}/api/quotations/{QUO_PACKAGE}", timeout=30)
        hist_after = r.json().get("history", [])
        edits_after = len([h for h in hist_after if h.get("action") == "edited"])
        assert edits_after == edits_before, "se registró history a pesar de que el valor no cambió"

    def test_presentation_text_translated(self, admin):
        new_pres = f"TEST_iter52 presentación — {os.urandom(3).hex()}"
        r = admin.patch(f"{BASE_URL}/api/quotations/{QUO_PACKAGE}",
                        json={"presentation_text": new_pres}, timeout=30)
        assert r.status_code == 200
        edit = self._get_last_edit(admin, QUO_PACKAGE)
        assert edit is not None
        detail = edit["detail"]
        assert "texto de presentación" in detail, f"esperaba 'texto de presentación' en: {detail}"
        assert "presentation_text" not in detail


# ---------- REGRESIÓN: motor de precios (Paquete Armado) ----------
class TestPricingRegression:
    def test_paquete_subtotal_plus_commission_equals_total(self, admin):
        """El requisito explícito del review: para tipo 'paquete' se debe cumplir
        subtotal+commission == total (± 0.02)."""
        r = admin.get(f"{BASE_URL}/api/quotations/{QUO_PACKAGE}", timeout=30)
        assert r.status_code == 200
        q = r.json()
        assert q.get("type") == "paquete"
        subtotal = float(q.get("subtotal", 0) or 0)
        commission = float(q.get("commission", 0) or 0)
        total = float(q.get("total", 0) or 0)
        assert abs((subtotal + commission) - total) <= 0.02, (
            f"[{QUO_PACKAGE}] subtotal({subtotal}) + commission({commission}) != total({total})"
        )

    def test_custom_invariant(self, admin):
        """Custom sigue el mismo patrón (subtotal+commission = total)."""
        r = admin.get(f"{BASE_URL}/api/quotations/{QUO_CUSTOM}", timeout=30)
        assert r.status_code == 200
        q = r.json()
        subtotal = float(q.get("subtotal", 0) or 0)
        commission = float(q.get("commission", 0) or 0)
        total = float(q.get("total", 0) or 0)
        assert abs((subtotal + commission) - total) <= 0.02
