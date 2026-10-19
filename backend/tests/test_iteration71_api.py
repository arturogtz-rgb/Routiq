"""Iter 71 — API E2E: TC Mayorista internacional (Ajustes, snapshot, refresh, público, PDF, otros canales)."""
import io
import os
import pytest
import requests

BASE = (os.environ.get("REACT_APP_BACKEND_URL") or open('/app/frontend/.env').read().split('REACT_APP_BACKEND_URL=')[1].split()[0]).rstrip('/')
API = f"{BASE}/api"
ITEMS = [{"category": "hospedaje", "name": "Hotel", "price_type": "neto", "unit": "per_night", "checkin": "2026-11-04", "checkout": "2026-11-09", "nights": 5,
          "occupancy_rows": [{"ocupacion": "doble", "rooms": 1, "price": 700}, {"ocupacion": "cuadruple", "rooms": 1, "price": 560}]},
         {"category": "traslado", "name": "Vehículo", "price_type": "publico", "unit": "per_vehicle", "net_price": 6000, "qty": 1},
         {"category": "tour", "name": "Tour", "price_type": "publico", "unit": "per_person", "net_price": 450, "qty": 0},
         {"category": "extra", "name": "Cena", "price_type": "publico", "unit": "per_group", "net_price": 3000, "qty": 1}]
S = {}


@pytest.fixture(scope="module")
def s():
    ses = requests.Session()
    r = ses.post(f"{API}/auth/login", json={"email": "admin@aventurate.mx", "password": "Demo2026!"})
    assert r.status_code == 200
    orig = ses.get(f"{API}/companies/me").json()["pricing_config"]
    S["orig"] = orig
    S["cfg"] = {**orig, "margin_divisor": 0.80, "commissions": {"directo": 0.0, "agencia": 0.10, "mayorista": 0.15, "operador": 0.15}}
    S["clients"], S["quotes"] = [], []
    yield ses
    for q in S["quotes"]:
        ses.delete(f"{API}/quotations/{q}")
    for c in S["clients"]:
        ses.delete(f"{API}/clients/{c}")
    ses.patch(f"{API}/companies/me/pricing", json=orig)


def _quote(s, channel, title):
    cl = s.post(f"{API}/clients", json={"name": f"TEST71 {title}", "channel": channel}).json()
    S["clients"].append(cl["id"])
    r = s.post(f"{API}/quotations", json={"type": "personalizado", "client_id": cl["id"], "custom_title": f"TEST71 {title}",
                                         "dates": {"start": "2026-11-04", "end": "2026-11-09"},
                                         "pax": {"adultos": 6, "menores": 0, "rooms": []}, "custom_items": ITEMS, "show_per_person": True})
    assert r.status_code == 201, r.text
    S["quotes"].append(r.json()["id"])
    return r.json()


def test_01_no_tc_mayorista_warning(s):
    r = s.patch(f"{API}/companies/me/pricing", json={**S["cfg"], "fx_mayorista_mxn_per_usd": None})
    assert r.status_code == 200 and r.json()["pricing_config"]["fx_mayorista_mxn_per_usd"] is None
    q = _quote(s, "mayorista", "SinTC")
    d = s.get(f"{API}/quotations/{q['id']}").json()
    assert d.get("fx_rate_mxn_per_usd") is None
    assert d["usd_presentation"]["available"] is False and "Captura el tipo de cambio" in d["usd_presentation"]["warning"]
    tok = s.post(f"{API}/quotations/{q['id']}/public-link").json()["token"]
    pub = requests.get(f"{API}/public/quotations/{tok}").json()
    assert pub["quotation"]["usd_presentation"] is None
    assert pub["payment"]["equivalent_amount"] is None
    # refresh without TC -> 400
    assert s.post(f"{API}/quotations/{q['id']}/fx/refresh").status_code == 400
    S["q_notc"] = q["id"]


@pytest.mark.parametrize("bad", [0, -1, 18.12345])
def test_02_invalid_fx(s, bad):
    assert s.patch(f"{API}/companies/me/pricing", json={**S["cfg"], "fx_mayorista_mxn_per_usd": bad}).status_code == 422


def test_03_set_fx(s):
    r = s.patch(f"{API}/companies/me/pricing", json={**S["cfg"], "fx_mayorista_mxn_per_usd": 18.5, "fx_mayorista_updated_at": "1999-01-01"})
    pc = r.json()["pricing_config"]
    assert pc["fx_mayorista_mxn_per_usd"] == 18.5 and pc["fx_mayorista_updated_at"] and not pc["fx_mayorista_updated_at"].startswith("1999")
    S["fx_date"] = pc["fx_mayorista_updated_at"]
    # same rate again keeps date
    pc2 = s.patch(f"{API}/companies/me/pricing", json={**S["cfg"], "fx_mayorista_mxn_per_usd": 18.5}).json()["pricing_config"]
    assert pc2["fx_mayorista_updated_at"] == S["fx_date"]


