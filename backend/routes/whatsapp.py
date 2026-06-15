"""WhatsApp (Baileys) integration routes.

The frontend talks only to FastAPI (same-origin /api). FastAPI proxies connect /
QR / status / send to the private Baileys microservice using a shared secret,
and exposes a secret-protected webhook the microservice calls for inbound
messages and connection-status updates.

Session id convention: f"{tenant_id}_{number_id}" (both are hyphenated UUIDs,
so they never contain underscores → safe to rsplit on "_").
"""
import os
import logging
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, Depends, HTTPException, Header, Body
from pydantic import BaseModel

from database import get_db, new_id, now_iso
from auth import require_tenant, require_roles

log = logging.getLogger("routiq.whatsapp")
router = APIRouter()

BAILEYS_URL = os.environ.get("BAILEYS_URL", "").rstrip("/")
BAILEYS_SECRET = os.environ.get("BAILEYS_SHARED_SECRET", "")


def _sid(tenant_id: str, number_id: str) -> str:
    return f"{tenant_id}_{number_id}"


async def _call(method: str, path: str, json: dict | None = None):
    if not BAILEYS_URL:
        raise HTTPException(status_code=503,
                            detail="El servicio de WhatsApp no está configurado. Despliega el microservicio Baileys y define BAILEYS_URL.")
    try:
        async with httpx.AsyncClient(timeout=30) as c:
            r = await c.request(method, f"{BAILEYS_URL}{path}", json=json,
                                headers={"x-baileys-secret": BAILEYS_SECRET})
        return r
    except httpx.HTTPError as e:
        log.warning("baileys call failed: %s", e)
        raise HTTPException(status_code=502, detail="No se pudo contactar el servicio de WhatsApp.")


async def _get_number(db, tenant_id: str, number_id: str) -> dict:
    company = await db.companies.find_one({"id": tenant_id}, {"_id": 0, "whatsapp_numbers": 1})
    for n in (company or {}).get("whatsapp_numbers", []):
        if n.get("id") == number_id:
            return n
    raise HTTPException(status_code=404, detail="Número no encontrado")


# ---------------------------------------------------------------------------
# Number management
# ---------------------------------------------------------------------------
class NumberCreate(BaseModel):
    label: str = ""
    number: str = ""


@router.get("/whatsapp/numbers")
async def list_numbers(user: dict = Depends(require_tenant)):
    db = get_db()
    company = await db.companies.find_one({"id": user["tenant_id"]}, {"_id": 0, "whatsapp_numbers": 1})
    return (company or {}).get("whatsapp_numbers", [])


@router.post("/whatsapp/numbers", status_code=201)
async def add_number(payload: NumberCreate, user: dict = Depends(require_roles("company_admin"))):
    db = get_db()
    wa = {"id": new_id(), "number": payload.number.strip(), "label": payload.label.strip() or "Número", "status": "disconnected"}
    await db.companies.update_one({"id": user["tenant_id"]}, {"$push": {"whatsapp_numbers": wa}})
    return wa


@router.delete("/whatsapp/numbers/{number_id}")
async def delete_number(number_id: str, user: dict = Depends(require_roles("company_admin"))):
    db = get_db()
    if BAILEYS_URL:
        try:
            await _call("POST", f"/sessions/{_sid(user['tenant_id'], number_id)}/logout")
        except Exception:
            pass
    await db.companies.update_one({"id": user["tenant_id"]}, {"$pull": {"whatsapp_numbers": {"id": number_id}}})
    return {"ok": True}


# ---------------------------------------------------------------------------
# Connection lifecycle (proxied to Baileys)
# ---------------------------------------------------------------------------
@router.post("/whatsapp/numbers/{number_id}/connect")
async def connect_number(number_id: str, user: dict = Depends(require_roles("company_admin"))):
    db = get_db()
    await _get_number(db, user["tenant_id"], number_id)
    r = await _call("POST", f"/sessions/{_sid(user['tenant_id'], number_id)}/connect")
    if r.status_code >= 400:
        raise HTTPException(status_code=502, detail="El servicio de WhatsApp no pudo iniciar la conexión.")
    return r.json()


@router.get("/whatsapp/numbers/{number_id}/qr")
async def number_qr(number_id: str, user: dict = Depends(require_tenant)):
    db = get_db()
    await _get_number(db, user["tenant_id"], number_id)
    r = await _call("GET", f"/sessions/{_sid(user['tenant_id'], number_id)}/qr")
    if r.status_code >= 400:
        return {"status": "error", "qr": None}
    data = r.json()
    await _sync_number_status(db, user["tenant_id"], number_id, data.get("status"))
    return data


