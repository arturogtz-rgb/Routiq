"""Iter 73 — TC editable por cotización (PUT /fx, refresh, candado, create/patch fx, leyenda público/PDF, PDF confirmación)."""
import io
import os
import re
import pytest
import requests
import pdfplumber

BASE = (os.environ.get("REACT_APP_BACKEND_URL") or open('/app/frontend/.env').read().split('REACT_APP_BACKEND_URL=')[1].split()[0]).rstrip('/')
API = f"{BASE}/api"
ITEMS = [{"category": "hospedaje", "name": "Hotel", "price_type": "neto", "unit": "per_night", "checkin": "2026-11-04", "checkout": "2026-11-09", "nights": 5,
          "occupancy_rows": [{"ocupacion": "doble", "rooms": 1, "price": 700}, {"ocupacion": "cuadruple", "rooms": 1, "price": 560}]},
         {"category": "traslado", "name": "Vehículo", "price_type": "publico", "unit": "per_vehicle", "net_price": 6000, "qty": 1},
         {"category": "tour", "name": "Tour", "price_type": "publico", "unit": "per_person", "net_price": 450, "qty": 0},
         {"category": "extra", "name": "Cena", "price_type": "publico", "unit": "per_group", "net_price": 3000, "qty": 1}]
S = {}
NOTE_TAIL = "El cobro se realiza en pesos mexicanos (MXN) y el tipo de cambio puede variar según su banco."


def _login(email):
    ses = requests.Session()
    r = ses.post(f"{API}/auth/login", json={"email": email, "password": "Demo2026!"})
    assert r.status_code == 200, r.text
    return ses


@pytest.fixture(scope="module")
def s():
    ses = _login("admin@aventurate.mx")
    S["ex"] = _login("ejecutivo@aventurate.mx")
    orig = ses.get(f"{API}/companies/me").json()["pricing_config"]
    S["orig"] = orig
    S["cfg"] = {**orig, "margin_divisor": 0.80, "commissions": {"directo": 0.0, "agencia": 0.10, "mayorista": 0.15, "operador": 0.15}}
    r = ses.patch(f"{API}/companies/me/pricing", json={**S["cfg"], "fx_mayorista_mxn_per_usd": 18.5})
    assert r.status_code == 200
    S["clients"], S["quotes"] = [], []
    yield ses
    for q in S["quotes"]:
        ses.delete(f"{API}/quotations/{q}")
    for c in S["clients"]:
        ses.delete(f"{API}/clients/{c}")
    ses.patch(f"{API}/companies/me/pricing", json=orig)


def _client(s, channel, title):
    cl = s.post(f"{API}/clients", json={"name": f"TEST73 {title}", "channel": channel}).json()
    S["clients"].append(cl["id"])
    return cl["id"]


def _quote(s, channel, title, **extra):
    cid = _client(s, channel, title)
    r = s.post(f"{API}/quotations", json={"type": "personalizado", "client_id": cid, "custom_title": f"TEST73 {title}",
                                         "dates": {"start": "2026-11-04", "end": "2026-11-09"},
                                         "pax": {"adultos": 6, "menores": 0, "rooms": []}, "custom_items": ITEMS,
                                         "show_per_person": True, **extra})
    if r.status_code == 201:
        S["quotes"].append(r.json()["id"])
    return r


def _pdf_pages(content):
    with pdfplumber.open(io.BytesIO(content)) as pdf:
        return [p.extract_text() or "" for p in pdf.pages]


# A4: create with custom TC / omitted / non-mayorista
def test_01_create_custom_rate(s):
    r = _quote(s, "mayorista", "Custom", fx_rate_mxn_per_usd=19.25, fx_reason="TC acordado")
    assert r.status_code == 201, r.text
    d = s.get(f"{API}/quotations/{r.json()['id']}").json()
    assert d["fx_rate_mxn_per_usd"] == 19.25
    assert len(d["fx_history"]) == 1 and d["fx_history"][0]["old"] == 18.5 and d["fx_history"][0]["new"] == 19.25
    assert d["fx_history"][0]["reason"] == "TC acordado"
    assert d["total"] == 29282.50
    assert d["usd_presentation"]["rate"] == 19.25
    assert d["fx_lock"]["locked"] is False
    S["qa"] = d["id"]


def test_02_create_omitted_and_other_channel(s):
    r = _quote(s, "mayorista", "Omit")
    d = s.get(f"{API}/quotations/{r.json()['id']}").json()
    assert d["fx_rate_mxn_per_usd"] == 18.5 and not d.get("fx_history")
    S["qb"] = d["id"]
    r2 = _quote(s, "directo", "Dir", fx_rate_mxn_per_usd=20)
    d2 = s.get(f"{API}/quotations/{r2.json()['id']}").json()
    assert d2.get("fx_rate_mxn_per_usd") is None and d2["usd_presentation"] is None
    S["qdir"] = d2["id"]


