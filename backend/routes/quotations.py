"""Quotation routes: CRUD, state, pricing-adjust, archive/delete, PDF,
public-link management and AI assistant endpoints."""
import io
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from database import get_db, new_id, now_iso, DEFAULT_PRICING_CONFIG
from auth import require_tenant
from models import (
    QuotationCreate, QuotationStateUpdate, QuotationUpdate,
    QuotationPricingAdjust, QuotationArchive, PresentationInput,
)
from pricing import compute_quotation, compute_custom_quotation
from pdf_generator import generate_quotation_pdf
import ai_service
from deps import (
    _load_services_catalog, _next_quotation_code, _append_history, _record_audit, _apply_discount,
)

log = logging.getLogger("routiq")
router = APIRouter()


async def _check_ai_enabled(tenant_id: str):
    company = await get_db().companies.find_one({"id": tenant_id}, {"_id": 0, "ai_enabled": 1})
    if not bool((company or {}).get("ai_enabled", True)):
        raise HTTPException(
            status_code=403,
            detail="La IA operativa no está incluida en tu plan. Solicita una actualización al administrador de Routiq.",
        )


@router.get("/quotations")
async def list_quotations(state: str | None = None, archived: bool = False, user: dict = Depends(require_tenant)):
    db = get_db()
    q = {"tenant_id": user["tenant_id"], "deleted": {"$ne": True}}
    if archived:
        q["archived"] = True
    else:
        q["archived"] = {"$ne": True}
    if state:
        q["state"] = state
    items = await db.quotations.find(q, {"_id": 0}).sort("created_at", -1).to_list(500)
    now = datetime.now(timezone.utc)
    for it in items:
        try:
            last = datetime.fromisoformat(it.get("last_activity_at", it.get("created_at")))
            it["days_idle"] = (now - last).days
        except Exception:
            it["days_idle"] = 0
    return items


@router.get("/quotations/{quotation_id}")
async def get_quotation(quotation_id: str, user: dict = Depends(require_tenant)):
    db = get_db()
    q = await db.quotations.find_one({"id": quotation_id, "tenant_id": user["tenant_id"]}, {"_id": 0})
    if not q:
        raise HTTPException(status_code=404, detail="Cotización no encontrada")
    return q


