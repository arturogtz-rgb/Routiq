"""Generates a professional quotation PDF using ReportLab."""
from __future__ import annotations
import io
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
from reportlab.lib.enums import TA_LEFT, TA_CENTER

PRIMARY = colors.HexColor("#185FA5")
ACCENT = colors.HexColor("#378ADD")
PASTEL = colors.HexColor("#E6F1FB")
MINT = colors.HexColor("#E1F5EE")
PEACH = colors.HexColor("#FAEEDA")
TEXT = colors.HexColor("#0F172A")
TEXT_SOFT = colors.HexColor("#475569")


def _styles():
    base = getSampleStyleSheet()
    styles = {
        "title": ParagraphStyle("t", parent=base["Title"], fontName="Helvetica-Bold", fontSize=18, textColor=PRIMARY, alignment=TA_LEFT, spaceAfter=4),
        "h2": ParagraphStyle("h2", parent=base["Heading2"], fontName="Helvetica-Bold", fontSize=11, textColor=PRIMARY, spaceBefore=8, spaceAfter=3),
        "h3": ParagraphStyle("h3", parent=base["Heading3"], fontName="Helvetica-Bold", fontSize=9.5, textColor=TEXT, spaceBefore=4, spaceAfter=2),
        "body": ParagraphStyle("b", parent=base["BodyText"], fontName="Helvetica", fontSize=8.5, textColor=TEXT, leading=11),
        "soft": ParagraphStyle("s", parent=base["BodyText"], fontName="Helvetica", fontSize=8, textColor=TEXT_SOFT, leading=10),
        "total": ParagraphStyle("tot", parent=base["BodyText"], fontName="Helvetica-Bold", fontSize=13, textColor=PRIMARY, alignment=TA_LEFT),
    }
    return styles


def _money(v: float, currency: str = "MXN") -> str:
    return f"${v:,.2f} {currency}"


_MESES_ABBR = ["ENE", "FEB", "MAR", "ABR", "MAY", "JUN", "JUL", "AGO", "SEP", "OCT", "NOV", "DIC"]


def _fmt_date(iso: str) -> str:
    from datetime import date as _date
    try:
        d = _date.fromisoformat((iso or "")[:10])
        return f"{d.day:02d} {_MESES_ABBR[d.month - 1]} {d.year}"
    except Exception:
        return iso or ""


