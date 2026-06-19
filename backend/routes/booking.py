"""Confirmación de Reserva: documento generado por el ejecutivo desde una
cotización en estado 'ganada'. Incluye PDF y envío por correo / WhatsApp."""
import io
import re
import secrets

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

from database import get_db, new_id, now_iso
from auth import require_tenant
from models import BookingConfirmationSave, BookingSendRequest
from pdf_generator import generate_booking_confirmation_pdf
from notifications import send_email

router = APIRouter()


def _base_url(request: Request) -> str:
    return f"{request.url.scheme}://{request.headers.get('host', '')}"


async def _ctx_for_confirmation(db, conf: dict):
    q = await db.quotations.find_one({"id": conf["quotation_id"]}, {"_id": 0})
    company = await db.companies.find_one({"id": conf["tenant_id"]}, {"_id": 0})
    client = None
    if q:
        client = await db.clients.find_one({"id": q.get("client_id")}, {"_id": 0})
    return q or {}, company or {}, client or {"name": (q or {}).get("client_snapshot", {}).get("name", "")}


OCC_LABEL = {"sencilla": "Sencilla", "doble": "Doble", "triple": "Triple", "cuadruple": "Cuádruple"}
OCC_CNT = {"sencilla": 1, "doble": 2, "triple": 3, "cuadruple": 4}


@router.get("/quotations/{quotation_id}/booking-confirmation")
async def get_booking_confirmation(quotation_id: str, user: dict = Depends(require_tenant)):
    db = get_db()
    conf = await db.booking_confirmations.find_one(
        {"quotation_id": quotation_id, "tenant_id": user["tenant_id"]}, {"_id": 0})
    if conf:
        return conf

    # Sin confirmación previa -> devolver un BORRADOR prellenado desde la cotización.
    q = await db.quotations.find_one({"id": quotation_id, "tenant_id": user["tenant_id"]}, {"_id": 0})
    if not q:
        return {}
    client = await db.clients.find_one({"id": q.get("client_id")}, {"_id": 0}) or {}
    contacts = q.get("contacts") or {}
    agency = contacts.get("agency") or {}
    traveler = contacts.get("traveler") or {}
    pax = q.get("pax") or {}
    rooms = pax.get("rooms") or []
    if rooms:
        total_pax = sum(OCC_CNT.get(r.get("ocupacion", "doble"), 1) * int(r.get("count", 1)) for r in rooms) + int(pax.get("menores", 0))
        occ = rooms[0].get("ocupacion", "doble")
    else:
        total_pax = int(pax.get("adultos", 0) or 0) + int(pax.get("menores", 0) or 0)
        occ = pax.get("ocupacion", "doble")
    total = q.get("final_total") if q.get("final_total") is not None else q.get("total", 0)
    dates = q.get("dates") or {}

    pack = None
    if q.get("package_id"):
        pack = await db.packages.find_one({"id": q["package_id"]}, {"_id": 0})
    incl = (pack or {}).get("inclusions") or {}
    svc_map = [("arrival_transfer", "Traslado de llegada"), ("departure_transfer", "Traslado de salida"),
               ("tours", "Tours"), ("venue_access", "Accesos a recintos")]
    services = [{"date": "", "service": label, "details": "", "persons": str(total_pax) if total_pax else "", "observations": ""}
                for key, label in svc_map if incl.get(key)]
    if incl.get("extras"):
        services.append({"date": "", "service": "Servicios extra", "details": incl["extras"],
                         "persons": str(total_pax) if total_pax else "", "observations": ""})

    lodging = [{
        "hotel": q.get("hotel_selected", ""), "plan": "",
        "checkin": dates.get("start", ""), "checkout": dates.get("end", ""),
        "nights": str(q.get("nights_total", "") or ""), "room_type": OCC_LABEL.get(occ, ""),
        "confirmation_number": "", "guest_name": traveler.get("name", ""),
    }] if q.get("hotel_selected") else []

    return {
        "_prefill": True,
        "agent_name": agency.get("contact") or client.get("name", ""),
        "agent_phone": client.get("phone", ""),
        "agent_company": agency.get("name") or client.get("name", ""),
        "reservation_date": now_iso()[:10],
        "passenger_name": traveler.get("name") or client.get("name", ""),
        "passenger_phone": traveler.get("phone") or client.get("phone", ""),
        "num_persons": str(total_pax) if total_pax else "",
        "services": services,
        "lodging": lodging,
        "general_observations": "",
        "price_per_person": round(total / total_pax, 2) if total_pax else 0,
        "total_amount": total or 0,
    }