@router.post("/quotations", status_code=201)
async def create_quotation(payload: QuotationCreate, user: dict = Depends(require_tenant)):
    db = get_db()
    client = await db.clients.find_one({"id": payload.client_id, "tenant_id": user["tenant_id"]}, {"_id": 0})
    if not client:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")
    company = await db.companies.find_one({"id": user["tenant_id"]}, {"_id": 0})
    pricing_config = company.get("pricing_config") or DEFAULT_PRICING_CONFIG
    services_sel = [s.model_dump() for s in payload.services]
    services_catalog = await _load_services_catalog(db, user["tenant_id"], services_sel)

    is_services = payload.type == "servicios"
    is_custom = payload.type == "personalizado"
    if not is_custom and not is_services and not payload.package_id:
        is_services = True
    pack = None
    package_snapshot = None
    custom_payload = {}

    d_start = payload.dates.start
    d_end = payload.dates.end
    if d_start and d_end and d_start > d_end:
        d_start, d_end = d_end, d_start

    if is_custom:
        if not payload.custom_items:
            raise HTTPException(status_code=400, detail="Agrega al menos un concepto al programa personalizado")
        calc = compute_custom_quotation(
            [c.model_dump() for c in payload.custom_items], payload.pax.model_dump(),
            payload.custom_nights, payload.custom_rooms, client["channel"], pricing_config,
            dates={"start": d_start, "end": d_end})
        title = (payload.custom_title or "").strip() or "Programa personalizado"
        package_snapshot = {"name": title, "code": "", "nights": calc["nights_total"]}
        custom_payload = {
            "custom_title": title,
            "custom_items": [c.model_dump() for c in payload.custom_items],
            "custom_itinerary": [d.model_dump() for d in payload.custom_itinerary],
            "custom_includes": payload.custom_includes,
            "custom_excludes": payload.custom_excludes,
            "custom_nights": payload.custom_nights,
            "custom_rooms": payload.custom_rooms,
        }
        extra_cfg = None
    else:
        if not is_services:
            pack = await db.packages.find_one({"id": payload.package_id, "tenant_id": user["tenant_id"]}, {"_id": 0})
            if not pack:
                raise HTTPException(status_code=404, detail="Paquete no encontrado")
            package_snapshot = {"name": pack["name"], "code": pack["code"], "nights": pack["nights"]}
        elif not services_sel:
            raise HTTPException(status_code=400, detail="Agrega al menos un servicio para una cotización a la carta")
        extra_cfg = payload.extra_nights.model_dump() if payload.extra_nights else None
        pack_nights = pack["nights"] if pack else 0
        calc = compute_quotation(pack, payload.hotel_name, payload.pax.model_dump(),
                                 pack_nights, client["channel"], pricing_config,
                                 services_catalog, services_sel,
                                 dates={"start": d_start, "end": d_end}, extra_nights_cfg=extra_cfg)
    type_label = {"personalizado": "programa personalizado", "servicios": "servicios a la carta"}.get(payload.type, "paquete")
    code = await _next_quotation_code(db, user["tenant_id"])
    doc = {
        "id": new_id(), "tenant_id": user["tenant_id"], "code": code,
        "client_id": client["id"], "client_snapshot": {"name": client["name"], "channel": client["channel"]},
        "type": "personalizado" if is_custom else ("servicios" if is_services else "paquete"),
        "package_id": pack["id"] if pack else None,
        "package_snapshot": package_snapshot,
        "hotel_selected": payload.hotel_name if pack else "",
        "dates": {"start": d_start, "end": d_end},
        "pax": payload.pax.model_dump(),
        "services": services_sel,
        "contacts": payload.contacts.model_dump() if payload.contacts else None,
        "extra_nights_cfg": extra_cfg,
        **custom_payload,
        "nights_total": calc["nights_total"],
        "extra_nights": calc["extra_nights"],
        "season_applied": calc.get("season_applied"),
        "items": calc["items"],
        "subtotal": calc["subtotal"],
        "commission": calc["commission"],
        "commission_rate": calc["commission_rate"],
        "total": calc["total"],
        "currency": calc["currency"],
        "state": "nueva_consulta",
        "archived": False,
        "deleted": False,
        "assigned_to": payload.assigned_to or user["id"],
        "created_by": user["id"],
        "notes": payload.notes,
        "presentation_text": payload.presentation_text or "",
        "from_request": payload.from_request or None,
        "history": [{
            "at": now_iso(), "user_id": user["id"], "user_name": user.get("name", ""),
            "action": "created", "detail": f"Cotización creada ({type_label})",
        }],
        "last_activity_at": now_iso(),
        "created_at": now_iso(),
    }
    await db.quotations.insert_one(dict(doc))
    return doc


@router.patch("/quotations/{quotation_id}/state")
async def update_quotation_state(quotation_id: str, payload: QuotationStateUpdate, user: dict = Depends(require_tenant)):
    db = get_db()
    q = await db.quotations.find_one({"id": quotation_id, "tenant_id": user["tenant_id"]}, {"_id": 0})
    if not q:
        raise HTTPException(status_code=404, detail="Cotización no encontrada")
    prev = q.get("state")
    await db.quotations.update_one(
        {"id": quotation_id, "tenant_id": user["tenant_id"]},
        {"$set": {"state": payload.state, "last_activity_at": now_iso()}},
    )
    STATE_LABELS = {
        "nueva_consulta": "Nueva consulta", "cotizando": "Cotizando", "enviada": "Enviada",
        "negociacion": "En negociación", "ganada": "Ganada", "perdida": "Perdida",
    }
    await _append_history(db, quotation_id, user, "state_change",
                          f"Estado: {STATE_LABELS.get(prev, prev)} → {STATE_LABELS.get(payload.state, payload.state)}")
    if payload.state == "ganada" and prev != "ganada":
        await _record_audit(db, user["tenant_id"], user, "won", q, "Marcada como ganada")
    return {"ok": True, "state": payload.state}


@router.patch("/quotations/{quotation_id}/pricing-adjust")
async def adjust_quotation_pricing(quotation_id: str, payload: QuotationPricingAdjust, user: dict = Depends(require_tenant)):
    db = get_db()
    q = await db.quotations.find_one({"id": quotation_id, "tenant_id": user["tenant_id"]}, {"_id": 0})
    if not q:
        raise HTTPException(status_code=404, detail="Cotización no encontrada")
    discount = {"type": payload.discount_type, "value": payload.discount_value}
    final_total, amount = _apply_discount(float(q.get("total", 0) or 0), discount)
    discount["amount"] = amount
    await db.quotations.update_one(
        {"id": quotation_id, "tenant_id": user["tenant_id"]},
        {"$set": {"discount": discount, "final_total": final_total, "last_activity_at": now_iso()}},
    )
    dlabel = "sin descuento" if payload.discount_type == "none" else (
        f"{payload.discount_value}%" if payload.discount_type == "percent" else f"${payload.discount_value}")
    await _append_history(db, quotation_id, user, "discount", f"Descuento aplicado: {dlabel}")
    return await db.quotations.find_one({"id": quotation_id, "tenant_id": user["tenant_id"]}, {"_id": 0})


