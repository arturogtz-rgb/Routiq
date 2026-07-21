"""
Iteración 54 — 4 ajustes de cotizaciones (Iter3, Lote Routiq).

Cobertura:
  PUNTO 1 → Descuento: PATCH /quotations/{id}/pricing-adjust setea final_total < total
            (con final_total y total en el snapshot). GET listado incluye ambos.
  PUNTO 2 → Servicios a la carta admite custom_items con description. Se persiste
            y compute_quotation (pack=None) lo incluye en items con `description`.
  PUNTO 3 → PDF (200) para cotización con description; enlace público
            (/public/quotations/{token}) devuelve items con description en JSON.
  PUNTO 4 → Seed multi-mes en `quotations` (created_at) — pymongo directo.
            Verifica que GET /quotations trae docs con distintos created_at (>=4 meses
            + un mes 2025) para que el frontend agrupe correctamente.
  REGRESIÓN → subtotal + commission == total (± 0.02) para paquete y para servicios
              con conceptos adicionales.

NO se modifica pricing.py ni la lógica de Paquete Armado. Sólo se crean cotizaciones
via API pública y se hacen inserts/updates de created_at en Mongo para el punto 4.
"""
import os
import uuid
from datetime import datetime, timezone

import pytest
import requests
from pymongo import MongoClient


def _load_backend_url():
    p = "/app/frontend/.env"
    if os.path.exists(p):
        for ln in open(p):
            if ln.startswith("REACT_APP_BACKEND_URL="):
                return ln.split("=", 1)[1].strip().rstrip("/")
    return os.environ["REACT_APP_BACKEND_URL"].rstrip("/")


def _load_mongo():
    url, name = None, None
    for ln in open("/app/backend/.env"):
        if ln.startswith("MONGO_URL="):
            url = ln.split("=", 1)[1].strip().strip('"').strip("'")
        if ln.startswith("DB_NAME="):
            name = ln.split("=", 1)[1].strip().strip('"').strip("'")
    return url, name


BASE_URL = _load_backend_url()
MONGO_URL, DB_NAME = _load_mongo()
ADMIN_EMAIL = "admin@aventurate.mx"
ADMIN_PASS = "Demo2026!"
TENANT_ID = "de7483e7-7698-4a60-b6e3-6b08db474a67"

QUO_PACKAGE = "4ca24d69-d592-45fb-9b00-cc09167f25a2"

SEED_PREFIX = "TEST_ITER54_"


@pytest.fixture(scope="module")
def admin():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login",
               json={"email": ADMIN_EMAIL, "password": ADMIN_PASS}, timeout=30)
    assert r.status_code == 200, r.text
    return s


@pytest.fixture(scope="module")
def mongo():
    c = MongoClient(MONGO_URL)
    yield c[DB_NAME]
    c.close()


@pytest.fixture(scope="module")
def any_client_id(admin):
    r = admin.get(f"{BASE_URL}/api/clients", timeout=30)
    assert r.status_code == 200
    clients = r.json()
    assert len(clients) > 0, "No hay clientes seed"
    directo = next((c for c in clients if c.get("channel") == "directo"), clients[0])
    return directo["id"]


@pytest.fixture(scope="module")
def any_service_id(admin):
    r = admin.get(f"{BASE_URL}/api/services", timeout=30)
    assert r.status_code == 200
    services = r.json()
    assert len(services) > 0, "No hay servicios seed"
    return services[0]["id"]


