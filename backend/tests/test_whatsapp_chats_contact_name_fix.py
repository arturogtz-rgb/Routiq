"""
Iteración post-2 (fix quirúrgico): GET /api/whatsapp/chats debe devolver
contact_name = último push_name NO vacío del chat, en lugar de $first sobre
mensajes desc (que perdía el nombre cuando el último mensaje era saliente con
contact_name="").

Datos sembrados por /app/backend/seed_chat_fix_test.py:
- number_id = 975c561c-b0ee-45f6-b59e-de2653d46f6f
- chat_id   = 5213339990000@s.whatsapp.net
- entrante (más antiguo, -10min) contact_name="Juan Test", text="Hola, me interesa"
- saliente (más reciente)        contact_name="",           text="Con gusto, te comparto info"

Se verifica:
  1. FIX principal: contact_name == "Juan Test" (no el número), last_text/last_at
     siguen siendo del mensaje más reciente (saliente).
  2. Regresiones (chat "solo saliente", "solo entrante nombrado", CRM priority,
     is_group / hidden) — se insertan datos temporales y se limpian al final.
"""
import os
import time
from datetime import datetime, timezone, timedelta

import pytest
import requests
from pymongo import MongoClient

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://price-sync-alert.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

TENANT_ID = "de7483e7-7698-4a60-b6e3-6b08db474a67"
NUMBER_ID = "975c561c-b0ee-45f6-b59e-de2653d46f6f"
SEED_CHAT = "5213339990000@s.whatsapp.net"

# Chats de prueba propios (además del sembrado externo)
CHAT_OUTBOUND_ONLY = "5213338880001@s.whatsapp.net"     # solo saliente vacío -> fallback phone
CHAT_INBOUND_NAMED = "5213338880002@s.whatsapp.net"     # último es entrante con nombre
CHAT_CRM_MATCH     = "5213338880003@s.whatsapp.net"     # cruza con cliente CRM propio
CHAT_GROUP         = "1203630001234567@g.us"            # grupo (para F4)

TEST_CLIENT_ID   = "TEST_wa_client_iter53"
TEST_CLIENT_NAME = "TEST WA Cliente CRM"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def mongo_db():
    url = os.environ.get("MONGO_URL")
    dbname = os.environ.get("DB_NAME")
    assert url and dbname, "MONGO_URL / DB_NAME no configurados en backend/.env"
    return MongoClient(url)[dbname]


@pytest.fixture(scope="module")
def api_client():
    s = requests.Session()
    # login admin_aventurate
    r = s.post(f"{API}/auth/login", json={"email": "admin@aventurate.mx", "password": "Demo2026!"}, timeout=15)
    assert r.status_code == 200, f"Login falló: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="module", autouse=True)