@router.patch("/quotations/{quotation_id}")
async def update_quotation(quotation_id: str, payload: QuotationUpdate, user: dict = Depends(require_tenant)):
    db = get_db()
    updates = {k: v for k, v in payload.model_dump(exclude_unset=True).items() if v is not None}
    q = await db.quotations.find_one({"id": quotation_id, "tenant_id": user["tenant_id"]}, {"_id": 0})
    if not q:
        raise HTTPException(status_code=404, detail="Cotización no encontrada")
    changed_fields = [k for k in updates.keys()]
    if q.get("type") == "personalizado":
        if any(k in updates for k in ("pax", "dates", "custom_items", "custom_nights", "custom_rooms")):
            client = await db.clients.find_one({"id": q["client_id"], "tenant_id": user["tenant_id"]}, {"_id": 0})
            company = await db.companies.find_one({"id": user["tenant_id"]}, {"_id": 0})
            pricing_config = company.get("pricing_config") or DEFAULT_PRICING_CONFIG
            pax = updates.get("pax", q["pax"])
            new_dates = updates.get("dates", q.get("dates"))
            if new_dates and new_dates.get("start") and new_dates.get("end") and new_dates["start"] > new_dates["end"]:
                new_dates = {"start": new_dates["end"], "end": new_dates["start"]}
            citems = updates.get("custom_items", q.get("custom_items", []))
            cnights = updates.get("custom_nights", q.get("custom_nights", 0))
            crooms = updates.get("custom_rooms", q.get("custom_rooms", 0))
            calc = compute_custom_quotation(citems, pax, cnights, crooms, client["channel"], pricing_config, dates=new_dates)
            updates.update({
                "dates": new_dates,
                "nights_total": calc["nights_total"], "extra_nights": 0,
                "items": calc["items"], "subtotal": calc["subtotal"],
                "commission": calc["commission"], "commission_rate": calc["commission_rate"],
                "total": calc["total"],
            })
            if q.get("discount") and q["discount"].get("type") != "none":
                final_total, amount = _apply_discount(calc["total"], q["discount"])
                disc = dict(q["discount"]); disc["amount"] = amount
                updates["discount"] = disc
                updates["final_total"] = final_total
        if "custom_title" in updates:
            title = (updates["custom_title"] or "").strip() or "Programa personalizado"
            updates["custom_title"] = title
            snap = dict(q.get("package_snapshot") or {}); snap["name"] = title
            updates["package_snapshot"] = snap
    elif any(k in updates for k in ("pax", "hotel_name", "services", "dates", "extra_nights")):
        pack = None
        if q.get("package_id"):
            pack = await db.packages.find_one({"id": q["package_id"], "tenant_id": user["tenant_id"]}, {"_id": 0})
        client = await db.clients.find_one({"id": q["client_id"], "tenant_id": user["tenant_id"]}, {"_id": 0})
        company = await db.companies.find_one({"id": user["tenant_id"]}, {"_id": 0})
        pricing_config = company.get("pricing_config") or DEFAULT_PRICING_CONFIG
        hotel = updates.get("hotel_name", q["hotel_selected"])
        pax = updates.get("pax", q["pax"])
        services_sel = updates.get("services", q.get("services", []))
        new_dates = updates.get("dates", q.get("dates"))
        if new_dates and new_dates.get("start") and new_dates.get("end") and new_dates["start"] > new_dates["end"]:
            new_dates = {"start": new_dates["end"], "end": new_dates["start"]}
        extra_cfg = updates.get("extra_nights", q.get("extra_nights_cfg"))
        services_catalog = await _load_services_catalog(db, user["tenant_id"], services_sel)
        pack_nights = pack["nights"] if pack else 0
        calc = compute_quotation(pack, hotel, pax, pack_nights, client["channel"], pricing_config,
                                 services_catalog, services_sel,
                                 dates=new_dates, extra_nights_cfg=extra_cfg)
        updates.update({
            "hotel_selected": hotel if pack else "",
            "services": services_sel,
            "dates": new_dates,
            "extra_nights_cfg": extra_cfg,
            "nights_total": calc["nights_total"],
            "extra_nights": calc["extra_nights"],
            "season_applied": calc.get("season_applied"),
            "items": calc["items"], "subtotal": calc["subtotal"],
            "commission": calc["commission"], "commission_rate": calc["commission_rate"],
            "total": calc["total"],
        })
        updates.pop("hotel_name", None)
        if q.get("discount") and q["discount"].get("type") != "none":
            final_total, amount = _apply_discount(calc["total"], q["discount"])
            disc = dict(q["discount"]); disc["amount"] = amount
            updates["discount"] = disc
            updates["final_total"] = final_total
    updates["last_activity_at"] = now_iso()
    await db.quotations.update_one({"id": quotation_id, "tenant_id": user["tenant_id"]}, {"$set": updates})
    if changed_fields:
        FIELD_ES = {"dates": "fechas", "pax": "habitaciones/pax", "services": "servicios",
                    "extra_nights": "noches extra", "hotel_name": "hotel", "contacts": "contactos",
                    "notes": "notas", "assigned_to": "responsable"}
        detail = "Editó: " + ", ".join(FIELD_ES.get(f, f) for f in changed_fields)
        await _append_history(db, quotation_id, user, "edited", detail)
    return await db.quotations.find_one({"id": quotation_id, "tenant_id": user["tenant_id"]}, {"_id": 0})


