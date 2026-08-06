"""Iteration 4 (report iteration 58) — Backend regression:
- Anti double-charge reconciliation (P0-B)
- Payment gating (payment_enabled, allowed_pay_type)
- Card bank fee (card_fee_enabled, card_fee_percent, card_fee_amount)
- Company integrations card_fee_percent persistence
- Booking confirmation payment_stamp on PDF (auto/paid/pending)
- Rename Ganada->Aceptada (UI only; backend Literal still 'ganada')
"""
import os
import pytest
import requests

def _read_backend_url():
    url = os.environ.get("REACT_APP_BACKEND_URL")
    if url:
        return url.rstrip("/")
    envf = "/app/frontend/.env"
    if os.path.exists(envf):
        for line in open(envf):
            if line.startswith("REACT_APP_BACKEND_URL="):
                return line.split("=", 1)[1].strip().rstrip("/")
    raise RuntimeError("REACT_APP_BACKEND_URL not set")


BASE_URL = _read_backend_url()
API = f"{BASE_URL}/api"

ADMIN = {"email": "admin@aventurate.mx", "password": "Demo2026!"}
UITAG = "TEST_ITER58_"


@pytest.fixture(scope="module")
def s():
    sess = requests.Session()
    r = sess.post(f"{API}/auth/login", json=ADMIN, timeout=30)
    assert r.status_code == 200, r.text
    return sess


@pytest.fixture(scope="module")
def created(s):
    """Create client + paquete quotation, capture ids/token."""
    # find a package
    pkgs = s.get(f"{API}/packages", timeout=30).json()
    assert isinstance(pkgs, list) and len(pkgs) > 0, "No hay paquetes seed"
    pkg = pkgs[0]
    # ensure at least one hotel
    hotels = pkg.get("hotels") or []
    assert hotels, "El paquete seed no tiene hoteles"
    hotel = hotels[0]["name"]

    # create client
    r = s.post(f"{API}/clients", json={
        "name": f"{UITAG}Client",
        "type": "directo",
        "email": "test58@example.com",
        "phone": "5551234567",
    }, timeout=30)
    assert r.status_code in (200, 201), r.text
    client = r.json()
    client_id = client["id"]

    # create quotation (paquete)
    body = {
        "type": "paquete",
        "client_id": client_id,
        "package_id": pkg["id"],
        "hotel_name": hotel,
        "dates": {"start": "2026-06-01", "end": "2026-06-04"},
        "pax": {"adultos": 2, "menores": 0,
                "rooms": [{"ocupacion": "doble", "count": 1}]},
    }
    r = s.post(f"{API}/quotations", json=body, timeout=30)
    assert r.status_code in (200, 201), r.text
    q = r.json()
    qid = q["id"]

    # create public link
    r = s.post(f"{API}/quotations/{qid}/public-link", timeout=30)
    assert r.status_code in (200, 201), r.text
    token = r.json().get("token") or r.json().get("public_link", {}).get("token")
    assert token, r.text

    yield {"qid": qid, "client_id": client_id, "token": token, "quotation": q}

    # cleanup
    try:
        s.delete(f"{API}/quotations/{qid}", timeout=30)
    except Exception:
        pass
    try:
        s.delete(f"{API}/clients/{client_id}", timeout=30)
    except Exception:
        pass


