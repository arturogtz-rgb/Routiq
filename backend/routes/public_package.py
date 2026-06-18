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


def _base_price(pack: dict, margin_divisor: float = 0.76):
    """Precio público "Desde": tarifa neta mínima del catálogo / divisor de margen."""
    nets = [v for h in (pack.get("hotels") or [])
            for v in (h.get("prices_by_occupancy") or {}).values() if v and v > 0]
    if not nets:
        return None
    net = min(nets)
    return round(net / margin_divisor, 2) if margin_divisor and margin_divisor > 0 else round(net, 2)


def _margin(company: dict) -> float:
    return float((company.get("pricing_config") or {}).get("margin_divisor", 0.76) or 0.76)


@router.get("/public/package/{slug}/{code}")
async def public_package(slug: str, code: str):
    db = get_db()
    company = await db.companies.find_one({"slug": slug}, {"_id": 0})
    if not company:
        raise HTTPException(status_code=404, detail="Empresa no encontrada")
    pack = await db.packages.find_one({"tenant_id": company["id"], "code": code}, {"_id": 0})
    if not pack or pack.get("status") == "inactive":
        raise HTTPException(status_code=404, detail="Paquete no disponible")
    # Record a public view event for catalog analytics (best-effort, never blocks).
    try:
        await db.catalog_views.insert_one({
            "id": new_id(), "tenant_id": company["id"],
            "package_id": pack["id"], "package_code": pack["code"],
            "created_at": now_iso(),
        })
    except Exception as e:
        log.warning("catalog view tracking failed: %s", e)
    return {
        "package": {
            "code": pack["code"], "name": pack["name"], "nights": pack.get("nights"),
            "description": pack.get("description", ""), "image_url": pack.get("image_url", ""),
            "itinerary": pack.get("itinerary", []),
            "includes": pack.get("includes", []), "excludes": pack.get("excludes", []),
            "hotels": [{"name": h.get("name", ""), "category": h.get("category", "")}
                       for h in (pack.get("hotels") or [])],
            "base_price": _base_price(pack, _margin(company)),
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
# Public per-company catalog (no auth) — /c/:slug landing
# ---------------------------------------------------------------------------
@router.get("/public/company/{slug}")
async def public_company_catalog(slug: str):
    db = get_db()
    company = await db.companies.find_one({"slug": slug}, {"_id": 0})
    if not company or company.get("status") == "suspended":
        raise HTTPException(status_code=404, detail="Empresa no encontrada")
    packs = await db.packages.find(
        {"tenant_id": company["id"], "status": {"$ne": "inactive"}}, {"_id": 0}
    ).sort("created_at", -1).to_list(500)
    services_count = await db.services.count_documents(
        {"tenant_id": company["id"], "status": {"$ne": "inactive"}})
    return {
        "company": {
            "name": company.get("name", ""), "slug": company.get("slug", ""),
            "logo_url": company.get("logo_url", ""),
            "primary_color": company.get("primary_color", "#185FA5"),
            "contact_email": company.get("contact_email", ""),
            "contact_phone": company.get("contact_phone", ""),
            "address": company.get("address", ""),
            "catalog_subtitle": company.get("catalog_subtitle", ""),
        },
        "has_services": services_count > 0,
        "packages": [{
            "code": p["code"], "name": p["name"], "nights": p.get("nights"),
            "description": p.get("description", ""), "image_url": p.get("image_url", ""),
            "base_price": _base_price(p, _margin(company)), "currency": company.get("base_currency", "MXN"),
            "hotels_count": len(p.get("hotels") or []),
        } for p in packs],
    }


def _public_company_block(company: dict) -> dict:
    return {
        "name": company.get("name", ""), "slug": company.get("slug", ""),
        "logo_url": company.get("logo_url", ""),
        "primary_color": company.get("primary_color", "#185FA5"),
        "contact_email": company.get("contact_email", ""),
        "contact_phone": company.get("contact_phone", ""),
        "address": company.get("address", ""),
    }


_SVC_CATEGORIES = [("tour", "Tours"), ("traslado", "Traslados"), ("acceso", "Accesos"), ("extra", "Extras")]


@router.get("/public/company/{slug}/services")
async def public_company_services(slug: str):
    """Catálogo público de servicios por categoría (sin auth) — /c/:slug/servicios."""
    db = get_db()
    company = await db.companies.find_one({"slug": slug}, {"_id": 0})
    if not company or company.get("status") == "suspended":
        raise HTTPException(status_code=404, detail="Empresa no encontrada")
    services = await db.services.find(
        {"tenant_id": company["id"], "status": {"$ne": "inactive"}}, {"_id": 0}
    ).sort("name", 1).to_list(1000)
    cur = company.get("base_currency", "MXN")
    groups = []
    for key, label in _SVC_CATEGORIES:
        items = [{
            "name": s.get("name", ""), "description": s.get("description", ""),
            "image_url": s.get("image_url", ""), "unit": s.get("unit", "per_group"),
            "public_price": s.get("public_price", 0), "currency": cur,
        } for s in services if s.get("category") == key]
        if items:
            groups.append({"key": key, "label": label, "items": items})
    return {"company": _public_company_block(company), "groups": groups}


@router.get("/public/company/{slug}/conditions")
async def public_company_conditions(slug: str):
    """Condiciones generales + políticas de cancelación (sin auth) — /c/:slug/condiciones."""
    db = get_db()
    company = await db.companies.find_one({"slug": slug}, {"_id": 0})
    if not company or company.get("status") == "suspended":
        raise HTTPException(status_code=404, detail="Empresa no encontrada")
    return {
        "company": _public_company_block(company),
        "general_conditions": company.get("general_conditions", ""),
        "cancellation_policy": company.get("cancellation_policy", ""),
    }


# ---------------------------------------------------------------------------
# Tenant lead management (auth)
# ---------------------------------------------------------------------------
@router.get("/quote-requests/stats")
async def quote_request_stats(user: dict = Depends(require_tenant)):
    db = get_db()
    from datetime import datetime, timezone, timedelta
    tid = user["tenant_id"]
    leads = await db.quote_requests.find({"tenant_id": tid}, {"_id": 0}).to_list(2000)
    week_ago = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    by_pkg = {}
    for l in leads:
        by_pkg[l.get("package_name", "—")] = by_pkg.get(l.get("package_name", "—"), 0) + 1
    top = sorted(by_pkg.items(), key=lambda x: -x[1])[:5]
    return {
        "total": len(leads),
        "new": sum(1 for l in leads if l.get("status") == "new"),
        "this_week": sum(1 for l in leads if (l.get("created_at") or "") >= week_ago),
        "attended": sum(1 for l in leads if l.get("status") == "attended"),
        "top_packages": [{"name": n, "count": c} for n, c in top],
    }


@router.get("/catalog/analytics")
async def catalog_analytics(period: str = "month", user: dict = Depends(require_tenant)):
    """Per-package public catalog analytics: views, leads, quotations and
    conversion rates (views -> lead -> quotation) for the selected period."""
    from datetime import datetime, timezone, timedelta
    db = get_db()
    tid = user["tenant_id"]
    days = 7 if period == "week" else 30
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

    packs = await db.packages.find(
        {"tenant_id": tid, "status": {"$ne": "inactive"}}, {"_id": 0}
    ).sort("created_at", -1).to_list(500)

    views = await db.catalog_views.find(
        {"tenant_id": tid, "created_at": {"$gte": cutoff}}, {"_id": 0, "package_id": 1}
    ).to_list(20000)
    leads = await db.quote_requests.find(
        {"tenant_id": tid, "created_at": {"$gte": cutoff}}, {"_id": 0, "package_id": 1}
    ).to_list(20000)
    quotes = await db.quotations.find(
        {"tenant_id": tid, "created_at": {"$gte": cutoff}, "deleted": {"$ne": True},
         "from_request": {"$ne": None}, "package_id": {"$ne": None}},
        {"_id": 0, "package_id": 1}
    ).to_list(20000)

    def _count(rows, pid):
        return sum(1 for r in rows if r.get("package_id") == pid)

    def _rate(num, den):
        return round(100.0 * num / den, 1) if den else 0.0

    rows = []
    for p in packs:
        pid = p["id"]
        v, l, qn = _count(views, pid), _count(leads, pid), _count(quotes, pid)
        rows.append({
            "package_id": pid, "code": p["code"], "name": p["name"],
            "views": v, "leads": l, "quotations": qn,
            "view_to_lead": _rate(l, v),
            "lead_to_quote": _rate(qn, l),
            "view_to_quote": _rate(qn, v),
        })
    rows.sort(key=lambda r: (-r["views"], -r["leads"], r["name"]))
    totals = {
        "views": sum(r["views"] for r in rows),
        "leads": sum(r["leads"] for r in rows),
        "quotations": sum(r["quotations"] for r in rows),
    }
    totals["view_to_lead"] = _rate(totals["leads"], totals["views"])
    totals["lead_to_quote"] = _rate(totals["quotations"], totals["leads"])
    return {"period": period, "days": days, "totals": totals, "packages": rows}


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