@pytest.mark.parametrize("bad", [0, -1, 18.12345])
def test_03_create_invalid(s, bad):
    assert _quote(s, "mayorista", f"Bad{bad}", fx_rate_mxn_per_usd=bad).status_code == 400


# A2: PUT /fx
def test_04_put_fx(s):
    other_before = s.get(f"{API}/quotations/{S['qb']}").json()["fx_rate_mxn_per_usd"]
    r = s.put(f"{API}/quotations/{S['qa']}/fx", json={"rate": 17.8765, "reason": "cliente pidió"})
    assert r.status_code == 200 and r.json()["changed"] is True
    d = s.get(f"{API}/quotations/{S['qa']}").json()
    assert d["fx_rate_mxn_per_usd"] == 17.8765
    e = d["fx_history"][-1]
    assert e["old"] == 19.25 and e["new"] == 17.8765 and e["reason"] == "cliente pidió" and e["source"] == "manual" and e["unlocked"] is False
    assert e["user_name"] and e["user_id"]
    assert any(h["action"] == "fx" and "17.8765" in h["detail"] for h in d["history"])
    assert s.get(f"{API}/quotations/{S['qb']}").json()["fx_rate_mxn_per_usd"] == other_before
    assert d["total"] == 29282.50


@pytest.mark.parametrize("bad", [0, -1, 18.12345])
def test_05_put_invalid(s, bad):
    assert s.put(f"{API}/quotations/{S['qa']}/fx", json={"rate": bad}).status_code == 400


def test_06_put_on_directo_400(s):
    assert s.put(f"{API}/quotations/{S['qdir']}/fx", json={"rate": 18}).status_code == 400


def test_07_patch_fx(s):
    r = s.patch(f"{API}/quotations/{S['qa']}", json={"fx_rate_mxn_per_usd": 18.5, "fx_reason": "patch"})
    assert r.status_code == 200, r.text
    d = s.get(f"{API}/quotations/{S['qa']}").json()
    assert d["fx_rate_mxn_per_usd"] == 18.5 and d["fx_history"][-1]["reason"] == "patch"
    assert d["usd_presentation"]["total_usd"] == 1582.86


# A1: settings change doesn't alter existing quotations; refresh does
def test_08_settings_change(s):
    s.patch(f"{API}/companies/me/pricing", json={**S["cfg"], "fx_mayorista_mxn_per_usd": 20.1})
    assert s.get(f"{API}/quotations/{S['qa']}").json()["fx_rate_mxn_per_usd"] == 18.5
    assert s.get(f"{API}/quotations/{S['qb']}").json()["fx_rate_mxn_per_usd"] == 18.5
    r = S["ex"].post(f"{API}/quotations/{S['qb']}/fx/refresh", json={})
    assert r.status_code == 200, r.text
    d = s.get(f"{API}/quotations/{S['qb']}").json()
    assert d["fx_rate_mxn_per_usd"] == 20.1 and d["fx_history"][-1]["source"] == "refresh"
    s.patch(f"{API}/companies/me/pricing", json={**S["cfg"], "fx_mayorista_mxn_per_usd": 18.5})


# A3: ganada alone not locked; lock with payment
def test_09_ganada_not_locked(s):
    assert s.patch(f"{API}/quotations/{S['qb']}/state", json={"state": "ganada"}).status_code == 200
    d = S["ex"].get(f"{API}/quotations/{S['qb']}").json()
    assert d["fx_lock"]["locked"] is False and d["fx_lock"]["can_unlock"] is False
    assert S["ex"].put(f"{API}/quotations/{S['qb']}/fx", json={"rate": 18.6}).status_code == 200


def test_10_lock_by_payment(s):
    r = s.patch(f"{API}/quotations/{S['qa']}/mark-paid", json={"amount": 1000, "method": "transfer"})
    assert r.status_code == 200, r.text
    d = S["ex"].get(f"{API}/quotations/{S['qa']}").json()
    assert d["fx_lock"]["locked"] is True and "pago" in d["fx_lock"]["reason"] and d["fx_lock"]["can_unlock"] is False
    assert s.get(f"{API}/quotations/{S['qa']}").json()["fx_lock"]["can_unlock"] is True
    assert S["ex"].put(f"{API}/quotations/{S['qa']}/fx", json={"rate": 18.7, "reason": "x"}).status_code == 403
    noop = S["ex"].post(f"{API}/quotations/{S['qa']}/fx/refresh", json={"reason": "x"})  # same rate → no-op
    assert noop.status_code == 200 and noop.json()["changed"] is False
    s.patch(f"{API}/companies/me/pricing", json={**S["cfg"], "fx_mayorista_mxn_per_usd": 20.1})
    try:
        assert S["ex"].post(f"{API}/quotations/{S['qa']}/fx/refresh", json={"reason": "x"}).status_code == 403
        assert s.post(f"{API}/quotations/{S['qa']}/fx/refresh", json={}).status_code == 400
    finally:
        s.patch(f"{API}/companies/me/pricing", json={**S["cfg"], "fx_mayorista_mxn_per_usd": 18.5})
    assert S["ex"].patch(f"{API}/quotations/{S['qa']}", json={"fx_rate_mxn_per_usd": 18.7}).status_code == 403
    assert s.put(f"{API}/quotations/{S['qa']}/fx", json={"rate": 18.7}).status_code == 400
    assert s.put(f"{API}/quotations/{S['qa']}/fx", json={"rate": 18.7, "reason": "   "}).status_code == 400
    r = s.put(f"{API}/quotations/{S['qa']}/fx", json={"rate": 18.7, "reason": "ajuste admin"})
    assert r.status_code == 200
    d = s.get(f"{API}/quotations/{S['qa']}").json()
    assert d["fx_history"][-1]["unlocked"] is True and d["fx_lock"]["locked"] is True
    assert s.put(f"{API}/quotations/{S['qa']}/fx", json={"rate": 18.5}).status_code == 400  # still requires reason
    assert s.put(f"{API}/quotations/{S['qa']}/fx", json={"rate": 18.5, "reason": "volver"}).status_code == 200