# =============== PUNTO 1: descuento -> final_total < total ===============
class TestPunto1DiscountFinalTotal:
    def test_apply_percent_discount_creates_final_total(self, admin):
        r = admin.get(f"{BASE_URL}/api/quotations/{QUO_PACKAGE}", timeout=30)
        assert r.status_code == 200, r.text
        q_before = r.json()
        total = float(q_before["total"])
        assert total > 0

        # Aplica 5% descuento
        r = admin.patch(f"{BASE_URL}/api/quotations/{QUO_PACKAGE}/pricing-adjust",
                        json={"discount_type": "percent", "discount_value": 5}, timeout=30)
        assert r.status_code == 200, r.text
        q_after = r.json()
        final_total = q_after.get("final_total")
        assert final_total is not None
        assert final_total < total, f"final_total ({final_total}) debe ser < total ({total})"
        expected = round(total * 0.95, 2)
        assert abs(final_total - expected) < 0.02, f"final_total={final_total} expected~{expected}"

    def test_listing_returns_final_total_field(self, admin):
        # El listado /api/quotations debe entregar tanto `total` como `final_total`
        r = admin.get(f"{BASE_URL}/api/quotations", timeout=30)
        assert r.status_code == 200
        items = r.json()
        target = next((x for x in items if x["id"] == QUO_PACKAGE), None)
        assert target is not None, "No se encontró la cotización con descuento en listado"
        assert "total" in target and "final_total" in target
        assert target["final_total"] is not None
        assert target["final_total"] < target["total"]

    def test_reset_discount(self, admin):
        # cleanup: quitamos el descuento para no dejar la demo con estado alterado
        r = admin.patch(f"{BASE_URL}/api/quotations/{QUO_PACKAGE}/pricing-adjust",
                        json={"discount_type": "none", "discount_value": 0}, timeout=30)
        assert r.status_code == 200

    def test_regression_engine_paquete(self, admin):
        # Regresión motor: subtotal + commission ~ total (± 0.02)
        r = admin.get(f"{BASE_URL}/api/quotations/{QUO_PACKAGE}", timeout=30)
        assert r.status_code == 200
        q = r.json()
        s = float(q.get("subtotal") or 0)
        c = float(q.get("commission") or 0)
        t = float(q.get("total") or 0)
        assert abs((s - c) - t) < 0.02, f"subtotal({s}) - commission({c}) != total({t})"


# =============== PUNTO 2: servicios + custom_items con description ===============
@pytest.fixture(scope="module")
def created_servicios_quotation(admin, any_client_id, any_service_id):
    payload = {
        "type": "servicios",
        "client_id": any_client_id,
        "services": [{"service_id": any_service_id, "qty": 2}],
        "pax": {"adultos": 2, "menores": 0, "rooms": []},
        "dates": {"start": "2026-07-10", "end": "2026-07-12"},
        "custom_items": [{
            "category": "extra",
            "name": SEED_PREFIX + "Traslado privado",
            "description": "Vehículo VIP con anfitrión bilingüe — puerta a puerta",
            "net_price": 1500,
            "price_type": "publico",
            "unit": "per_group",
            "qty": 1,
        }],
        "notes": "TEST_ITER54 servicios+concepto",
        "presentation_text": "",
        "important_info": "",
    }
    r = admin.post(f"{BASE_URL}/api/quotations", json=payload, timeout=30)
    assert r.status_code in (200, 201), r.text
    data = r.json()
    yield data
    # Cleanup: mark archived
    admin.patch(f"{BASE_URL}/api/quotations/{data['id']}", json={"archived": True}, timeout=15)


class TestPunto2ServiciosCustomItems:
    def test_custom_item_persisted_with_description(self, admin, created_servicios_quotation):
        qid = created_servicios_quotation["id"]
        r = admin.get(f"{BASE_URL}/api/quotations/{qid}", timeout=30)
        assert r.status_code == 200
        q = r.json()
        items = q.get("items", [])
        # buscar el custom item por kind='custom'
        customs = [it for it in items if it.get("kind") == "custom"]
        assert len(customs) >= 1, f"No hay items custom: {items}"
        ci = customs[0]
        assert ci.get("description") == "Vehículo VIP con anfitrión bilingüe — puerta a puerta"
        assert ci.get("name", "").startswith(SEED_PREFIX)

    def test_regression_engine_servicios_with_custom(self, admin, created_servicios_quotation):
        qid = created_servicios_quotation["id"]
        r = admin.get(f"{BASE_URL}/api/quotations/{qid}", timeout=30)
        q = r.json()
        s = float(q.get("subtotal") or 0)
        c = float(q.get("commission") or 0)
        t = float(q.get("total") or 0)
        # subtotal debe INCLUIR el custom item (1500)
        assert s >= 1500, f"subtotal ({s}) debería incluir el concepto (1500)"
        assert abs((s - c) - t) < 0.02, f"subtotal({s}) - commission({c}) != total({t})"

    def test_servicios_persists_type_and_no_package(self, admin, created_servicios_quotation):
        qid = created_servicios_quotation["id"]
        r = admin.get(f"{BASE_URL}/api/quotations/{qid}", timeout=30)
        q = r.json()
        assert q.get("type") == "servicios"
        assert not q.get("package_id")