@router.patch("/quotations/{quotation_id}/archive")
async def archive_quotation(quotation_id: str, payload: QuotationArchive, user: dict = Depends(require_tenant)):
    db = get_db()
    q = await db.quotations.find_one({"id": quotation_id, "tenant_id": user["tenant_id"]}, {"_id": 0})
    if not q:
        raise HTTPException(status_code=404, detail="Cotización no encontrada")
    await db.quotations.update_one(
        {"id": quotation_id, "tenant_id": user["tenant_id"]},
        {"$set": {"archived": payload.archived, "last_activity_at": now_iso()}},
    )
    action = "archived" if payload.archived else "restored"
    await _append_history(db, quotation_id, user, action, "Archivada" if payload.archived else "Restaurada")
    await _record_audit(db, user["tenant_id"], user, action, q,
                        "Cotización archivada" if payload.archived else "Cotización restaurada")
    return {"ok": True, "archived": payload.archived}


@router.delete("/quotations/{quotation_id}")
async def delete_quotation(quotation_id: str, user: dict = Depends(require_tenant)):
    db = get_db()
    q = await db.quotations.find_one({"id": quotation_id, "tenant_id": user["tenant_id"]}, {"_id": 0})
    if not q:
        raise HTTPException(status_code=404, detail="Cotización no encontrada")
    await db.quotations.update_one(
        {"id": quotation_id, "tenant_id": user["tenant_id"]},
        {"$set": {"deleted": True, "deleted_at": now_iso(), "deleted_by": user["id"]}},
    )
    await _record_audit(db, user["tenant_id"], user, "deleted", q, "Cotización eliminada")
    return {"ok": True}


@router.get("/quotations/{quotation_id}/pdf")
async def download_quotation_pdf(quotation_id: str, user: dict = Depends(require_tenant)):
    db = get_db()
    q = await db.quotations.find_one({"id": quotation_id, "tenant_id": user["tenant_id"]}, {"_id": 0})
    if not q:
        raise HTTPException(status_code=404, detail="Cotización no encontrada")
    company = await db.companies.find_one({"id": user["tenant_id"]}, {"_id": 0})
    pack = None
    if q.get("package_id"):
        pack = await db.packages.find_one({"id": q["package_id"], "tenant_id": user["tenant_id"]}, {"_id": 0})
    if q.get("type") == "personalizado":
        pack = {
            "name": q.get("custom_title") or "Programa personalizado",
            "description": "",
            "nights": q.get("nights_total"),
            "itinerary": q.get("custom_itinerary", []),
            "includes": q.get("custom_includes", []),
            "excludes": q.get("custom_excludes", []),
        }
    client = await db.clients.find_one({"id": q["client_id"], "tenant_id": user["tenant_id"]}, {"_id": 0})
    pdf = generate_quotation_pdf(company, q, pack or {}, client or {"name": q.get("client_snapshot", {}).get("name", "")})
    return StreamingResponse(
        io.BytesIO(pdf), media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{q["code"]}.pdf"'},
    )


