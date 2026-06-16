"""Quotation templates: save a custom 'programa personalizado' as a reusable
template and clone it later. Plus 'save as package' to grow the catalog from a
successful custom quotation."""
import logging

from fastapi import APIRouter, Depends, HTTPException

from database import get_db, new_id, now_iso, DEFAULT_PRICING_CONFIG
from auth import require_tenant, require_roles
from models import TemplateCreate, TemplateUpdate, SaveAsTemplateInput, SaveAsPackageInput
from deps import slugify

log = logging.getLogger("routiq")
router = APIRouter()


def _template_doc_from_fields(tenant_id: str, user: dict, name: str, src: dict) -> dict:
    return {
        "id": new_id(), "tenant_id": tenant_id, "name": name.strip(),
        "custom_title": src.get("custom_title", "") or "",
        "custom_items": src.get("custom_items", []) or [],
        "custom_itinerary": src.get("custom_itinerary", []) or [],
        "custom_includes": src.get("custom_includes", []) or [],
        "custom_excludes": src.get("custom_excludes", []) or [],
        "custom_nights": int(src.get("custom_nights", 0) or 0),
        "custom_rooms": int(src.get("custom_rooms", 0) or 0),
        "pax_default": src.get("pax_default") or {
            "adultos": int((src.get("pax") or {}).get("adultos", 0) or 0),
            "menores": int((src.get("pax") or {}).get("menores", 0) or 0),
        },
        "featured": bool(src.get("featured", False)),
        "created_by": user["id"], "created_by_name": user.get("name", ""),
        "created_at": now_iso(), "updated_at": now_iso(),
    }


@router.get("/templates")
async def list_templates(user: dict = Depends(require_tenant)):
    db = get_db()
    return await db.quotation_templates.find(
        {"tenant_id": user["tenant_id"]}, {"_id": 0}
    ).sort([("featured", -1), ("created_at", -1)]).to_list(500)


@router.get("/templates/{template_id}")
async def get_template(template_id: str, user: dict = Depends(require_tenant)):
    db = get_db()
    tpl = await db.quotation_templates.find_one(
        {"id": template_id, "tenant_id": user["tenant_id"]}, {"_id": 0})
    if not tpl:
        raise HTTPException(status_code=404, detail="Plantilla no encontrada")
    return tpl


@router.post("/templates", status_code=201)
async def create_template(payload: TemplateCreate, user: dict = Depends(require_tenant)):
    db = get_db()
    if not payload.custom_items:
        raise HTTPException(status_code=400, detail="La plantilla necesita al menos un concepto")
    src = payload.model_dump()
    doc = _template_doc_from_fields(user["tenant_id"], user, payload.name, src)
    await db.quotation_templates.insert_one(dict(doc))
    return doc


@router.patch("/templates/{template_id}")
async def update_template(template_id: str, payload: TemplateUpdate, user: dict = Depends(require_roles("company_admin"))):
    db = get_db()
    updates = {k: v for k, v in payload.model_dump(exclude_unset=True).items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="Nada que actualizar")
    updates["updated_at"] = now_iso()
    res = await db.quotation_templates.update_one(
        {"id": template_id, "tenant_id": user["tenant_id"]}, {"$set": updates})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Plantilla no encontrada")
    return await db.quotation_templates.find_one(
        {"id": template_id, "tenant_id": user["tenant_id"]}, {"_id": 0})


@router.delete("/templates/{template_id}")
async def delete_template(template_id: str, user: dict = Depends(require_tenant)):
    db = get_db()
    res = await db.quotation_templates.delete_one(
        {"id": template_id, "tenant_id": user["tenant_id"]})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Plantilla no encontrada")
    return {"ok": True}


@router.post("/quotations/{quotation_id}/save-as-template", status_code=201)
async def save_quotation_as_template(quotation_id: str, payload: SaveAsTemplateInput,
                                     user: dict = Depends(require_tenant)):
    db = get_db()
    q = await db.quotations.find_one({"id": quotation_id, "tenant_id": user["tenant_id"]}, {"_id": 0})
    if not q:
        raise HTTPException(status_code=404, detail="Cotización no encontrada")
    if q.get("type") != "personalizado":
        raise HTTPException(status_code=400, detail="Solo las cotizaciones a medida pueden guardarse como plantilla")
    doc = _template_doc_from_fields(user["tenant_id"], user, payload.name, q)
    await db.quotation_templates.insert_one(dict(doc))
    return doc


async def _unique_package_code(db, tenant_id: str, base: str) -> str:
    base = (base or "PROG").upper()[:20] or "PROG"
    code = base
    n = 1
    while await db.packages.find_one({"tenant_id": tenant_id, "code": code}):
        n += 1
        code = f"{base}-{n}"
    return code