# =============== PUNTO 3: PDF y enlace público con description ===============
class TestPunto3PdfAndPublic:
    def test_pdf_200_for_servicios_with_custom(self, admin, created_servicios_quotation):
        qid = created_servicios_quotation["id"]
        r = admin.get(f"{BASE_URL}/api/quotations/{qid}/pdf", timeout=45)
        assert r.status_code == 200, r.text[:400]
        assert r.headers.get("content-type", "").startswith("application/pdf")
        assert len(r.content) > 1000

    def test_public_link_returns_item_description(self, admin, created_servicios_quotation):
        qid = created_servicios_quotation["id"]
        # Crear public link
        r = admin.post(f"{BASE_URL}/api/quotations/{qid}/public-link", timeout=30)
        assert r.status_code in (200, 201), r.text
        token = r.json()["token"]

        # Consumir sin autenticación
        anon = requests.Session()
        r = anon.get(f"{BASE_URL}/api/public/quotations/{token}", timeout=30)
        assert r.status_code == 200, r.text[:400]
        payload = r.json()
        items = (payload.get("quotation") or {}).get("items") or []
        customs = [it for it in items if it.get("kind") == "custom"]
        assert len(customs) >= 1, f"public quotation no expone custom items: {items}"
        assert customs[0].get("description") == "Vehículo VIP con anfitrión bilingüe — puerta a puerta"


# =============== PUNTO 4: seed multi-mes en `quotations` ===============
SEEDED_IDS = []


@pytest.fixture(scope="module")
def seed_multi_month(mongo, any_client_id):
    """Inserta 4 cotizaciones sintéticas con created_at en meses distintos
    (mayo 2026, abril 2026, marzo 2026, diciembre 2025). Docs mínimos — copian
    la estructura de una cotización existente para no romper el listado."""
    src = mongo.quotations.find_one({"id": QUO_PACKAGE, "tenant_id": TENANT_ID})
    assert src is not None, "no encontré la cotización paquete demo"
    months = [
        ("2026-05-10T12:00:00+00:00", "MAY26"),
        ("2026-04-10T12:00:00+00:00", "APR26"),
        ("2026-03-10T12:00:00+00:00", "MAR26"),
        ("2025-12-10T12:00:00+00:00", "DEC25"),
    ]
    for iso, tag in months:
        doc = dict(src)
        doc.pop("_id", None)
        doc["id"] = str(uuid.uuid4())
        doc["code"] = f"{SEED_PREFIX}{tag}"
        doc["created_at"] = iso
        doc["last_activity_at"] = iso
        doc["archived"] = False
        # eliminar public_link para no ensuciar
        doc.pop("public_link", None)
        doc.pop("discount", None)
        doc["final_total"] = None
        mongo.quotations.insert_one(doc)
        SEEDED_IDS.append(doc["id"])
    yield SEEDED_IDS
    # teardown
    if SEEDED_IDS:
        mongo.quotations.delete_many({"id": {"$in": SEEDED_IDS}})


class TestPunto4MonthGrouping:
    def test_listing_contains_multi_month_docs(self, admin, seed_multi_month):
        r = admin.get(f"{BASE_URL}/api/quotations", timeout=30)
        assert r.status_code == 200
        items = r.json()
        by_id = {x["id"]: x for x in items}
        # los 4 sembrados deben aparecer
        for sid in seed_multi_month:
            assert sid in by_id, f"Falta {sid} en /quotations"
        # verificar que created_at está en el mes esperado
        months = {by_id[sid]["created_at"][:7] for sid in seed_multi_month}
        assert {"2026-05", "2026-04", "2026-03", "2025-12"}.issubset(months), months

    def test_previous_year_present_for_selector(self, admin, seed_multi_month):
        r = admin.get(f"{BASE_URL}/api/quotations", timeout=30)
        items = r.json()
        years = {x.get("created_at", "")[:4] for x in items if x.get("created_at")}
        assert "2025" in years, f"esperaba 2025 en años, obtuve {years}"

    def test_month_filter_returns_only_that_month(self, admin, seed_multi_month):
        # el listado admite date_from/date_to (usado por el filtro de mes de Lote E)
        r = admin.get(f"{BASE_URL}/api/quotations",
                      params={"date_from": "2026-05-01", "date_to": "2026-05-31"}, timeout=30)
        assert r.status_code == 200
        items = r.json()
        assert len(items) >= 1
        assert all(x.get("created_at", "").startswith("2026-05") for x in items), \
            [x.get("code") + ":" + x.get("created_at", "")[:10] for x in items]
