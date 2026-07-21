"""Confirmación de Reserva: documento generado por el ejecutivo desde una
cotización en estado 'ganada'. Incluye PDF y envío por correo / WhatsApp."""
import io
import re
import secrets

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse, HTMLResponse

from database import get_db, new_id, now_iso
from auth import require_tenant
from models import BookingConfirmationSave, BookingSendRequest
from pdf_generator import generate_booking_confirmation_pdf
from notifications import send_email
from deps import _append_history

router = APIRouter()


def _base_url(request: Request) -> str:
    return f"{request.url.scheme}://{request.headers.get('host', '')}"


async def _executive_fields(db, q: dict, company: dict) -> dict:
    """H1/10.4: el 'ejecutivo' real es el usuario Routiq que elaboró la cotización
    (created_by), no el contacto de la agencia. Empresa = tenant."""
    name = email = phone = ""
    uid = (q or {}).get("created_by")
    if uid:
        u = await db.users.find_one({"id": uid}, {"_id": 0, "name": 1, "email": 1, "phone": 1})
        if u:
            name = u.get("name") or u.get("email") or ""
            email = u.get("email") or ""
            phone = u.get("phone") or ""
    return {"agent_name": name, "agent_email": email, "agent_company": (company or {}).get("name", ""), "agent_phone": phone}


async def _ctx_for_confirmation(db, conf: dict):
    q = await db.quotations.find_one({"id": conf["quotation_id"]}, {"_id": 0})
    company = await db.companies.find_one({"id": conf["tenant_id"]}, {"_id": 0})
    client = None
    if q:
        client = await db.clients.find_one({"id": q.get("client_id")}, {"_id": 0})
    # Siempre resolver el ejecutivo real para el PDF/enlace, ignorando datos de agencia previos.
    ef = await _executive_fields(db, q or {}, company or {})
    conf["agent_name"] = ef["agent_name"]
    conf["agent_email"] = ef["agent_email"]
    conf["agent_company"] = ef["agent_company"]
    if not conf.get("agent_phone"):
        conf["agent_phone"] = ef["agent_phone"]
    return q or {}, company or {}, client or {"name": (q or {}).get("client_snapshot", {}).get("name", "")}


OCC_LABEL = {"sencilla": "Sencilla", "doble": "Doble", "triple": "Triple", "cuadruple": "Cuádruple"}
OCC_CNT = {"sencilla": 1, "doble": 2, "triple": 3, "cuadruple": 4}

from pricing import CUSTOM_CATEGORY_ES


async def _prefill_itinerary(db, q: dict, pack: dict | None) -> list:
    """10.5 — Contenido del programa según el tipo de cotización:
      - paquete       -> itinerario día a día completo del paquete.
      - servicios     -> descripción de cada servicio contratado.
      - personalizado -> concepto + descripción de cada ítem del programa.
    """
    qtype = (q or {}).get("type", "paquete")
    entries: list = []
    if qtype == "personalizado":
        for ci in (q.get("custom_items") or []):
            name = (ci.get("name") or "").strip() or CUSTOM_CATEGORY_ES.get(ci.get("category", ""), "Concepto")
            entries.append({"title": name, "description": (ci.get("description") or "").strip()})
    elif qtype == "servicios":
        sel = q.get("services") or []
        ids = [s.get("service_id") for s in sel if s.get("service_id")]
        svcs: dict = {}
        if ids:
            async for s in db.services.find({"id": {"$in": ids}, "tenant_id": q.get("tenant_id")}, {"_id": 0}):
                svcs[s["id"]] = s
        for s in sel:
            svc = svcs.get(s.get("service_id"))
            if svc:
                entries.append({"title": svc.get("name", ""), "description": (svc.get("description") or "").strip()})
    else:  # paquete
        for d in ((pack or {}).get("itinerary") or []):
            title = f"Día {d.get('day', '')}: {d.get('title', '')}".strip().rstrip(":")
            entries.append({"title": title, "description": (d.get("description") or "").strip()})
    return entries


async def _recompute_from_quotation(db, q: dict) -> dict:
    """Valores que la Confirmación copia de la cotización, recalculados AL VUELO desde
    el estado actual de la cotización (para detectar desfase y para la actualización manual)."""
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
    return {
        "total_amount": total or 0,
        "price_per_person": round(total / total_pax, 2) if total_pax else 0,
        "num_persons": str(total_pax) if total_pax else "",
        "hotel": q.get("hotel_selected", ""),
        "checkin": dates.get("start", ""),
        "checkout": dates.get("end", ""),
        "nights": str(q.get("nights_total", "") or ""),
        "room_type": OCC_LABEL.get(occ, ""),
    }