@router.post("/quotations/{quotation_id}/booking-confirmation")
async def save_booking_confirmation(quotation_id: str, payload: BookingConfirmationSave,
                                    user: dict = Depends(require_tenant)):
    db = get_db()
    q = await db.quotations.find_one({"id": quotation_id, "tenant_id": user["tenant_id"]}, {"_id": 0})
    if not q:
        raise HTTPException(status_code=404, detail="Cotización no encontrada")
    if q.get("state") != "ganada":
        raise HTTPException(status_code=400, detail="La cotización debe estar en estado 'Ganada' para generar la confirmación.")
    data = payload.model_dump()
    existing = await db.booking_confirmations.find_one(
        {"quotation_id": quotation_id, "tenant_id": user["tenant_id"]}, {"_id": 0})
    if existing:
        await db.booking_confirmations.update_one(
            {"id": existing["id"]}, {"$set": {**data, "updated_at": now_iso()}})
        return await db.booking_confirmations.find_one({"id": existing["id"]}, {"_id": 0})
    doc = {
        "id": new_id(), "tenant_id": user["tenant_id"], "quotation_id": quotation_id,
        "code": f"{q.get('code', 'RES')}-CR",
        "token": secrets.token_urlsafe(16),
        "currency": q.get("currency", "MXN"),
        "created_by": user["id"], "created_at": now_iso(),
        **data,
    }
    await db.booking_confirmations.insert_one(dict(doc))
    return await db.booking_confirmations.find_one({"id": doc["id"]}, {"_id": 0})


@router.get("/booking-confirmations/{conf_id}/pdf")
async def booking_pdf(conf_id: str, request: Request, user: dict = Depends(require_tenant)):
    db = get_db()
    conf = await db.booking_confirmations.find_one(
        {"id": conf_id, "tenant_id": user["tenant_id"]}, {"_id": 0})
    if not conf:
        raise HTTPException(status_code=404, detail="Confirmación no encontrada")
    q, company, client = await _ctx_for_confirmation(db, conf)
    pdf = generate_booking_confirmation_pdf(company, q, conf, client, base_url=_base_url(request))
    return StreamingResponse(io.BytesIO(pdf), media_type="application/pdf",
                             headers={"Content-Disposition": f'attachment; filename="{conf["code"]}.pdf"'})


@router.get("/public/booking-confirmation/{token}/pdf")
async def public_booking_pdf(token: str, request: Request):
    db = get_db()
    conf = await db.booking_confirmations.find_one({"token": token}, {"_id": 0})
    if not conf:
        raise HTTPException(status_code=404, detail="Documento no encontrado")
    q, company, client = await _ctx_for_confirmation(db, conf)
    pdf = generate_booking_confirmation_pdf(company, q, conf, client, base_url=_base_url(request))
    return StreamingResponse(io.BytesIO(pdf), media_type="application/pdf",
                             headers={"Content-Disposition": f'inline; filename="{conf["code"]}.pdf"'})


