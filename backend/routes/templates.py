"""Quotation templates: save a custom 'programa personalizado' as a reusable
template and clone it later. Plus 'save as package' to grow the catalog from a
successful custom quotation."""
import logging

from fastapi import APIRouter, Depends, HTTPException

from database import get_db, new_id, now_iso, DEFAULT_PRICING_CONFIG
from auth import require_tenant, require_roles
from models import TemplateCreate, SaveAsTemplateInput, SaveAsPackageInput
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
        "created_by": user["id"], "created_by_name": user.get("name", ""),
        "created_at": now_iso(), "updated_at": now_iso(),
    }


@router.get("/templates")
async def list_templates(user: dict = Depends(require_tenant)):
    db = get_db()
    return await db.quotation_templates.find(
        {"tenant_id": user["tenant_id"]}, {"_id": 0}).sort("created_at", -1).to_list(500)


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


@router.post("/quotations/{quotation_id}/save-as-package", status_code=201)
async def save_quotation_as_package(quotation_id: str, payload: SaveAsPackageInput,
                                    user: dict = Depends(require_roles("company_admin"))):
    """Create a catalog package from a successful custom quotation. Descriptive
    content (name, nights, itinerary, includes/excludes) is copied verbatim; a
    single hotel is pre-filled from the hospedaje concept's public price so the
    admin only needs to fine-tune occupancy prices in the editor."""
    db = get_db()
    q = await db.quotations.find_one({"id": quotation_id, "tenant_id": user["tenant_id"]}, {"_id": 0})
    if not q:
        raise HTTPException(status_code=404, detail="Cotización no encontrada")
    if q.get("type") != "personalizado":
        raise HTTPException(status_code=400, detail="Solo las cotizaciones a medida pueden guardarse como paquete")

    company = await db.companies.find_one({"id": user["tenant_id"]}, {"_id": 0})
    pricing_config = (company or {}).get("pricing_config") or DEFAULT_PRICING_CONFIG
    margin = float(pricing_config.get("margin_divisor", 0.76) or 0.76)

    # Pre-fill a single hotel from the first 'hospedaje' concept (public price).
    hosp = next((it for it in (q.get("custom_items") or []) if it.get("category") == "hospedaje"), None)
    if hosp:
        net = float(hosp.get("net_price", 0) or 0)
        public = round(net / margin, 2) if margin > 0 else round(net, 2)
        hotel_name = hosp.get("name") or "Hotel"
    else:
        public = 0.0
        hotel_name = "Por definir"
    hotel = {
        "name": hotel_name, "category": "",
        "prices_by_occupancy": {"sencilla": public, "doble": public, "triple": public, "cuadruple": public},
        "minor_price": 0.0, "season_prices": {},
    }

    title = q.get("custom_title") or "Programa personalizado"
    base_code = (payload.code or slugify(title).replace("-", "").upper()) or "PROG"
    code = await _unique_package_code(db, user["tenant_id"], base_code)

    doc = {
        "id": new_id(), "tenant_id": user["tenant_id"], "created_at": now_iso(),
        "code": code, "name": title, "nights": int(q.get("nights_total") or q.get("custom_nights") or 0),
        "description": "", "image_url": "",
        "itinerary": q.get("custom_itinerary", []) or [],
        "hotels": [hotel],
        "seasons": [], "includes": q.get("custom_includes", []) or [],
        "excludes": q.get("custom_excludes", []) or [],
        "season_start": None, "season_end": None,
        "allowed_start_days": [], "special_departure_dates": [], "status": "active",
        "from_custom_quotation": quotation_id,
    }
    await db.packages.insert_one(dict(doc))
    return doc
