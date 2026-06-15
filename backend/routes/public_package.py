"""Public package preview (no auth) + lead capture, and tenant lead management.

- GET  /public/package/{slug}/{code}          -> branded package data for sharing
- POST /public/package/{slug}/{code}/request  -> client lead ("Quiero este paquete")
- GET  /quote-requests                        -> tenant leads (auth)
- PATCH /quote-requests/{request_id}          -> update lead status (auth)
"""
import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, EmailStr
from fastapi import Depends

from database import get_db, new_id, now_iso
from auth import require_tenant
import notifications

log = logging.getLogger("routiq.public_package")
router = APIRouter()


def _base_price(pack: dict):
    prices = [v for h in (pack.get("hotels") or [])
              for v in (h.get("prices_by_occupancy") or {}).values() if v and v > 0]
    return min(prices) if prices else None


@router.get("/public/package/{slug}/{code}")
async def public_package(slug: str, code: str):
    db = get_db()
    company = await db.companies.find_one({"slug": slug}, {"_id": 0})
    if not company:
        raise HTTPException(status_code=404, detail="Empresa no encontrada")
    pack = await db.packages.find_one({"tenant_id": company["id"], "code": code}, {"_id": 0})
    if not pack or pack.get("status") == "inactive":
        raise HTTPException(status_code=404, detail="Paquete no disponible")
    return {
        "package": {
            "code": pack["code"], "name": pack["name"], "nights": pack.get("nights"),
            "description": pack.get("description", ""), "image_url": pack.get("image_url", ""),
            "itinerary": pack.get("itinerary", []),
            "includes": pack.get("includes", []), "excludes": pack.get("excludes", []),
            "hotels": [{"name": h.get("name", ""), "category": h.get("category", "")}
                       for h in (pack.get("hotels") or [])],
            "base_price": _base_price(pack),
            "currency": company.get("base_currency", "MXN"),
        },
        "company": {
            "name": company.get("name", ""), "slug": company.get("slug", ""),
            "logo_url": company.get("logo_url", ""),
            "primary_color": company.get("primary_color", "#185FA5"),
            "contact_email": company.get("contact_email", ""),
            "contact_phone": company.get("contact_phone", ""),
        },
    }


class PackageRequestInput(BaseModel):
    name: str
    email: EmailStr
    phone: str = ""
    message: str = ""
    travel_date: str = ""
    pax: str = ""
    company_website: str = ""  # honeypot — must stay empty


@router.post("/public/package/{slug}/{code}/request")
async def request_package(slug: str, code: str, payload: PackageRequestInput):
    db = get_db()
    if payload.company_website:  # bot honeypot
        return {"ok": True}
    if not payload.name.strip():
        raise HTTPException(status_code=400, detail="El nombre es obligatorio")
    company = await db.companies.find_one({"slug": slug}, {"_id": 0})
    if not company:
        raise HTTPException(status_code=404, detail="Empresa no encontrada")
    pack = await db.packages.find_one({"tenant_id": company["id"], "code": code}, {"_id": 0})
    if not pack:
        raise HTTPException(status_code=404, detail="Paquete no disponible")
    lead = {
        "id": new_id(), "tenant_id": company["id"],
        "package_id": pack["id"], "package_code": pack["code"], "package_name": pack["name"],
        "name": payload.name.strip(), "email": str(payload.email), "phone": payload.phone.strip(),
        "message": payload.message.strip(), "travel_date": payload.travel_date.strip(),
        "pax": payload.pax.strip(), "status": "new", "created_at": now_iso(),
    }
    await db.quote_requests.insert_one(dict(lead))

    title = f"🌟 Nueva solicitud: {pack['name']}"
    body = f"{lead['name']} solicitó información de {pack['name']} ({pack['code']}). Tel: {lead['phone'] or '—'}."
    await db.notifications.insert_one({
        "tenant_id": company["id"], "quotation_id": None, "kind": "lead",
        "title": title, "body": body, "read": False, "created_at": now_iso(),
    })

    to = company.get("notify_email") or company.get("contact_email") or ""
    if to:
        html = (f"<h2>{title}</h2><p>{body}</p>"
                f"<p><b>Correo:</b> {lead['email']}</p>"
                f"<p><b>Fecha tentativa:</b> {lead['travel_date'] or '—'} · <b>Pax:</b> {lead['pax'] or '—'}</p>"
                f"<p><b>Mensaje:</b> {lead['message'] or '—'}</p>")
        try:
            await notifications.send_email(company, to, title, html)
        except Exception as e:
            log.warning("lead email failed: %s", e)
    return {"ok": True}


# ---------------------------------------------------------------------------
# Tenant lead management (auth)
# ---------------------------------------------------------------------------
@router.get("/quote-requests")
async def list_quote_requests(user: dict = Depends(require_tenant)):
    db = get_db()
    return await db.quote_requests.find(
        {"tenant_id": user["tenant_id"]}, {"_id": 0}).sort("created_at", -1).to_list(300)


class LeadStatusInput(BaseModel):
    status: str


@router.patch("/quote-requests/{request_id}")
async def update_quote_request(request_id: str, payload: LeadStatusInput, user: dict = Depends(require_tenant)):
    db = get_db()
    if payload.status not in ("new", "attended", "archived"):
        raise HTTPException(status_code=400, detail="Estado inválido")
    res = await db.quote_requests.update_one(
        {"id": request_id, "tenant_id": user["tenant_id"]}, {"$set": {"status": payload.status}})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Solicitud no encontrada")
    return await db.quote_requests.find_one({"id": request_id, "tenant_id": user["tenant_id"]}, {"_id": 0})