@router.get("/whatsapp/numbers/{number_id}/status")
async def number_status(number_id: str, user: dict = Depends(require_tenant)):
    db = get_db()
    await _get_number(db, user["tenant_id"], number_id)
    r = await _call("GET", f"/sessions/{_sid(user['tenant_id'], number_id)}/status")
    if r.status_code >= 400:
        return {"status": "error", "jid": None}
    data = r.json()
    await _sync_number_status(db, user["tenant_id"], number_id, data.get("status"))
    return data


@router.post("/whatsapp/numbers/{number_id}/logout")
async def logout_number(number_id: str, user: dict = Depends(require_roles("company_admin"))):
    db = get_db()
    await _get_number(db, user["tenant_id"], number_id)
    r = await _call("POST", f"/sessions/{_sid(user['tenant_id'], number_id)}/logout")
    await _sync_number_status(db, user["tenant_id"], number_id, "disconnected")
    if r.status_code >= 400:
        return {"ok": True, "warning": "session_already_closed"}
    return r.json()


async def _sync_number_status(db, tenant_id: str, number_id: str, status: str | None):
    if not status:
        return
    norm = "connected" if status == "connected" else "disconnected"
    await db.companies.update_one(
        {"id": tenant_id, "whatsapp_numbers.id": number_id},
        {"$set": {"whatsapp_numbers.$.status": norm}},
    )


# ---------------------------------------------------------------------------
# Messaging
# ---------------------------------------------------------------------------
class SendInput(BaseModel):
    number_id: str
    to: str
    text: str


@router.get("/whatsapp/chats")
async def list_chats(number_id: str, user: dict = Depends(require_tenant)):
    db = get_db()
    pipeline = [
        {"$match": {"tenant_id": user["tenant_id"], "number_id": number_id}},
        {"$sort": {"timestamp": -1}},
        {"$group": {
            "_id": "$chat_id",
            "last_text": {"$first": "$text"},
            "last_at": {"$first": "$timestamp"},
            "contact_name": {"$first": "$contact_name"},
            "unread": {"$sum": {"$cond": [{"$and": [{"$eq": ["$from_me", False]}, {"$ne": ["$read", True]}]}, 1, 0]}},
        }},
        {"$sort": {"last_at": -1}},
        {"$limit": 200},
    ]
    rows = await db.whatsapp_messages.aggregate(pipeline).to_list(200)
    # join quotation links for this number
    links = await db.whatsapp_links.find(
        {"tenant_id": user["tenant_id"], "number_id": number_id}, {"_id": 0}).to_list(500)
    link_by_chat = {l["chat_id"]: l for l in links}
    out = []
    for r in rows:
        link = link_by_chat.get(r["_id"])
        out.append({
            "chat_id": r["_id"],
            "phone": (r["_id"] or "").split("@")[0],
            "contact_name": r.get("contact_name") or (r["_id"] or "").split("@")[0],
            "last_text": r.get("last_text", ""),
            "last_at": r.get("last_at", ""),
            "unread": r.get("unread", 0),
            "quotation_id": link["quotation_id"] if link else None,
            "quotation_code": link["quotation_code"] if link else None,
        })
    return out


@router.get("/whatsapp/messages")
async def list_messages(number_id: str, chat_id: str, user: dict = Depends(require_tenant)):
    db = get_db()
    msgs = await db.whatsapp_messages.find(
        {"tenant_id": user["tenant_id"], "number_id": number_id, "chat_id": chat_id},
        {"_id": 0, "tenant_id": 0},
    ).sort("timestamp", 1).to_list(500)
    # mark inbound as read
    await db.whatsapp_messages.update_many(
        {"tenant_id": user["tenant_id"], "number_id": number_id, "chat_id": chat_id, "from_me": False, "read": {"$ne": True}},
        {"$set": {"read": True}},
    )
    return msgs


