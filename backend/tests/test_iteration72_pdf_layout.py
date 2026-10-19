"""Iter 71 parte 2 — Reorganización PDFs Cotización / Confirmación de Reserva (hoja de itinerario, columnas, important_info)."""
import io
import os
import re
import pytest
import requests
import pdfplumber

BASE = (os.environ.get("REACT_APP_BACKEND_URL") or open('/app/frontend/.env').read().split('REACT_APP_BACKEND_URL=')[1].split()[0]).rstrip('/')
API = f"{BASE}/api"
Q_PKG = "ea2a2a1f-8d3e-484f-afb6-57e964bf8fdd"
CONF = "1ef0db49-5df9-4d62-9600-ad7232ec2df6"
CONF_AG_NOEXEC = "de6d8655-192d-464f-992c-a1540650ca23"  # Agencia Demo SA, executive_id 'exec1' (no match), 2 ejecutivos
AG_CLIENT = "c76a1ac7-1eaa-40b2-83bb-63d7cd52f218"
LAURA = "279e0affe93c"
FORBIDDEN = ["$", "MXN", "USD", "Aventúrate", "aventurateporjalisco", "Generado con Routiq"]
S = {"cleanup": []}


def pages(pdf_bytes):
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as p:
        return [pg.extract_text() or "" for pg in p.pages]


def itin_pages(pg):
    """Itinerary sheet = from the first page that has the ITINERARIO header to the end."""
    idx = next((i for i, t in enumerate(pg) if "ITINERARIO" in t), None)
    return idx, (pg[idx:] if idx is not None else [])


def assert_clean(txts):
    joined = "\n".join(txts)
    bad = [f for f in FORBIDDEN if f.lower() in joined.lower()]
    assert not bad, f"Itinerary page contains forbidden {bad}:\n{joined[:1500]}"


@pytest.fixture(scope="module")
def s():
    ses = requests.Session()
    r = ses.post(f"{API}/auth/login", json={"email": "admin@aventurate.mx", "password": "Demo2026!"})
    assert r.status_code == 200
    yield ses
    for qid in S["cleanup"]:
        ses.delete(f"{API}/quotations/{qid}")
    if "restore_ii" in S:
        qid, val = S["restore_ii"]
        ses.patch(f"{API}/quotations/{qid}", json={"important_info": val})


# ---- Quotation PDF (paquete) ----
def test_quotation_pkg_pdf_layout(s):
    q = s.get(f"{API}/quotations/{Q_PKG}").json()
    r = s.get(f"{API}/quotations/{Q_PKG}/pdf")
    assert r.status_code == 200 and r.content[:4] == b"%PDF"
    pg = pages(r.content)
    idx, it = itin_pages(pg)
    assert idx is not None and idx >= 1, "itinerary must be on its own page"
    assert "ITINERARIO" not in "\n".join(pg[:idx])
    first = it[0]
    assert first.lstrip().startswith("CLIENTE") or first.lstrip().startswith("AGENCIA") or first.split("\n")[0].upper().startswith(("CLIENTE", "AGENCIA", "MAYORISTA", "OPERADOR")), first[:200]
    jt = "\n".join(it)
    assert "Día 1" in jt
    assert "Incluye" in jt and "No incluye" in jt
    for k in ("Fechas", "Noches", "Pasajeros", "Hospedaje"):
        assert k in jt, k
    assert_clean(it)
    p1 = "\n".join(pg[:idx])
    assert "Fecha" in p1 and "Concepto" in p1 and "Cant." in p1 and "$ unitario" in p1 and "Subtotal" in p1
    assert "Detalle " not in p1.replace("Detalles de reservación", "")
    total_str = f"{q['total']:,.2f}"
    assert total_str in p1 or f"{q['total']:,.0f}" in p1, (total_str, p1[-800:])
    assert "Generado con Routiq" in pg[idx - 1]
    # Incluye/No incluye no longer on price pages
    assert "No incluye" not in p1
    S["q"] = q


def test_includes_one_per_line(s):
    q = S["q"]
    pack = s.get(f"{API}/packages/{q['package_id']}").json()
    r = s.get(f"{API}/quotations/{Q_PKG}/pdf")
    jt = "\n".join(itin_pages(pages(r.content))[1])
    lines = jt.split("\n")
    for inc in (pack.get("includes") or [])[:5]:
        assert any(l.strip().endswith(inc.strip()) for l in lines if len(inc) < 70), (inc, lines)


def test_public_quotation_pdf(s):
    tok = S["q"]["public_link"]["token"]
    r = requests.get(f"{API}/public/quotations/{tok}/pdf")
    assert r.status_code == 200 and r.content[:4] == b"%PDF"
    idx, it = itin_pages(pages(r.content))
    assert idx and idx >= 1
    assert_clean(it)