def test_11_lock_by_confirmation_and_pdf(s):
    qb = S["qb"]
    s.put(f"{API}/quotations/{qb}/fx", json={"rate": 18.5})
    pre = s.get(f"{API}/quotations/{qb}/booking-confirmation")
    assert pre.status_code == 200, pre.text
    body = pre.json()
    data = body.get("confirmation") or body.get("prefill") or body
    payload = {k: data.get(k) for k in ("agent_name", "passenger_name", "num_persons", "services", "lodging", "itinerary",
                                        "general_observations", "price_per_person", "total_amount") if data.get(k) is not None}
    payload["total_amount"] = 29282.50
    payload["price_per_person"] = 5376.25
    payload["itinerary"] = [{"title": "Día 1", "description": "Llegada y paseo"}]
    r = s.post(f"{API}/quotations/{qb}/booking-confirmation", json=payload)
    assert r.status_code == 200, r.text
    S["conf"] = r.json()["id"]
    d = S["ex"].get(f"{API}/quotations/{qb}").json()
    assert d["fx_lock"]["locked"] is True and "Confirmación" in d["fx_lock"]["reason"]
    assert S["ex"].put(f"{API}/quotations/{qb}/fx", json={"rate": 18.9, "reason": "x"}).status_code == 403
    # B: PDF
    pdf = s.get(f"{API}/booking-confirmations/{S['conf']}/pdf")
    assert pdf.status_code == 200
    pages = _pdf_pages(pdf.content)
    txt = "\n".join(pages)
    S["conf_txt"] = txt
    assert "US$1,582.86" in txt, txt[-1500:]  # iter74: same as quotation total_usd (Σ pp × pax)
    assert f"US${round(5376.25/18.5, 2):,.2f}" in txt
    assert "$18.50 MXN por USD" in txt.replace("\n", " ")
    last = pages[-1]
    S["conf_last"] = last
    assert "$" not in last and "USD" not in last and "MXN" not in last, last


# A5: public + quotation PDF legend uses stored rate (not settings)
def test_12_public_and_pdf_legend(s):
    qa = S["qa"]
    s.put(f"{API}/quotations/{qa}/fx", json={"rate": 19.1, "reason": "leyenda"})
    s.patch(f"{API}/companies/me/pricing", json={**S["cfg"], "fx_mayorista_mxn_per_usd": 21.0})
    try:
        tok = s.post(f"{API}/quotations/{qa}/public-link").json()["token"]
        pub = requests.get(f"{API}/public/quotations/{tok}").json()
        u = pub["quotation"]["usd_presentation"]
        assert u["rate"] == 19.1 and "$19.10 MXN por USD" in u["note"] and NOTE_TAIL in u["note"]
        S["tok_qa"] = tok
        txt = " ".join(_pdf_pages(s.get(f"{API}/quotations/{qa}/pdf").content)).replace("\n", " ")
        assert "$19.10 MXN por USD" in txt and "21.00" not in txt
        assert "puede variar según su banco" in txt
    finally:
        s.patch(f"{API}/companies/me/pricing", json={**S["cfg"], "fx_mayorista_mxn_per_usd": 18.5})


def test_13_directo_confirmation_pdf_no_usd(s):
    qd = S["qdir"]
    s.patch(f"{API}/quotations/{qd}/state", json={"state": "ganada"})
    r = s.post(f"{API}/quotations/{qd}/booking-confirmation", json={"total_amount": 29282.5, "price_per_person": 4880.42})
    assert r.status_code == 200, r.text
    txt = "\n".join(_pdf_pages(s.get(f"{API}/booking-confirmations/{r.json()['id']}/pdf").content))
    assert "US$" not in txt and "29,282.50" in txt