@router.get("/quotations/{quotation_id}/booking-confirmation")
async def get_booking_confirmation(quotation_id: str, user: dict = Depends(require_tenant)):
    db = get_db()
    conf = await db.booking_confirmations.find_one(
        {"quotation_id": quotation_id, "tenant_id": user["tenant_id"]}, {"_id": 0})
    if conf:
        qc = await db.quotations.find_one({"id": quotation_id, "tenant_id": user["tenant_id"]}, {"_id": 0}) or {}
        if not conf.get("itinerary"):
            packc = await db.packages.find_one({"id": qc.get("package_id")}, {"_id": 0}) if qc.get("package_id") else None
            conf["itinerary"] = await _prefill_itinerary(db, qc, packc)
        # Detección de desfase: exponer los valores ACTUALES de la cotización.
        if qc:
            conf["_expected"] = await _recompute_from_quotation(db, qc)
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

    company = await db.companies.find_one({"id": user["tenant_id"]}, {"_id": 0}) or {}
    ef = await _executive_fields(db, q, company)

    return {
        "_prefill": True,
        "agent_name": ef["agent_name"],
        "agent_phone": ef["agent_phone"],
        "agent_company": ef["agent_company"],
        "agent_email": ef["agent_email"],
        "reservation_date": now_iso()[:10],
        "passenger_name": traveler.get("name") or client.get("name", ""),
        "passenger_phone": traveler.get("phone") or client.get("phone", ""),
        "num_persons": str(total_pax) if total_pax else "",
        "services": services,
        "lodging": lodging,
        "itinerary": await _prefill_itinerary(db, q, pack),
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


@router.post("/quotations/{quotation_id}/booking-confirmation/refresh-amounts")
async def refresh_booking_amounts(quotation_id: str, user: dict = Depends(require_tenant)):
    """Actualiza manualmente los montos (y datos de viaje) de la Confirmación guardada con
    los valores ACTUALES de la cotización. Explícito, nunca automático."""
    db = get_db()
    conf = await db.booking_confirmations.find_one(
        {"quotation_id": quotation_id, "tenant_id": user["tenant_id"]}, {"_id": 0})
    if not conf:
        raise HTTPException(status_code=404, detail="Confirmación no encontrada")
    q = await db.quotations.find_one({"id": quotation_id, "tenant_id": user["tenant_id"]}, {"_id": 0})
    if not q:
        raise HTTPException(status_code=404, detail="Cotización no encontrada")
    exp = await _recompute_from_quotation(db, q)
    updates = {
        "total_amount": exp["total_amount"],
        "price_per_person": exp["price_per_person"],
        "num_persons": exp["num_persons"],
        "updated_at": now_iso(),
    }
    # Actualiza los datos de viaje del hospedaje conservando lo que el ejecutivo editó
    # (n° de confirmación, nombre del huésped, plan).
    lodging = [dict(r) for r in (conf.get("lodging") or [])]
    if lodging:
        lodging[0].update({
            "hotel": exp["hotel"], "checkin": exp["checkin"], "checkout": exp["checkout"],
            "nights": exp["nights"], "room_type": exp["room_type"],
        })
        updates["lodging"] = lodging
    await db.booking_confirmations.update_one({"id": conf["id"]}, {"$set": updates})
    cur = f"${float(exp['total_amount'] or 0):,.2f}".rstrip("0").rstrip(".") if exp["total_amount"] else "$0"
    await _append_history(db, quotation_id, user, "confirmation_updated",
                          f"Actualizó los montos de la Confirmación de Reserva desde la cotización ({cur} {conf.get('currency', 'MXN')})")
    return await db.booking_confirmations.find_one({"id": conf["id"]}, {"_id": 0})


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


def _esc(s: str) -> str:
    return (str(s or "").replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


@router.get("/share/r/{token}", response_class=HTMLResponse)
async def share_booking_confirmation(token: str, request: Request):
    """Página compartible (Open Graph por tenant) para la Confirmación de Reserva;
    redirige a la SPA /r/{token}."""
    db = get_db()
    base = _base_url(request)
    spa_url = f"{base}/r/{token}"
    conf = await db.booking_confirmations.find_one({"token": token}, {"_id": 0})
    title = "Confirmación de Reserva"
    desc = "Consulta los detalles de tu reserva y agrégala a tu calendario."
    image = ""
    if conf:
        company = await db.companies.find_one({"id": conf["tenant_id"]}, {"_id": 0}) or {}
        cname = company.get("name") or "Routiq"
        title = f"{cname} · Confirmación {conf.get('code', '')}".strip()
        passenger = conf.get("passenger_name") or "viajero"
        desc = (f"Hola {passenger}, tu Confirmación de Reserva está lista. "
                "Ábrela para ver servicios, hospedaje y agregarla a tu calendario.")
        logo = company.get("logo_url") or ""
        if logo.startswith("/"):
            image = base + logo
        elif logo.startswith("http"):
            image = logo
    img_tags = (f'<meta property="og:image" content="{_esc(image)}"/>'
                f'<meta name="twitter:image" content="{_esc(image)}"/>') if image else ""
    html = f"""<!doctype html>
<html lang="es"><head><meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>{_esc(title)}</title>
<meta name="description" content="{_esc(desc)}"/>
<meta property="og:type" content="website"/>
<meta property="og:title" content="{_esc(title)}"/>
<meta property="og:description" content="{_esc(desc)}"/>
<meta property="og:url" content="{_esc(spa_url)}"/>
<meta name="twitter:card" content="summary_large_image"/>
<meta name="twitter:title" content="{_esc(title)}"/>
<meta name="twitter:description" content="{_esc(desc)}"/>
{img_tags}
<meta http-equiv="refresh" content="0; url={_esc(spa_url)}"/>
<script>window.location.replace({spa_url!r});</script>
</head><body>
<p>Redirigiendo a tu confirmación… <a href="{_esc(spa_url)}">Abrir confirmación</a></p>
</body></html>"""
    return HTMLResponse(content=html)


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