def test_04_case_c(s):
    q = _quote(s, "mayorista", "CasoC")
    d = s.get(f"{API}/quotations/{q['id']}").json()
    assert d["total"] == 29282.50 and d["fx_rate_mxn_per_usd"] == 18.5
    u = d["usd_presentation"]
    rows = {r["key"]: r for r in u["rows"]}
    assert rows["doble"]["price_per_person_mxn"] == 5376.25 and rows["doble"]["price_per_person_usd"] == 290.61
    assert rows["cuadruple"]["price_per_person_mxn"] == 4632.50 and rows["cuadruple"]["price_per_person_usd"] == 250.41
    assert u["total_usd"] == 1582.86 and u["direct_total_usd"] == 1582.84 and u["rounding_diff_usd"] == 0.02
    assert "$18.50 MXN por USD" in u["note"]
    S["qc"] = q["id"]


def test_05_other_channels_no_usd(s):
    for ch in ("directo", "agencia", "operador"):
        q = _quote(s, ch, f"Otro{ch}")
        d = s.get(f"{API}/quotations/{q['id']}").json()
        assert d["usd_presentation"] is None and d.get("fx_rate_mxn_per_usd") is None
        tok = s.post(f"{API}/quotations/{q['id']}/public-link").json()["token"]
        pub = requests.get(f"{API}/public/quotations/{tok}").json()
        assert pub["quotation"]["usd_presentation"] is None
        if ch == "directo":
            S["q_dir"] = q["id"]


def test_06_public_and_card_fee_mxn(s):
    r = s.patch(f"{API}/quotations/{S['qc']}/payment-config", json={"payment_enabled": True, "allowed_pay_type": "full", "card_fee_enabled": True, "card_fee_percent": 5.5})
    assert r.status_code == 200
    tok = s.post(f"{API}/quotations/{S['qc']}/public-link").json()["token"]
    S["tok"] = tok
    pub = requests.get(f"{API}/public/quotations/{tok}").json()
    u = pub["quotation"]["usd_presentation"]
    assert u["total_usd"] == 1582.86 and u["rate"] == 18.5
    pay = pub["payment"]
    assert pay["equivalent_amount"] is None
    assert pay["card_fee_amount"] == round(29282.50 * 0.055, 2)
    assert pub["quotation"].get("currency", "MXN") == "MXN"


def test_07_pdf(s):
    r = s.get(f"{API}/quotations/{S['qc']}/pdf")
    assert r.status_code == 200
    from pypdf import PdfReader
    txt = "\n".join(p.extract_text() for p in PdfReader(io.BytesIO(r.content)).pages)
    S["pdf"] = txt
    assert "US$" in txt
    assert "(detalle en MXN)" in txt
    flat = " ".join(txt.split())
    assert "Montos en dólares de referencia al tipo de cambio de $18.50 MXN por USD" in flat


def test_08_pdf_directo_no_usd(s):
    r = s.get(f"{API}/quotations/{S['q_dir']}/pdf")
    from pypdf import PdfReader
    txt = "\n".join(p.extract_text() for p in PdfReader(io.BytesIO(r.content)).pages)
    assert "US$" not in txt and "Montos en dólares de referencia" not in txt


def test_09_settings_change_snapshot_kept_then_refresh(s):
    s.patch(f"{API}/companies/me/pricing", json={**S["cfg"], "fx_mayorista_mxn_per_usd": 19.0})
    d = s.get(f"{API}/quotations/{S['qc']}").json()
    assert d["usd_presentation"]["rate"] == 18.5 and d["usd_presentation"]["company_rate"] == 19.0
    assert d["total"] == 29282.50
    r = s.post(f"{API}/quotations/{S['qc']}/fx/refresh")
    assert r.status_code == 200 and r.json()["fx_rate_mxn_per_usd"] == 19.0
    d = s.get(f"{API}/quotations/{S['qc']}").json()
    assert d["usd_presentation"]["rate"] == 19.0 and d["total"] == 29282.50
    assert d["usd_presentation"]["total_usd"] == round(round(5376.25 / 19, 2) * 2 + round(4632.50 / 19, 2) * 4, 2)
    # refresh not allowed for directo
    assert s.post(f"{API}/quotations/{S['q_dir']}/fx/refresh").status_code == 400


def test_10_edit_keeps_original_tc(s):
    d = s.get(f"{API}/quotations/{S['qc']}").json()
    r = s.patch(f"{API}/quotations/{S['qc']}", json={"custom_items": ITEMS, "pax": d["pax"], "dates": d["dates"], "custom_title": "TEST71 CasoC edit", "show_per_person": True})
    assert r.status_code == 200, r.text
    d2 = s.get(f"{API}/quotations/{S['qc']}").json()
    assert d2["fx_rate_mxn_per_usd"] == 19.0 and d2["total"] == 29282.50


def test_11_show_per_person_off_total_only(s):
    s.patch(f"{API}/quotations/{S['qc']}", json={"show_per_person": False})
    d = s.get(f"{API}/quotations/{S['qc']}").json()
    if d.get("show_per_person") is False:
        assert d["usd_presentation"]["rows"] == [] and d["usd_presentation"]["total_usd"] == round(29282.50 / 19.0, 2)


def test_12_exchange_rate_no_fake(s):
    j = requests.get(f"{API}/exchange-rate").json()
    assert j["mxn_per_usd"] is None or (j["mxn_per_usd"] != 17.0 and j["source"] != "fallback")
