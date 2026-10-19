"""Iter 74 — retest fixes: confirmation PDF USD == quotation total_usd; PATCH fx atomic (403 saves nothing)."""
import io
import os
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
    cfg = {**orig, "margin_divisor": 0.80, "commissions": {"directo": 0.0, "agencia": 0.10, "mayorista": 0.15, "operador": 0.15},
           "fx_mayorista_mxn_per_usd": 18.5}
    assert ses.patch(f"{API}/companies/me/pricing", json=cfg).status_code == 200
    S["clients"], S["quotes"] = [], []
    yield ses
    for q in S["quotes"]:
        ses.delete(f"{API}/quotations/{q}")
    for c in S["clients"]:
        ses.delete(f"{API}/clients/{c}")
    ses.patch(f"{API}/companies/me/pricing", json=orig)


def _quote(s, channel, title):
    cl = s.post(f"{API}/clients", json={"name": f"TEST74 {title}", "channel": channel}).json()
    S["clients"].append(cl["id"])
    r = s.post(f"{API}/quotations", json={"type": "personalizado", "client_id": cl["id"], "custom_title": f"TEST74 {title}",
                                         "dates": {"start": "2026-11-04", "end": "2026-11-09"},
                                         "pax": {"adultos": 6, "menores": 0, "rooms": []}, "custom_items": ITEMS,
                                         "show_per_person": True})
    assert r.status_code == 201, r.text
    S["quotes"].append(r.json()["id"])
    return r.json()["id"]


def _pdf_text(content):
    with pdfplumber.open(io.BytesIO(content)) as pdf:
        return [p.extract_text() or "" for p in pdf.pages]


def _confirm(s, qid, total, ppp):
    s.patch(f"{API}/quotations/{qid}/state", json={"state": "ganada"})
    pre = s.get(f"{API}/quotations/{qid}/booking-confirmation").json()
    data = pre.get("confirmation") or pre.get("prefill") or pre
    payload = {k: data.get(k) for k in ("agent_name", "passenger_name", "num_persons", "services", "lodging",
                                        "general_observations") if data.get(k) is not None}
    payload.update({"total_amount": total, "price_per_person": ppp, "itinerary": [{"title": "Día 1", "description": "Llegada"}]})
    r = s.post(f"{API}/quotations/{qid}/booking-confirmation", json=payload)
    assert r.status_code == 200, r.text
    return r.json()["id"]


# Confirmation PDF: total == quotation total -> USD equals quotation total_usd
def test_01_conf_pdf_matches_quotation_usd(s):
    qid = _quote(s, "mayorista", "ConfSame")
    S["qa"] = qid
    d = s.get(f"{API}/quotations/{qid}").json()
    assert d["fx_rate_mxn_per_usd"] == 18.5
    assert d["usd_presentation"]["total_usd"] == 1582.86
    total = d.get("final_total") or d["total"]
    assert total == 29282.50
    cid = _confirm(s, qid, total, 5376.25)
    pages = _pdf_text(s.get(f"{API}/booking-confirmations/{cid}/pdf").content)
    txt = "\n".join(pages)
    assert "US$1,582.86" in txt, txt[-1200:]
    assert "US$1,582.84" not in txt
    assert "29,282.50" in txt
    assert f"US${round(5376.25 / 18.5, 2):,.2f}" in txt
    assert "$18.50 MXN por USD" in txt.replace("\n", " ")
    last = pages[-1]
    assert "$" not in last and "USD" not in last and "MXN" not in last, last


# Confirmation total differs -> round(MXN/TC, 2)
def test_02_conf_pdf_different_total(s):
    qid = _quote(s, "mayorista", "ConfDiff")
    cid = _confirm(s, qid, 30000.0, 5000.0)
    txt = "\n".join(_pdf_text(s.get(f"{API}/booking-confirmations/{cid}/pdf").content))
    assert f"US${round(30000 / 18.5, 2):,.2f}" in txt, txt[-1200:]  # 1,621.62
    assert "US$1,582.86" not in txt


def test_03_directo_conf_pdf_no_usd(s):
    qid = _quote(s, "directo", "Dir")
    s.patch(f"{API}/quotations/{qid}/state", json={"state": "ganada"})
    r = s.post(f"{API}/quotations/{qid}/booking-confirmation", json={"total_amount": 29282.5, "price_per_person": 4880.42})
    assert r.status_code == 200, r.text
    txt = "\n".join(_pdf_text(s.get(f"{API}/booking-confirmations/{r.json()['id']}/pdf").content))
    assert "US$" not in txt and "29,282.50" in txt and "MXN por USD" not in txt


# PATCH atomic: locked + executive -> 403 and notes unchanged
def test_04_patch_locked_exec_atomic(s):
    qid = S["qa"]  # locked by confirmation
    d = S["ex"].get(f"{API}/quotations/{qid}").json()
    assert d["fx_lock"]["locked"] is True
    notes_before = d.get("notes")
    hist_len = len(d.get("history") or [])
    r = S["ex"].patch(f"{API}/quotations/{qid}", json={"fx_rate_mxn_per_usd": 19.9, "notes": "TEST74 should not save"})
    assert r.status_code == 403, r.text
    d2 = s.get(f"{API}/quotations/{qid}").json()
    assert d2.get("notes") == notes_before
    assert d2["fx_rate_mxn_per_usd"] == 18.5
    assert len(d2.get("history") or []) == hist_len


def test_05_patch_invalid_rate_saves_nothing(s):
    qid = _quote(s, "mayorista", "PatchBad")
    S["qb"] = qid
    r = s.patch(f"{API}/quotations/{qid}", json={"fx_rate_mxn_per_usd": 18.12345, "notes": "TEST74 bad"})
    assert r.status_code == 400
    d = s.get(f"{API}/quotations/{qid}").json()
    assert d.get("notes") != "TEST74 bad" and d["fx_rate_mxn_per_usd"] == 18.5


def test_06_patch_valid_saves_all(s):
    qid = S["qb"]
    r = S["ex"].patch(f"{API}/quotations/{qid}", json={"fx_rate_mxn_per_usd": 19.75, "fx_reason": "TEST74", "notes": "TEST74 ok"})
    assert r.status_code == 200, r.text
    d = s.get(f"{API}/quotations/{qid}").json()
    assert d["notes"] == "TEST74 ok"
    assert d["fx_rate_mxn_per_usd"] == 19.75
    e = d["fx_history"][-1]
    assert e["old"] == 18.5 and e["new"] == 19.75 and e["reason"] == "TEST74"
    assert d["usd_presentation"]["rate"] == 19.75
    assert d["total"] == 29282.50


def test_07_admin_locked_patch_requires_reason_atomic(s):
    qid = S["qa"]
    r = s.patch(f"{API}/quotations/{qid}", json={"fx_rate_mxn_per_usd": 19.0, "notes": "TEST74 admin noreason"})
    assert r.status_code == 400
    d = s.get(f"{API}/quotations/{qid}").json()
    assert d.get("notes") != "TEST74 admin noreason" and d["fx_rate_mxn_per_usd"] == 18.5