# ---------------- Integrations card_fee_percent ----------------
class TestIntegrationsCardFee:
    def test_get_default_card_fee(self, s):
        r = s.get(f"{API}/companies/me/integrations", timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "card_fee_percent" in data
        # default per spec = 4.5
        assert float(data["card_fee_percent"]) >= 0

    def test_persist_card_fee(self, s):
        r = s.patch(f"{API}/companies/me/integrations",
                    json={"card_fee_percent": 3.75}, timeout=30)
        assert r.status_code == 200, r.text
        r2 = s.get(f"{API}/companies/me/integrations", timeout=30)
        assert r2.json()["card_fee_percent"] == 3.75
        # restore default 4.5
        s.patch(f"{API}/companies/me/integrations", json={"card_fee_percent": 4.5}, timeout=30)


# ---------------- Payment gating & config ----------------
class TestPaymentGating:
    def test_public_default_payment_disabled(self, s, created):
        r = requests.get(f"{API}/public/quotations/{created['token']}", timeout=30)
        assert r.status_code == 200, r.text
        pay = r.json().get("payment") or {}
        # by default payment_enabled=False on freshly created quotation
        assert pay.get("enabled") is False

    def test_checkout_blocked_when_disabled(self, s, created):
        r = requests.post(
            f"{API}/public/quotations/{created['token']}/checkout",
            json={"origin_url": BASE_URL, "pay_type": "total"},
            timeout=30,
        )
        # 403 gated
        assert r.status_code == 403, r.text
        assert "habilitado" in r.text.lower()

    def test_enable_payment_config_full(self, s, created):
        r = s.patch(f"{API}/quotations/{created['qid']}/payment-config", json={
            "payment_enabled": True,
            "allowed_pay_type": "full",
            "card_fee_enabled": True,
            "card_fee_percent": 4.5,
        }, timeout=30)
        assert r.status_code == 200, r.text
        q = r.json()
        assert q["payment_enabled"] is True
        assert q["allowed_pay_type"] == "full"
        assert q["card_fee_enabled"] is True
        assert float(q["card_fee_percent"]) == 4.5

    def test_public_reflects_enabled_and_fee(self, s, created):
        r = requests.get(f"{API}/public/quotations/{created['token']}", timeout=30)
        assert r.status_code == 200
        data = r.json()
        pay = data["payment"]
        # payment.enabled depends on stripe_ready too (company has stripe test key)
        # allowed_pay_type surfaced
        assert pay["allowed_pay_type"] == "full"
        assert pay["card_fee_percent"] == 4.5
        assert pay["card_fee_enabled"] is True
        # amount_due>0 so card_fee_amount>0
        amt_due = data["quotation"]["amount_due"]
        expected_fee = round(amt_due * 4.5 / 100.0, 2)
        assert abs(pay["card_fee_amount"] - expected_fee) < 0.02

    def test_wrong_pay_type_returns_400(self, s, created):
        # allowed_pay_type = full, client tries deposit
        r = requests.post(
            f"{API}/public/quotations/{created['token']}/checkout",
            json={"origin_url": BASE_URL, "pay_type": "deposit"},
            timeout=30,
        )
        # gating enabled=true, but allowed mismatch => 400
        # It could be 403 if enabled failed; assert 400 specifically
        assert r.status_code == 400, r.text

    def test_switch_to_deposit_and_wrong_type(self, s, created):
        r = s.patch(f"{API}/quotations/{created['qid']}/payment-config",
                    json={"allowed_pay_type": "deposit"}, timeout=30)
        assert r.status_code == 200
        r2 = requests.post(
            f"{API}/public/quotations/{created['token']}/checkout",
            json={"origin_url": BASE_URL, "pay_type": "total"},
            timeout=30,
        )
        assert r2.status_code == 400, r2.text

    def test_already_paid_blocks_checkout(self, s, created):
        # Force amount_due<=0 via mark-paid (transfer flow)
        # First need to accept publicly and then mark paid
        # Get final_total
        q = s.get(f"{API}/quotations/{created['qid']}", timeout=30).json()
        final_total = q.get("final_total") or q.get("total")
        assert final_total and final_total > 0
        # mark paid for the full amount
        r = s.patch(f"{API}/quotations/{created['qid']}/mark-paid", json={
            "amount": float(final_total),
            "method": "transfer",
            "note": "TEST58 full payment",
        }, timeout=30)
        assert r.status_code == 200, r.text
        # switch allowed to full for consistency
        s.patch(f"{API}/quotations/{created['qid']}/payment-config",
                json={"allowed_pay_type": "full"}, timeout=30)
        # Now attempt checkout -> 400 already paid
        r2 = requests.post(
            f"{API}/public/quotations/{created['token']}/checkout",
            json={"origin_url": BASE_URL, "pay_type": "total"},
            timeout=30,
        )
        assert r2.status_code == 400, r2.text
        assert "pagada" in r2.text.lower()


# ---------------- Booking confirmation payment_stamp ----------------
class TestBookingConfirmationStamp:
    def test_save_and_pdf_paid_stamp(self, s, created):
        # quotation is now paid + ganada via previous test
        payload = {
            "confirmation_number": f"{UITAG}-CONF-1",
            "guest_name": f"{UITAG}Guest",
            "plan": "Todo Incluido",
            "payment_stamp": "paid",
        }
        r = s.post(f"{API}/quotations/{created['qid']}/booking-confirmation",
                   json=payload, timeout=30)
        assert r.status_code in (200, 201), r.text
        conf = r.json()
        conf_id = conf.get("id") or conf.get("confirmation_id")
        assert conf_id, conf
        # download PDF
        r2 = s.get(f"{API}/booking-confirmations/{conf_id}/pdf", timeout=30)
        assert r2.status_code == 200, r2.text
        assert r2.headers.get("content-type", "").startswith("application/pdf")
        assert r2.content[:4] == b"%PDF", "Not a valid PDF"
        assert len(r2.content) > 1000

    def test_save_pending_stamp(self, s, created):
        payload = {
            "confirmation_number": f"{UITAG}-CONF-1",
            "guest_name": f"{UITAG}Guest",
            "plan": "Todo Incluido",
            "payment_stamp": "pending",
        }
        r = s.post(f"{API}/quotations/{created['qid']}/booking-confirmation",
                   json=payload, timeout=30)
        assert r.status_code in (200, 201), r.text

    def test_save_auto_stamp(self, s, created):
        payload = {
            "confirmation_number": f"{UITAG}-CONF-1",
            "guest_name": f"{UITAG}Guest",
            "plan": "Todo Incluido",
            "payment_stamp": "auto",
        }
        r = s.post(f"{API}/quotations/{created['qid']}/booking-confirmation",
                   json=payload, timeout=30)
        assert r.status_code in (200, 201), r.text


# ---------------- State internal value still 'ganada' ----------------
class TestStateInternalGanada:
    def test_state_ganada_accepted_by_backend(self, s, created):
        # already ganada from mark-paid, force via state PATCH too
        r = s.patch(f"{API}/quotations/{created['qid']}/state",
                    json={"state": "ganada"}, timeout=30)
        assert r.status_code == 200, r.text
        q = s.get(f"{API}/quotations/{created['qid']}", timeout=30).json()
        assert q["state"] == "ganada"
