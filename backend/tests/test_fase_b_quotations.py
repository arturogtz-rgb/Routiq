"""Fase B regression — servicios a la carta, contactos, edición, historial,
archivar/eliminar y auditoría. Run: pytest backend/tests/test_fase_b_quotations.py
Requires the backend running and reachable via REACT_APP_BACKEND_URL.
"""
import os
import re
import httpx
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))


def _api_url():
    env = os.path.join(ROOT, "frontend", ".env")
    with open(env) as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL"):
                return line.split("=", 1)[1].strip()
    raise RuntimeError("REACT_APP_BACKEND_URL not found")


API = _api_url() + "/api"
ADMIN = {"email": "admin@aventurate.mx", "password": "Demo2026!"}


@pytest.fixture(scope="module")
def client():
    c = httpx.Client(base_url=API, timeout=30)
    r = c.post("/auth/login", json=ADMIN)
    assert r.status_code == 200, r.text
    yield c
    c.close()


def test_servicios_quotation_lifecycle(client):
    clients = client.get("/clients").json()
    services = client.get("/services").json()
    assert clients and services, "need seed clients & services"
    cid = clients[0]["id"]
    sid = services[0]["id"]

    # create servicios-only quotation with contacts
    payload = {
        "client_id": cid, "type": "servicios",
        "pax": {"adultos": 4, "menores": 0, "rooms": []},
        "services": [{"service_id": sid, "qty": 0}],
        "contacts": {"agency": {"name": "Ag XYZ", "contact": "Ana", "email": "a@x.com"},
                      "traveler": {"name": "Juan", "phone": "555"}},
    }
    r = client.post("/quotations", json=payload)
    assert r.status_code == 201, r.text
    q = r.json()
    assert q["type"] == "servicios"
    assert q["package_snapshot"] is None
    assert q["total"] > 0
    assert q["contacts"]["agency"]["name"] == "Ag XYZ"
    assert [h["action"] for h in q["history"]] == ["created"]
    qid = q["id"]

    # servicios requires at least one service
    bad = client.post("/quotations", json={"client_id": cid, "type": "servicios", "services": []})
    assert bad.status_code == 400

    # edit -> recompute + history
    r = client.patch(f"/quotations/{qid}", json={"notes": "edit", "pax": {"adultos": 8, "menores": 0, "rooms": []}})
    assert r.status_code == 200
    assert "edited" in [h["action"] for h in r.json()["history"]]

    # pdf works for servicios
    r = client.get(f"/quotations/{qid}/pdf")
    assert r.status_code == 200 and r.content[:4] == b"%PDF"

    # archive -> excluded from default list, present in archived list
    assert client.patch(f"/quotations/{qid}/archive", json={"archived": True}).status_code == 200
    default_ids = [x["id"] for x in client.get("/quotations").json()]
    assert qid not in default_ids
    archived_ids = [x["id"] for x in client.get("/quotations", params={"archived": True}).json()]
    assert qid in archived_ids

    # delete -> soft delete + audit
    assert client.delete(f"/quotations/{qid}").status_code == 200
    all_ids = [x["id"] for x in client.get("/quotations", params={"archived": True}).json()]
    assert qid not in all_ids

    audit = client.get("/audit-log").json()
    actions_for_q = [a["action"] for a in audit if a["quotation_id"] == qid]
    assert "archived" in actions_for_q and "deleted" in actions_for_q


def test_won_audit_on_state_change(client):
    clients = client.get("/clients").json()
    packages = client.get("/packages").json()
    assert packages, "need seed packages"
    cid = clients[0]["id"]
    pack = packages[0]
    hotel = pack["hotels"][0]["name"]
    payload = {
        "client_id": cid, "type": "paquete", "package_id": pack["id"], "hotel_name": hotel,
        "dates": {"start": "2026-09-01", "end": "2026-09-04"},
        "pax": {"rooms": [{"ocupacion": "doble", "count": 1}], "menores": 0},
    }
    q = client.post("/quotations", json=payload).json()
    qid = q["id"]
    client.patch(f"/quotations/{qid}/state", json={"state": "ganada"})
    audit = client.get("/audit-log").json()
    won = [a for a in audit if a["quotation_id"] == qid and a["action"] == "won"]
    assert won, "expected a 'won' audit entry"
    client.delete(f"/quotations/{qid}")