@router.post("/whatsapp/send")
async def send_message(payload: SendInput, user: dict = Depends(require_tenant)):
    db = get_db()
    await _get_number(db, user["tenant_id"], payload.number_id)
    r = await _call("POST", f"/sessions/{_sid(user['tenant_id'], payload.number_id)}/send",
                    json={"to": payload.to, "text": payload.text})
    if r.status_code == 409:
        raise HTTPException(status_code=409, detail="El número no está conectado. Conéctalo escaneando el QR.")
    if r.status_code >= 400:
        raise HTTPException(status_code=502, detail="No se pudo enviar el mensaje.")
    data = r.json()
    chat_id = data.get("chat_id") or (payload.to if "@" in payload.to else f"{payload.to}@s.whatsapp.net")
    doc = {
        "id": new_id(), "tenant_id": user["tenant_id"], "number_id": payload.number_id,
        "chat_id": chat_id, "message_id": data.get("message_id", ""), "from_me": True,
        "text": payload.text, "contact_name": "",
        "timestamp": datetime.now(timezone.utc).isoformat(), "read": True, "created_at": now_iso(),
    }
    await db.whatsapp_messages.update_one(
        {"tenant_id": user["tenant_id"], "number_id": payload.number_id, "message_id": doc["message_id"]},
        {"$setOnInsert": doc}, upsert=True,
    )
    return {"ok": True, "chat_id": chat_id}


# ---------------------------------------------------------------------------
# Webhook (called by the Baileys microservice — secret-protected)
# ---------------------------------------------------------------------------
@router.post("/whatsapp/webhook")
async def whatsapp_webhook(body: dict = Body(...), x_baileys_secret: str | None = Header(default=None)):
    if not BAILEYS_SECRET or x_baileys_secret != BAILEYS_SECRET:
        raise HTTPException(status_code=401, detail="unauthorized")
    db = get_db()
    sid = body.get("session_id", "")
    if "_" not in sid:
        return {"ok": True}
    tenant_id, number_id = sid.rsplit("_", 1)
    event = body.get("event")

    if event == "status":
        await _sync_number_status(db, tenant_id, number_id, body.get("status"))
        return {"ok": True}

    if event == "message":
        ts = body.get("timestamp")
        iso = datetime.fromtimestamp(int(ts), tz=timezone.utc).isoformat() if ts else now_iso()
        message_id = body.get("message_id", "") or new_id()
        doc = {
            "id": new_id(), "tenant_id": tenant_id, "number_id": number_id,
            "chat_id": body.get("chat_id", ""), "message_id": message_id,
            "from_me": bool(body.get("from_me")), "text": body.get("text", ""),
            "contact_name": body.get("push_name", ""),
            "timestamp": iso, "read": bool(body.get("from_me")), "created_at": now_iso(),
        }
        await db.whatsapp_messages.update_one(
            {"tenant_id": tenant_id, "number_id": number_id, "message_id": message_id},
            {"$setOnInsert": doc}, upsert=True,
        )
        return {"ok": True}

    return {"ok": True}



# ---------------------------------------------------------------------------
# Quotation <-> WhatsApp chat linking (by folio)
# ---------------------------------------------------------------------------
class LinkInput(BaseModel):
    quotation_id: str
    number_id: str
    chat_id: str


@router.post("/whatsapp/link")
async def link_chat(payload: LinkInput, user: dict = Depends(require_tenant)):
    db = get_db()
    quo = await db.quotations.find_one(
        {"id": payload.quotation_id, "tenant_id": user["tenant_id"]}, {"_id": 0, "code": 1})
    if not quo:
        raise HTTPException(status_code=404, detail="Cotización no encontrada")
    await _get_number(db, user["tenant_id"], payload.number_id)
    link = {
        "id": new_id(), "tenant_id": user["tenant_id"],
        "quotation_id": payload.quotation_id, "quotation_code": quo.get("code", ""),
        "number_id": payload.number_id, "chat_id": payload.chat_id,
        "phone": payload.chat_id.split("@")[0], "created_at": now_iso(),
    }
    # one chat ↔ one quotation: replace any existing link for this quotation OR this chat
    await db.whatsapp_links.delete_many({
        "tenant_id": user["tenant_id"],
        "$or": [{"quotation_id": payload.quotation_id},
                {"number_id": payload.number_id, "chat_id": payload.chat_id}],
    })
    await db.whatsapp_links.insert_one(dict(link))
    return {"ok": True, "quotation_code": link["quotation_code"], "phone": link["phone"]}


@router.delete("/whatsapp/link/{quotation_id}")
async def unlink_chat(quotation_id: str, user: dict = Depends(require_tenant)):
    db = get_db()
    await db.whatsapp_links.delete_many(
        {"tenant_id": user["tenant_id"], "quotation_id": quotation_id})
    return {"ok": True}


@router.get("/whatsapp/links/by-quotation/{quotation_id}")
async def link_by_quotation(quotation_id: str, user: dict = Depends(require_tenant)):
    db = get_db()
    link = await db.whatsapp_links.find_one(
        {"tenant_id": user["tenant_id"], "quotation_id": quotation_id}, {"_id": 0})
    return link or {}