def seed_and_cleanup(mongo_db):
    """Siembra chats extra + cliente CRM para regresiones. Limpia al final.
    NO toca el seed principal ('5213339990000') porque el test principal lo usa
    y seed_chat_fix_test.py ya lo colocó.
    """
    db = mongo_db
    # Re-siembra el chat principal por si otro test lo tocó (idempotente)
    base = datetime.now(timezone.utc)
    db.whatsapp_messages.delete_many({"chat_id": SEED_CHAT, "number_id": NUMBER_ID})
    db.whatsapp_messages.insert_many([
        {"id": "t1", "message_id": "m1", "tenant_id": TENANT_ID, "number_id": NUMBER_ID, "chat_id": SEED_CHAT,
         "from_me": False, "text": "Hola, me interesa", "contact_name": "Juan Test",
         "timestamp": (base - timedelta(minutes=10)).isoformat(),
         "created_at": (base - timedelta(minutes=10)).isoformat(), "read": True},
        {"id": "t2", "message_id": "m2", "tenant_id": TENANT_ID, "number_id": NUMBER_ID, "chat_id": SEED_CHAT,
         "from_me": True, "text": "Con gusto, te comparto info", "contact_name": "",
         "timestamp": base.isoformat(), "created_at": base.isoformat(), "read": True},
    ])

    # Chat OUTBOUND_ONLY (todos contact_name vacíos)
    db.whatsapp_messages.delete_many({"chat_id": CHAT_OUTBOUND_ONLY, "number_id": NUMBER_ID})
    db.whatsapp_messages.insert_many([
        {"id": "o1", "message_id": "o1m", "tenant_id": TENANT_ID, "number_id": NUMBER_ID,
         "chat_id": CHAT_OUTBOUND_ONLY, "from_me": True, "text": "hola", "contact_name": "",
         "timestamp": (base - timedelta(minutes=5)).isoformat(),
         "created_at": (base - timedelta(minutes=5)).isoformat(), "read": True},
    ])

    # Chat INBOUND_NAMED (último es entrante con nombre)
    db.whatsapp_messages.delete_many({"chat_id": CHAT_INBOUND_NAMED, "number_id": NUMBER_ID})
    db.whatsapp_messages.insert_many([
        {"id": "i1", "message_id": "i1m", "tenant_id": TENANT_ID, "number_id": NUMBER_ID,
         "chat_id": CHAT_INBOUND_NAMED, "from_me": False, "text": "Buen día",
         "contact_name": "Maria Regresion",
         "timestamp": (base - timedelta(minutes=3)).isoformat(),
         "created_at": (base - timedelta(minutes=3)).isoformat(), "read": False},
    ])

    # Chat CRM_MATCH (push_name distinto al CRM; el CRM debe ganar)
    db.whatsapp_messages.delete_many({"chat_id": CHAT_CRM_MATCH, "number_id": NUMBER_ID})
    db.whatsapp_messages.insert_many([
        {"id": "c1", "message_id": "c1m", "tenant_id": TENANT_ID, "number_id": NUMBER_ID,
         "chat_id": CHAT_CRM_MATCH, "from_me": False, "text": "hola crm",
         "contact_name": "PushName IGNORAR",
         "timestamp": (base - timedelta(minutes=2)).isoformat(),
         "created_at": (base - timedelta(minutes=2)).isoformat(), "read": False},
    ])

    # Chat GROUP (F4: is_group=true)
    db.whatsapp_messages.delete_many({"chat_id": CHAT_GROUP, "number_id": NUMBER_ID})
    db.whatsapp_messages.insert_many([
        {"id": "g1", "message_id": "g1m", "tenant_id": TENANT_ID, "number_id": NUMBER_ID,
         "chat_id": CHAT_GROUP, "from_me": False, "text": "mensaje de grupo",
         "contact_name": "Alguien del grupo",
         "timestamp": (base - timedelta(minutes=1)).isoformat(),
         "created_at": (base - timedelta(minutes=1)).isoformat(), "read": True},
    ])

    # Cliente CRM propio para probar F2 (teléfono últimos 10 dígitos = 3338880003)
    db.clients.delete_many({"id": TEST_CLIENT_ID})
    db.clients.insert_one({
        "id": TEST_CLIENT_ID, "tenant_id": TENANT_ID,
        "name": TEST_CLIENT_NAME, "phone": "3338880003",
        "executives": [], "created_at": base.isoformat(),
    })

    # Ocultar el chat de grupo para probar 'hidden' F4
    db.whatsapp_chat_prefs.delete_many(
        {"tenant_id": TENANT_ID, "number_id": NUMBER_ID, "chat_id": CHAT_GROUP})
    db.whatsapp_chat_prefs.insert_one({
        "tenant_id": TENANT_ID, "number_id": NUMBER_ID, "chat_id": CHAT_GROUP,
        "hidden": True, "updated_at": base.isoformat(),
    })

    yield

    # Teardown
    db.whatsapp_messages.delete_many({"number_id": NUMBER_ID, "chat_id": {"$in": [
        CHAT_OUTBOUND_ONLY, CHAT_INBOUND_NAMED, CHAT_CRM_MATCH, CHAT_GROUP,
    ]}})
    db.whatsapp_chat_prefs.delete_many(
        {"tenant_id": TENANT_ID, "number_id": NUMBER_ID, "chat_id": CHAT_GROUP})
    db.clients.delete_many({"id": TEST_CLIENT_ID})
    # No borramos el chat SEED_CHAT: es dato de test central que main agent puede reusar.