@router.get("/public/booking-confirmation/{token}")
async def public_booking_confirmation(token: str):
    """Datos de la Confirmación de Reserva para la página web pública /r/:token."""
    db = get_db()
    conf = await db.booking_confirmations.find_one({"token": token}, {"_id": 0})
    if not conf:
        raise HTTPException(status_code=404, detail="Documento no encontrado")
    q, company, client = await _ctx_for_confirmation(db, conf)

    # Fechas del viaje para el calendario: primer check-in → último check-out.
    def _iso(d: str) -> str:
        d = (d or "").strip()[:10]
        try:
            from datetime import date as _date
            _date.fromisoformat(d)
            return d
        except Exception:
            return ""
    checkins = [_iso(l.get("checkin")) for l in (conf.get("lodging") or [])]
    checkouts = [_iso(l.get("checkout")) for l in (conf.get("lodging") or [])]
    svc_dates = [_iso(s.get("date")) for s in (conf.get("services") or [])]
    starts = [d for d in (checkins + svc_dates) if d]
    ends = [d for d in (checkouts + svc_dates) if d]
    trip_start = min(starts) if starts else ""
    trip_end = max(ends) if ends else trip_start

    bank = company.get("bank") or {}
    transfer_enabled = bool(company.get("transfer_allowed", True)) and any(
        bank.get(k) for k in ("name", "clabe", "account", "usd_account"))
    return {
        "confirmation": {
            "code": conf.get("code", ""),
            "currency": conf.get("currency", "MXN"),
            "agent_name": conf.get("agent_name", ""),
            "agent_phone": conf.get("agent_phone", ""),
            "agent_company": conf.get("agent_company", ""),
            "reservation_date": conf.get("reservation_date", ""),
            "passenger_name": conf.get("passenger_name", ""),
            "passenger_phone": conf.get("passenger_phone", ""),
            "num_persons": conf.get("num_persons", ""),
            "services": conf.get("services", []),
            "lodging": conf.get("lodging", []),
            "general_observations": conf.get("general_observations", ""),
            "price_per_person": conf.get("price_per_person", 0),
            "total_amount": conf.get("total_amount", 0),
            "trip_start": trip_start,
            "trip_end": trip_end,
        },
        "company": {
            "name": company.get("name", ""), "logo_url": company.get("logo_url", ""),
            "slug": company.get("slug", ""),
            "contact_email": company.get("contact_email", ""),
            "contact_phone": company.get("contact_phone", ""),
            "general_conditions": company.get("general_conditions", ""),
            "cancellation_policy": company.get("cancellation_policy", ""),
            "white_label": bool(company.get("white_label")),
            "bank": {
                "name": bank.get("name", ""), "holder": bank.get("holder", ""),
                "clabe": bank.get("clabe", ""), "account": bank.get("account", ""),
                "usd_account": bank.get("usd_account", ""), "swift": bank.get("swift", ""),
                "branch": bank.get("branch", ""), "reference": bank.get("reference", ""),
            } if transfer_enabled else None,
        },
    }


@router.post("/booking-confirmations/{conf_id}/send")
async def send_booking_confirmation(conf_id: str, payload: BookingSendRequest, request: Request,
                                    user: dict = Depends(require_tenant)):
    db = get_db()
    conf = await db.booking_confirmations.find_one(
        {"id": conf_id, "tenant_id": user["tenant_id"]}, {"_id": 0})
    if not conf:
        raise HTTPException(status_code=404, detail="Confirmación no encontrada")
    q, company, client = await _ctx_for_confirmation(db, conf)
    web_url = f"{_base_url(request)}/r/{conf['token']}"
    pdf_url = f"{_base_url(request)}/api/public/booking-confirmation/{conf['token']}/pdf"

    if payload.channel == "whatsapp":
        phone = re.sub(r"[^0-9]", "", payload.to or conf.get("passenger_phone", "") or conf.get("agent_phone", ""))
        msg = (f"Hola, te compartimos la Confirmación de Reserva {conf['code']} de {company.get('name','')}. "
               f"Puedes consultarla y agregarla a tu calendario aquí: {web_url}")
        from urllib.parse import quote
        wa = f"https://wa.me/{phone}?text={quote(msg)}" if phone else f"https://wa.me/?text={quote(msg)}"
        return {"ok": True, "channel": "whatsapp", "wa_link": wa, "web_url": web_url, "pdf_url": pdf_url}

    to = (payload.to or client.get("email", "") or "").strip()
    if not to:
        raise HTTPException(status_code=400, detail="Falta el correo del destinatario.")
    pdf = generate_booking_confirmation_pdf(company, q, conf, client, base_url=_base_url(request))
    html = (f"<h2>Confirmación de Reserva {conf['code']}</h2>"
            f"<p>Hola, adjuntamos tu Confirmación de Reserva con {company.get('name','')}.</p>"
            f"<p>También puedes consultarla en línea y agregarla a tu calendario: <a href='{web_url}'>{web_url}</a></p>")
    sent = await send_email(company, to, f"Confirmación de Reserva {conf['code']} — {company.get('name','')}",
                            html, attachments=[{"filename": f"{conf['code']}.pdf", "data": pdf, "mime": "application/pdf"}])
    return {"ok": True, "channel": "email", "email_sent": sent, "to": to, "web_url": web_url, "pdf_url": pdf_url}