@router.post("/quotations/{quotation_id}/public-link")
async def create_public_link(quotation_id: str, user: dict = Depends(require_tenant)):
    import secrets
    from datetime import timedelta
    db = get_db()
    q = await db.quotations.find_one({"id": quotation_id, "tenant_id": user["tenant_id"]}, {"_id": 0})
    if not q:
        raise HTTPException(status_code=404, detail="Cotización no encontrada")
    token = secrets.token_urlsafe(18)
    expires_at = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()
    public = {"token": token, "expires_at": expires_at, "created_at": now_iso(), "accepted_at": None}
    await db.quotations.update_one({"id": quotation_id}, {"$set": {"public_link": public}})
    return {"token": token, "expires_at": expires_at}


@router.delete("/quotations/{quotation_id}/public-link")
async def revoke_public_link(quotation_id: str, user: dict = Depends(require_tenant)):
    db = get_db()
    await db.quotations.update_one(
        {"id": quotation_id, "tenant_id": user["tenant_id"]},
        {"$unset": {"public_link": ""}},
    )
    return {"ok": True}


# ---------------------------------------------------------------------------
# IA operativa (Claude Sonnet 4.5)
# ---------------------------------------------------------------------------
@router.post("/ai/presentation")
async def ai_presentation(payload: PresentationInput, user: dict = Depends(require_tenant)):
    await _check_ai_enabled(user["tenant_id"])
    try:
        text = await ai_service.generate_presentation(
            payload.client_name, payload.title, payload.date_start, payload.date_end,
            payload.adultos, payload.menores, tone=payload.tone, tenant_id=user["tenant_id"])
        return {"text": text}
    except Exception as e:
        log.exception("AI presentation failed")
        raise HTTPException(status_code=503, detail=f"IA no disponible: {e}")



@router.post("/ai/chat-summary")
async def ai_chat_summary(payload: dict, user: dict = Depends(require_tenant)):
    await _check_ai_enabled(user["tenant_id"])
    messages = payload.get("messages") or []
    if not messages:
        raise HTTPException(status_code=400, detail="Sin mensajes")
    try:
        summary = await ai_service.summarize_chat(messages, tenant_id=user['tenant_id'])
        return {"summary": summary}
    except Exception as e:
        log.exception("AI summary failed")
        raise HTTPException(status_code=503, detail=f"IA no disponible: {e}")


async def _load_quotation_context(quotation_id: str, tenant_id: str):
    db = get_db()
    q = await db.quotations.find_one({"id": quotation_id, "tenant_id": tenant_id}, {"_id": 0})
    if not q:
        raise HTTPException(status_code=404, detail="Cotización no encontrada")
    pack = await db.packages.find_one({"id": q["package_id"], "tenant_id": tenant_id}, {"_id": 0})
    client = await db.clients.find_one({"id": q["client_id"], "tenant_id": tenant_id}, {"_id": 0})
    try:
        last = datetime.fromisoformat(q.get("last_activity_at", q.get("created_at")))
        q["days_idle"] = (datetime.now(timezone.utc) - last).days
    except Exception:
        q["days_idle"] = 0
    return q, pack, client


@router.post("/ai/quotations/{quotation_id}/next-step")
async def ai_next_step(quotation_id: str, user: dict = Depends(require_tenant)):
    await _check_ai_enabled(user["tenant_id"])
    q, pack, client = await _load_quotation_context(quotation_id, user["tenant_id"])
    try:
        suggestion = await ai_service.suggest_next_step(q, pack, client, tenant_id=user['tenant_id'])
        return {"suggestion": suggestion}
    except Exception as e:
        log.exception("AI next-step failed")
        raise HTTPException(status_code=503, detail=f"IA no disponible: {e}")


@router.post("/ai/quotations/{quotation_id}/missing-fields")
async def ai_missing_fields(quotation_id: str, user: dict = Depends(require_tenant)):
    await _check_ai_enabled(user["tenant_id"])
    q, pack, client = await _load_quotation_context(quotation_id, user["tenant_id"])
    try:
        fields = await ai_service.detect_missing_fields(q, pack, client, tenant_id=user['tenant_id'])
        return {"fields": fields}
    except Exception as e:
        log.exception("AI missing-fields failed")
        raise HTTPException(status_code=503, detail=f"IA no disponible: {e}")


@router.post("/ai/quotations/{quotation_id}/client-message")
async def ai_client_message(quotation_id: str, user: dict = Depends(require_tenant)):
    await _check_ai_enabled(user["tenant_id"])
    q, pack, client = await _load_quotation_context(quotation_id, user["tenant_id"])
    try:
        msg = await ai_service.generate_client_message(q, pack, client, tenant_id=user['tenant_id'])
        return {"message": msg}
    except Exception as e:
        log.exception("AI client-message failed")
        raise HTTPException(status_code=503, detail=f"IA no disponible: {e}")