# ---- Agency client with executive ----
def test_agency_exec_header(s):
    q = S["q"]
    r = s.post(f"{API}/quotations", json={
        "client_id": AG_CLIENT, "type": "paquete", "package_id": q["package_id"], "hotel_name": q.get("hotel_selected", ""),
        "dates": q["dates"], "pax": q["pax"], "executive_id": LAURA})
    assert r.status_code == 201, r.text
    nq = r.json()
    S["cleanup"].append(nq["id"])
    S["ag_q"] = nq["id"]
    pdf = s.get(f"{API}/quotations/{nq['id']}/pdf")
    assert pdf.status_code == 200
    idx, it = itin_pages(pages(pdf.content))
    head = it[0][:400]
    assert "AGENCIA" in head and "Agencia Demo SA" in head, head
    assert "Laura Vendedora" in head and "3311111" in head and "laura@agdemo.mx" in head, head
    assert_clean(it)


# ---- important_info ----
def test_important_info_toggle_quotation(s):
    qid = S["ag_q"]
    s.patch(f"{API}/quotations/{qid}", json={"important_info": "TEST72 Lleve identificación oficial"})
    pg = pages(s.get(f"{API}/quotations/{qid}/pdf").content)
    j = "\n".join(pg)
    assert "Información importante" in j and "TEST72 Lleve identificación" in j
    s.patch(f"{API}/quotations/{qid}", json={"important_info": ""})
    assert s.get(f"{API}/quotations/{qid}").json().get("important_info") == ""
    j = "\n".join(pages(s.get(f"{API}/quotations/{qid}/pdf").content))
    assert "Información importante" not in j


def test_important_info_confirmation(s):
    conf_pdf = s.get(f"{API}/booking-confirmations/{CONF}/pdf")
    assert conf_pdf.status_code == 200
    # find quotation id via token endpoint
    qid = "1708d572-1f18-457c-9215-b151f956f0e9"
    orig = s.get(f"{API}/quotations/{qid}").json().get("important_info", "")
    S["restore_ii"] = (qid, orig)
    s.patch(f"{API}/quotations/{qid}", json={"important_info": "TEST72 Info conf"})
    j = "\n".join(pages(s.get(f"{API}/booking-confirmations/{CONF}/pdf").content))
    assert "Información importante" in j and "TEST72 Info conf" in j
    s.patch(f"{API}/quotations/{qid}", json={"important_info": ""})
    j = "\n".join(pages(s.get(f"{API}/booking-confirmations/{CONF}/pdf").content))
    assert "Información importante" not in j


# ---- Booking confirmation ----
def test_confirmation_layout(s):
    r = s.get(f"{API}/booking-confirmations/{CONF}/pdf")
    pg = pages(r.content)
    idx, it = itin_pages(pg)
    assert idx and idx >= 1
    p1 = "\n".join(pg[:idx])
    # two-column general data: label pairs on the same line
    assert re.search(r"Ejecutivo.*Empresa", p1), p1[:800]
    assert re.search(r"Fecha de reservación.*Número de personas", p1)
    assert re.search(r"Pasajero final.*Teléfono del pasajero", p1)
    assert "Precio por persona" in p1 and "Total a pagar" in p1
    assert "US$" not in p1
    assert "Observaciones\n" not in p1 and not re.search(r"Servicio\s+Detalles", p1) and not re.search(r"Pers\.\s+Observaciones", p1)
    assert_clean(it)
    assert "Generado con Routiq" in pg[idx - 1]


def test_public_confirmation_pdf(s):
    r = requests.get(f"{API}/public/booking-confirmation/BnV7-SD1GLxVEZeJOG1Y5w/pdf")
    assert r.status_code == 200 and r.content[:4] == b"%PDF"
    idx, it = itin_pages(pages(r.content))
    assert idx and idx >= 1
    assert_clean(it)


def test_confirmation_agency_no_exec_not_company_name(s):
    r = s.get(f"{API}/booking-confirmations/{CONF_AG_NOEXEC}/pdf")
    assert r.status_code == 200
    p1 = pages(r.content)[0]
    m = re.search(r"Ejecutivo (.*?) Empresa", p1)
    assert m, p1[:600]
    assert "Agencia Demo SA" not in m.group(1), m.group(0)


# ---- Regression other types ----
@pytest.mark.parametrize("qid", ["67883a57-0ff6-46e2-a689-c951b82fae01", "f0506de2-9399-4efd-9d2a-9182d3f6b64a",
                                 "bd34af90-689e-48ac-9a3a-c87b1dd479ab", "d0dc91c2-a9b8-4f46-b87d-fe59615e94fe"])