async def _build_package_from_custom(db, tenant_id: str, src: dict, margin: float,
                                     nights: int, code_in: str | None, status: str) -> dict:
    """Build a catalog package doc from custom_* fields (quotation or template).
    Descriptive content is copied verbatim; EVERY 'hospedaje' concept becomes a
    hotel pre-filled from its public price (net / margin_divisor). If the program
    has no lodging concept, a single 'Por definir' placeholder hotel is created."""
    def _hotel_from(item: dict) -> dict:
        net = float(item.get("net_price", 0) or 0)
        public = round(net / margin, 2) if margin > 0 else round(net, 2)
        return {
            "name": item.get("name") or "Hotel", "category": "",
            "prices_by_occupancy": {"sencilla": public, "doble": public, "triple": public, "cuadruple": public},
            "minor_price": 0.0, "season_prices": {},
        }

    hospedajes = [it for it in (src.get("custom_items") or []) if it.get("category") == "hospedaje"]
    if hospedajes:
        hotels = [_hotel_from(it) for it in hospedajes]
    else:
        hotels = [{
            "name": "Por definir", "category": "",
            "prices_by_occupancy": {"sencilla": 0.0, "doble": 0.0, "triple": 0.0, "cuadruple": 0.0},
            "minor_price": 0.0, "season_prices": {},
        }]
    title = src.get("custom_title") or src.get("name") or "Programa personalizado"
    base_code = (code_in or slugify(title).replace("-", "").upper()) or "PROG"
    code = await _unique_package_code(db, tenant_id, base_code)
    return {
        "id": new_id(), "tenant_id": tenant_id, "created_at": now_iso(),
        "code": code, "name": title, "nights": int(nights or 0),
        "description": "", "image_url": "",
        "itinerary": src.get("custom_itinerary", []) or [],
        "hotels": hotels,
        "seasons": [], "includes": src.get("custom_includes", []) or [],
        "excludes": src.get("custom_excludes", []) or [],
        "season_start": None, "season_end": None,
        "allowed_start_days": [], "special_departure_dates": [], "status": status,
    }


@router.post("/quotations/{quotation_id}/save-as-package", status_code=201)
async def save_quotation_as_package(quotation_id: str, payload: SaveAsPackageInput,
                                    user: dict = Depends(require_roles("company_admin"))):
    db = get_db()
    q = await db.quotations.find_one({"id": quotation_id, "tenant_id": user["tenant_id"]}, {"_id": 0})
    if not q:
        raise HTTPException(status_code=404, detail="Cotización no encontrada")
    if q.get("type") != "personalizado":
        raise HTTPException(status_code=400, detail="Solo las cotizaciones a medida pueden guardarse como paquete")
    company = await db.companies.find_one({"id": user["tenant_id"]}, {"_id": 0})
    pricing_config = (company or {}).get("pricing_config") or DEFAULT_PRICING_CONFIG
    margin = float(pricing_config.get("margin_divisor", 0.76) or 0.76)
    nights = q.get("nights_total") or q.get("custom_nights") or 0
    doc = await _build_package_from_custom(db, user["tenant_id"], q, margin, nights, payload.code, "active")
    doc["from_custom_quotation"] = quotation_id
    await db.packages.insert_one(dict(doc))
    return doc


@router.post("/templates/{template_id}/publish-as-package", status_code=201)
async def publish_template_as_package(template_id: str, payload: SaveAsPackageInput,
                                      user: dict = Depends(require_roles("company_admin"))):
    """Create a package from a featured template. Created as 'inactive' (NOT yet
    public) so the admin reviews/adjusts occupancy prices in the editor before
    publishing (setting status 'active' makes it appear in /c/:slug)."""
    db = get_db()
    tpl = await db.quotation_templates.find_one(
        {"id": template_id, "tenant_id": user["tenant_id"]}, {"_id": 0})
    if not tpl:
        raise HTTPException(status_code=404, detail="Plantilla no encontrada")
    company = await db.companies.find_one({"id": user["tenant_id"]}, {"_id": 0})
    pricing_config = (company or {}).get("pricing_config") or DEFAULT_PRICING_CONFIG
    margin = float(pricing_config.get("margin_divisor", 0.76) or 0.76)
    doc = await _build_package_from_custom(
        db, user["tenant_id"], tpl, margin, tpl.get("custom_nights", 0), payload.code, "inactive")
    doc["from_template"] = template_id
    await db.packages.insert_one(dict(doc))
    return doc