def generate_quotation_pdf(company: dict, quotation: dict, package: dict, client: dict) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter,
                            leftMargin=1.4 * cm, rightMargin=1.4 * cm,
                            topMargin=1.3 * cm, bottomMargin=1.3 * cm,
                            title=f"Cotización {quotation.get('code', '')}")
    s = _styles()
    story = []

    # Header — with logo if available
    from reportlab.platypus import Image as RLImage
    from pathlib import Path as _P
    logo_cell = ""
    logo_url = company.get("logo_url") or ""
    # accept both /uploads/... (legacy) and /api/uploads/... (current)
    rel = logo_url.replace("/api/uploads/", "").replace("/uploads/", "")
    if rel:
        # try docker path first, then local dev path
        candidates = [_P("/app/uploads") / rel, _P(__file__).parent / "uploads" / rel]
        for logo_path in candidates:
            if logo_path.exists() and logo_path.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp"):
                try:
                    logo_cell = RLImage(str(logo_path), width=3.5 * cm, height=3.5 * cm, kind="proportional")
                    break
                except Exception:
                    logo_cell = ""

    company_text = Paragraph(
        f"<b>{company['name']}</b><br/><font size=9 color='#475569'>{company.get('contact_email','')}<br/>{company.get('contact_phone','')}<br/>{company.get('address','')}</font>",
        s["body"],
    )
    cot_text = Paragraph(
        f"<b><font color='#185FA5' size=16>COTIZACIÓN</font></b><br/><font size=10>{quotation.get('code','')}</font><br/><font size=9 color='#475569'>{_fmt_date(quotation.get('created_at',''))}</font>",
        s["body"],
    )
    if logo_cell:
        header_data = [[logo_cell, company_text, cot_text]]
        col_widths = [4 * cm, 8 * cm, 5 * cm]
    else:
        header_data = [[company_text, cot_text]]
        col_widths = [10 * cm, 7 * cm]
    header = Table(header_data, colWidths=col_widths)
    header.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ALIGN", (-1, 0), (-1, 0), "RIGHT"),
        ("LINEBELOW", (0, 0), (-1, -1), 2, PRIMARY),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 14),
    ]))
    story.append(header)
    story.append(Spacer(1, 12))

    # Client block
    story.append(Paragraph("Cliente", s["h2"]))
    story.append(Paragraph(
        f"<b>{client.get('name','')}</b> &nbsp;&nbsp; <font color='#475569'>{client.get('email','')} · {client.get('phone','')}</font>",
        s["body"],
    ))

    # Agency + final traveler contacts (B2B quotations)
    contacts = quotation.get("contacts") or {}
    agency = contacts.get("agency") or {}
    traveler = contacts.get("traveler") or {}
    if any(agency.values()) or any(traveler.values()):
        ct_rows = []
        if any(agency.values()):
            ct_rows.append([
                Paragraph("<b>Agencia / Vendedor</b>", s["body"]),
                Paragraph(f"{agency.get('name','')}<br/><font color='#475569' size=8>{agency.get('contact','')} · {agency.get('email','')}</font>", s["soft"]),
            ])
        if any(traveler.values()):
            ct_rows.append([
                Paragraph("<b>Cliente final / Turista</b>", s["body"]),
                Paragraph(f"{traveler.get('name','')}<br/><font color='#475569' size=8>Tel: {traveler.get('phone','')}</font>", s["soft"]),
            ])
        ct = Table(ct_rows, colWidths=[4.5 * cm, 12.5 * cm])
        ct.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (0, -1), PASTEL),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
            ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ]))
        story.append(Spacer(1, 6))
        story.append(ct)

    # Package / type block
    is_services = quotation.get("type") == "servicios" or not package.get("name")
    title_txt = "Servicios a la carta" if is_services else package.get("name", "")
    story.append(Paragraph(title_txt, s["h2"]))
    if not is_services and package.get("description"):
        story.append(Paragraph(package["description"], s["soft"]))
    dates = quotation.get("dates", {}) or {}
    # Defensive: ensure start <= end (some legacy quotations may have them swapped)
    d_start = dates.get("start", "") or ""
    d_end = dates.get("end", "") or ""
    if d_start and d_end and d_start > d_end:
        d_start, d_end = d_end, d_start
    pax = quotation.get("pax", {})
    story.append(Spacer(1, 6))

    # Build pax description (rooms or legacy occupancy)
    if pax.get("rooms"):
        total_pax = sum({"sencilla":1,"doble":2,"triple":3,"cuadruple":4}.get(r["ocupacion"],0) * int(r.get("count",1)) for r in pax["rooms"])
        rooms_desc = ", ".join(f"{r['count']} {r['ocupacion']}" for r in pax["rooms"])
        pax_desc = f"{rooms_desc} ({total_pax} adultos)"
        if pax.get("menores", 0) > 0:
            pax_desc += f" + {pax['menores']} menores"
    else:
        pax_desc = f"{pax.get('ocupacion','')} · {pax.get('adultos',0)} adultos, {pax.get('menores',0)} menores"

    nights_total = quotation.get("nights_total") or package.get("nights", "")
    extra_nights = quotation.get("extra_nights", 0) or 0
    nights_label = str(nights_total)
    if extra_nights > 0:
        nights_label += f"  ({package.get('nights','')} del paquete + {extra_nights} extra)"
    meta_rows = []
    if quotation.get("hotel_selected"):
        meta_rows.append(["Hotel", quotation.get("hotel_selected", "")])
    if d_start or d_end:
        meta_rows.append(["Fechas", f"{_fmt_date(d_start)}  →  {_fmt_date(d_end)}"])
    if not is_services and nights_total:
        meta_rows.append(["Noches", nights_label])
    meta_rows.append(["Pax" if is_services else "Habitaciones / Pax", pax_desc])
    meta = Table(meta_rows, colWidths=[3.5 * cm, 12 * cm])
    meta.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), PASTEL),
        ("TEXTCOLOR", (0, 0), (0, -1), PRIMARY),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("ROWBACKGROUNDS", (1, 0), (1, -1), [colors.white, colors.HexColor("#F8F9FA")]),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(meta)

    # Itinerary
    if package.get("itinerary"):
        story.append(Paragraph("Itinerario", s["h2"]))
        for day in package["itinerary"]:
            story.append(Paragraph(f"<b>Día {day.get('day','')}:</b> {day.get('title','')}", s["h3"]))
            if day.get("description"):
                story.append(Paragraph(day["description"], s["body"]))

    # Price items
    story.append(Paragraph("Desglose de precios", s["h2"]))
    currency = quotation.get("currency", "MXN")
    rows = [["Concepto", "P. unitario", "Cant.", "Subtotal"]]
    for it in quotation.get("items", []):
        rows.append([it["label"], _money(it["unit_price"], currency), str(it["qty"]), _money(it["subtotal"], currency)])
    price_table = Table(rows, colWidths=[9 * cm, 3 * cm, 1.5 * cm, 3 * cm])
    price_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), PRIMARY),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8F9FA")]),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#E2E8F0")),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(price_table)
    story.append(Spacer(1, 10))

    # Totals
    tot_rows = [
        ["Subtotal", _money(quotation.get("subtotal", 0), currency)],
    ]
    if quotation.get("commission", 0) > 0:
        tot_rows.append(["Comisión canal", f"- {_money(quotation['commission'], currency)}"])
    tot_rows.append(["TOTAL", _money(quotation.get("total", 0), currency)])
    tot = Table(tot_rows, colWidths=[13 * cm, 3.5 * cm])
    tot.setStyle(TableStyle([
        ("ALIGN", (0, 0), (-1, -1), "RIGHT"),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ("TEXTCOLOR", (0, -1), (-1, -1), PRIMARY),
        ("FONTSIZE", (0, -1), (-1, -1), 13),
        ("LINEABOVE", (0, -1), (-1, -1), 1.5, PRIMARY),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(tot)

    # Includes / Excludes (flow naturally — no forced page break, deja a reportlab decidir)
    if package.get("includes") or package.get("excludes"):
        inc_exc_data = []
        if package.get("includes"):
            inc_text = "<b>Incluye:</b> " + " · ".join(f"✓ {x}" for x in package["includes"])
            inc_exc_data.append([Paragraph(inc_text, s["soft"])])
        if package.get("excludes"):
            exc_text = "<b>No incluye:</b> " + " · ".join(f"✗ {x}" for x in package["excludes"])
            inc_exc_data.append([Paragraph(exc_text, s["soft"])])
        if inc_exc_data:
            t = Table(inc_exc_data, colWidths=[17 * cm])
            t.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F8F9FA")),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("BOX", (0, 0), (-1, -1), 0.3, colors.HexColor("#E2E8F0")),
            ]))
            story.append(Spacer(1, 6))
            story.append(t)

    story.append(Spacer(1, 10))
    story.append(Paragraph(
        "<b>Condiciones generales:</b> Cotización válida por 7 días. Precios sujetos a disponibilidad al momento de la reservación. "
        "Política de cancelación según contrato. Precios por persona en MXN.",
        s["soft"],
    ))

    if not company.get("white_label"):
        story.append(Spacer(1, 16))
        story.append(Paragraph(
            "<font color='#94A3B8' size=8>Generado con Routiq · routiq.com.mx</font>",
            s["soft"],
        ))

    doc.build(story)
    return buf.getvalue()