def test_regression_types(s, qid):
    r = s.get(f"{API}/quotations/{qid}/pdf")
    assert r.status_code == 200 and r.content[:4] == b"%PDF"
    pg = pages(r.content)
    assert "Detalle\n" not in pg[0]
    idx, it = itin_pages(pg)
    if idx is not None:
        assert_clean(it)


@pytest.mark.parametrize("qid", ["56f0203c-f9ad-4b79-bd1b-3145c160ec6c", "ee63edab-0a8f-4fec-8bfc-d31538ed8f53"])
def test_usd_mayorista(s, qid):
    r = s.get(f"{API}/quotations/{qid}/pdf")
    if r.status_code == 404:
        pytest.skip("quotation deleted")
    pg = pages(r.content)
    idx, it = itin_pages(pg)
    pre = "\n".join(pg[:idx] if idx else pg)
    assert "US$" in pre
    if idx is not None:
        assert_clean(it)


def test_all_confirmation_pdfs_render(s):
    ids = ["1c521d0c-b63f-4dff-bede-a4a2811510b5", "c9cdf352-40ed-4777-b5c8-d8289dde3569", "f0e967ef-1b72-4513-a935-6846023d7a42",
           "6b270b1e-9c42-48d1-8436-18c69766ecd2", "9d6a889c-b6ce-4138-9606-c46bad98ef7b"]
    for cid in ids:
        r = s.get(f"{API}/booking-confirmations/{cid}/pdf")
        assert r.status_code == 200, (cid, r.status_code)
        idx, it = itin_pages(pages(r.content))
        if idx is not None:
            assert_clean(it)


# ---- New confirmation: agency client w/o executive_id, 2 executives, legacy agent_name = agency name ----
def test_new_confirmation_agency_no_exec(s):
    q = S["q"]
    r = s.post(f"{API}/quotations", json={
        "client_id": AG_CLIENT, "type": "paquete", "package_id": q["package_id"], "hotel_name": q.get("hotel_selected", ""),
        "dates": q["dates"], "pax": q["pax"], "executive_id": LAURA, "important_info": "TEST72 Importante conf nueva"})
    assert r.status_code == 201, r.text
    nq = r.json(); S["cleanup"].append(nq["id"])
    # API requires executive for agencies; simulate legacy quotation without executive_id directly in DB
    from pymongo import MongoClient
    from dotenv import dotenv_values
    env = dotenv_values("/app/backend/.env")
    MongoClient(env["MONGO_URL"])[env["DB_NAME"]].quotations.update_one({"id": nq["id"]}, {"$set": {"executive_id": None}})
    assert s.patch(f"{API}/quotations/{nq['id']}/state", json={"state": "ganada"}).status_code == 200
    pre = s.get(f"{API}/quotations/{nq['id']}/booking-confirmation").json()
    assert pre.get("agent_name", "") != "Agencia Demo SA", pre.get("agent_name")
    assert pre["agent_company"] == "Agencia Demo SA"
    payload = {k: pre[k] for k in ("agent_phone", "agent_email", "reservation_date", "passenger_name", "passenger_phone",
                                   "num_persons", "lodging", "itinerary", "price_per_person", "total_amount")}
    payload.update({"agent_name": "Agencia Demo SA", "agent_company": "Agencia Demo SA",
                    "services": [{"date": "2026-06-01", "service": "Traslado TEST72", "details": "DetalleXYZ", "persons": "8", "observations": "ObsABC"}]})
    c = s.post(f"{API}/quotations/{nq['id']}/booking-confirmation", json=payload)
    assert c.status_code == 200, c.text
    conf = c.json()
    pg = pages(s.get(f"{API}/booking-confirmations/{conf['id']}/pdf").content)
    p1 = pg[0]
    m = re.search(r"Ejecutivo (.*?) Empresa (.*)", p1)
    assert m and "Agencia Demo SA" not in m.group(1), p1[:600]
    assert "Agencia Demo SA" in m.group(2)
    j = "\n".join(pg)
    assert "DetalleXYZ" in j and "ObsABC" in j and "Traslado TEST72" in j
    assert "Información importante" in j and "TEST72 Importante conf nueva" in j
    # numbers equal to quotation
    full = s.get(f"{API}/quotations/{nq['id']}").json()
    tot = full.get("final_total") if full.get("final_total") is not None else full["total"]
    assert f"{tot:,.2f}" in j
    pub = requests.get(f"{API}/public/booking-confirmation/{conf['token']}/pdf")
    assert pub.status_code == 200
    idx, it = itin_pages(pages(pub.content))
    head = it[0][:300]
    assert "AGENCIA" in head and "Agencia Demo SA" in head
    assert_clean(it)
    S["new_conf"] = conf["id"]