@pytest.fixture(scope="module")
def chats(api_client):
    r = api_client.get(f"{API}/whatsapp/chats", params={"number_id": NUMBER_ID}, timeout=15)
    assert r.status_code == 200, f"chats endpoint status={r.status_code} body={r.text}"
    data = r.json()
    assert isinstance(data, list)
    return {c["chat_id"]: c for c in data}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
def test_fix_principal_contact_name_es_ultimo_no_vacio(chats):
    """FIX: chat con último mensaje saliente vacío debe conservar 'Juan Test'."""
    assert SEED_CHAT in chats, f"Chat sembrado no aparece en la lista. Keys: {list(chats.keys())}"
    c = chats[SEED_CHAT]
    assert c["contact_name"] == "Juan Test", (
        f"contact_name esperado 'Juan Test', recibido '{c['contact_name']}'"
    )
    # last_text/last_at siguen siendo del mensaje MÁS RECIENTE (saliente).
    assert c["last_text"] == "Con gusto, te comparto info", f"last_text inesperado: {c['last_text']}"
    assert c["last_at"], "last_at no debe estar vacío"


def test_estructura_endpoint_completa(chats):
    """Cada item debe tener todos los campos documentados."""
    required = {"chat_id", "phone", "is_group", "hidden", "contact_name",
                "last_text", "last_at", "unread", "quotation_id", "quotation_code"}
    for cid, item in chats.items():
        missing = required - set(item.keys())
        assert not missing, f"Chat {cid} falta campos: {missing}"


def test_regresion_solo_saliente_fallback_phone(chats):
    """Todos los contact_name vacíos -> el endpoint hace fallback a phone."""
    assert CHAT_OUTBOUND_ONLY in chats
    c = chats[CHAT_OUTBOUND_ONLY]
    # phone es la parte antes de '@'
    assert c["phone"] == "5213338880001"
    # Como CRM no matchea y push_name está vacío, fallback = phone
    assert c["contact_name"] == "5213338880001", (
        f"Fallback a phone esperado, recibido '{c['contact_name']}'"
    )


def test_regresion_ultimo_entrante_conserva_nombre(chats):
    """Último mensaje es entrante con nombre → sigue mostrando ese nombre."""
    assert CHAT_INBOUND_NAMED in chats
    c = chats[CHAT_INBOUND_NAMED]
    assert c["contact_name"] == "Maria Regresion", f"got {c['contact_name']}"
    assert c["unread"] == 1, f"unread esperado 1 (msg entrante no leído), got {c['unread']}"


def test_regresion_f2_crm_gana_sobre_push_name(chats):
    """CRM name ('TEST WA Cliente CRM') debe tener prioridad sobre push_name."""
    assert CHAT_CRM_MATCH in chats
    c = chats[CHAT_CRM_MATCH]
    assert c["contact_name"] == TEST_CLIENT_NAME, (
        f"CRM debía ganar sobre push_name. contact_name={c['contact_name']}"
    )


def test_regresion_f4_grupos_y_hidden(chats):
    """is_group y hidden se calculan correctamente. NO se modificaron."""
    assert CHAT_GROUP in chats
    c = chats[CHAT_GROUP]
    assert c["is_group"] is True, "is_group debe ser True para @g.us"
    assert c["hidden"] is True, "hidden debe reflejar whatsapp_chat_prefs"
    # Un chat no-grupo debe tener is_group=False
    c2 = chats[SEED_CHAT]
    assert c2["is_group"] is False
    assert c2["hidden"] is False  # no hay pref


def test_orden_last_at_descendente(chats):
    """Los chats se devuelven ordenados por last_at desc."""
    lst = list(chats.values())
    last_ats = [c["last_at"] for c in lst]
    assert last_ats == sorted(last_ats, reverse=True), (
        f"Chats no vienen ordenados desc por last_at: {last_ats}"
    )


def test_auth_requerida():
    """Sin cookie de sesión, /api/whatsapp/chats debe rechazar."""
    r = requests.get(f"{API}/whatsapp/chats", params={"number_id": NUMBER_ID}, timeout=10)
    assert r.status_code in (401, 403), f"Se esperaba 401/403, got {r.status_code}"
