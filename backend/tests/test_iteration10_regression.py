"""Iteration 10 — Fase B regression: package quotation + PDF + public link, audit filter."""
import os, httpx, pytest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))


def _api_url():
    with open(os.path.join(ROOT, "frontend", ".env")) as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL"):
                return line.split("=", 1)[1].strip()
    raise RuntimeError("missing url")


API = _api_url() + "/api"
ADMIN = {"email": "admin@aventurate.mx", "password": "Demo2026!"}


@pytest.fixture(scope="module")
def client():
    c = httpx.Client(base_url=API, timeout=30)
    r = c.post("/auth/login", json=ADMIN)
    assert r.status_code == 200
    yield c
    c.close()


def test_package_quotation_with_pdf_and_public_link(client):
    clients = client.get("/clients").json()
    packs = client.get("/packages").json()
    assert clients and packs
    cid = clients[0]["id"]
    pack = packs[0]
    hotel = pack["hotels"][0]["name"]
    payload = {
        "client_id": cid, "type": "paquete", "package_id": pack["id"], "hotel_name": hotel,
        "dates": {"start": "2026-10-01", "end": "2026-10-05"},
        "pax": {"rooms": [{"ocupacion": "doble", "count": 2}], "menores": 1},
    }
    r = client.post("/quotations", json=payload)
    assert r.status_code == 201, r.text
    q = r.json()
    assert q["type"] == "paquete"
    assert q["package_snapshot"] is not None
    assert q["total"] > 0
    qid = q["id"]

    # PDF
    pdf = client.get(f"/quotations/{qid}/pdf")
    assert pdf.status_code == 200 and pdf.content[:4] == b"%PDF"

    # public link
    public_token = q.get("public_token") or q.get("publicToken")
    if public_token:
        # try anonymous client
        anon = httpx.Client(base_url=API, timeout=30)
        r2 = anon.get(f"/quotations/public/{public_token}")
        assert r2.status_code == 200, r2.text
        anon.close()

    # cleanup
    client.delete(f"/quotations/{qid}")


def test_audit_log_visible_to_admin(client):
    r = client.get("/audit-log")
    assert r.status_code == 200
    audit = r.json()
    assert isinstance(audit, list)


def test_audit_log_blocked_for_executive():
    c = httpx.Client(base_url=API, timeout=30)
    r = c.post("/auth/login", json={"email": "ejecutivo@aventurate.mx", "password": "Demo2026!"})
    assert r.status_code == 200
    r2 = c.get("/audit-log")
    assert r2.status_code in (401, 403), r2.text
    c.close()


def test_archived_filter_excludes_default(client):
    clients = client.get("/clients").json()
    services = client.get("/services").json()
    cid = clients[0]["id"]
    sid = services[0]["id"]
    payload = {"client_id": cid, "type": "servicios",
               "pax": {"adultos": 2, "menores": 0, "rooms": []},
               "services": [{"service_id": sid, "qty": 0}]}
    q = client.post("/quotations", json=payload).json()
    qid = q["id"]
    client.patch(f"/quotations/{qid}/archive", json={"archived": True})
    default_ids = [x["id"] for x in client.get("/quotations").json()]
    assert qid not in default_ids
    arch_ids = [x["id"] for x in client.get("/quotations", params={"archived": True}).json()]
    assert qid in arch_ids
    # restore
    client.patch(f"/quotations/{qid}/archive", json={"archived": False})
    restored_ids = [x["id"] for x in client.get("/quotations").json()]
    assert qid in restored_ids
    client.delete(f"/quotations/{qid}")
