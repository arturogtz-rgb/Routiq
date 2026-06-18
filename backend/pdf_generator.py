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


# ---------------------------------------------------------------------------
# Rich-text (cancellation policy) → ReportLab flowables
# ReportLab Paragraph only understands a tiny inline subset (<b>,<i>,<u>,<br/>),
# so we translate block tags (<p>,<ul>,<ol>,<li>,<h*>) into separate paragraphs.
# ---------------------------------------------------------------------------
from html.parser import HTMLParser


def _xml_escape(t: str) -> str:
    return t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


class _PolicyHTMLParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.blocks = []      # list of (kind, inline_html)
        self._buf = []
        self._list_stack = []
        self._ol_counters = []

    def _flush(self, kind="p"):
        text = "".join(self._buf).strip()
        if text:
            self.blocks.append((kind, text))
        self._buf = []

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag in ("p", "div", "h1", "h2", "h3", "h4"):
            self._flush()
        elif tag == "br":
            self._buf.append("<br/>")
        elif tag in ("ul", "ol"):
            self._flush()
            self._list_stack.append(tag)
            self._ol_counters.append(0)
        elif tag == "li":
            self._flush()
        elif tag in ("b", "strong"):
            self._buf.append("<b>")
        elif tag in ("i", "em"):
            self._buf.append("<i>")
        elif tag == "u":
            self._buf.append("<u>")

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag in ("p", "div"):
            self._flush()
        elif tag in ("h1", "h2", "h3", "h4"):
            self._flush("h")
        elif tag == "li":
            prefix = "•  "
            if self._list_stack and self._list_stack[-1] == "ol":
                self._ol_counters[-1] += 1
                prefix = f"{self._ol_counters[-1]}.  "
            text = "".join(self._buf).strip()
            self._buf = []
            if text:
                self.blocks.append(("li", prefix + text))
        elif tag in ("ul", "ol"):
            if self._list_stack:
                self._list_stack.pop()
            if self._ol_counters:
                self._ol_counters.pop()
        elif tag in ("b", "strong"):
            self._buf.append("</b>")
        elif tag in ("i", "em"):
            self._buf.append("</i>")
        elif tag == "u":
            self._buf.append("</u>")

    def handle_data(self, data):
        self._buf.append(_xml_escape(data))


def _richtext_flowables(html: str, styles) -> list:
    parser = _PolicyHTMLParser()
    try:
        parser.feed(html or "")
        parser.close()
        parser._flush()
    except Exception:
        return [Paragraph(_xml_escape(html or ""), styles["soft"])]
    flows = []
    li_style = ParagraphStyle("policy_li", parent=styles["soft"], leftIndent=12, spaceAfter=2)
    for kind, text in parser.blocks:
        if kind == "li":
            flows.append(Paragraph(text, li_style))
        elif kind == "h":
            flows.append(Paragraph(f"<b>{text}</b>", styles["h3"]))
        else:
            flows.append(Paragraph(text, styles["soft"]))
    return flows


_MESES_ABBR = ["ENE", "FEB", "MAR", "ABR", "MAY", "JUN", "JUL", "AGO", "SEP", "OCT", "NOV", "DIC"]


def _fmt_date(iso: str) -> str:
    from datetime import date as _date
    try:
        d = _date.fromisoformat((iso or "")[:10])
        return f"{d.day:02d} {_MESES_ABBR[d.month - 1]} {d.year}"
    except Exception:
        return iso or ""


def _fmt_service_datetime(it: dict) -> str:
    """'12 AGO 2026 · 09:00–13:00' a partir de service_date/start_time/end_time."""
    parts = []
    if it.get("service_date"):
        parts.append(_fmt_date(it["service_date"]))
    st, et = (it.get("start_time") or "").strip(), (it.get("end_time") or "").strip()
    if st and et:
        parts.append(f"{st}–{et}")
    elif st:
        parts.append(st)
    return " · ".join(parts)


def generate_quotation_pdf(company: dict, quotation: dict, package: dict, client: dict,
                           exec_name: str = "", base_url: str = "") -> bytes:
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
                    logo_cell = RLImage(str(logo_path), width=4.6 * cm, height=4.6 * cm, kind="proportional")
                    break
                except Exception:
                    logo_cell = ""

    company_text = Paragraph(
        f"<b><font size=12>{company['name']}</font></b><br/><font size=9 color='#475569'>"
        f"{company.get('contact_phone','')}<br/>{company.get('contact_email','')}<br/>{company.get('address','')}</font>",
        s["body"],
    )
    cot_text = Paragraph(
        f"<b><font color='#185FA5' size=16>COTIZACIÓN</font></b><br/><font size=10>{quotation.get('code','')}</font><br/><font size=9 color='#475569'>{_fmt_date(quotation.get('created_at',''))}</font>",
        s["body"],
    )
    if logo_cell:
        header_data = [[logo_cell, company_text, cot_text]]
        col_widths = [5 * cm, 7 * cm, 5 * cm]
    else:
        header_data = [[company_text, cot_text]]
        col_widths = [11 * cm, 6 * cm]
    header = Table(header_data, colWidths=col_widths)
    header.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ALIGN", (-1, 0), (-1, 0), "RIGHT"),
        ("LINEBELOW", (0, 0), (-1, -1), 2, PRIMARY),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 14),
    ]))
    story.append(header)
    story.append(Spacer(1, 8))

    # Ciudad y fecha de emisión
    ciudad = (company.get("address", "") or "").strip()
    emision = _fmt_date(quotation.get("created_at", ""))
    emision_txt = (f"{ciudad}, a {emision}" if ciudad else (f"Fecha de emisión: {emision}" if emision else ""))
    if emision_txt:
        story.append(Paragraph(f"<font color='#475569'>{_xml_escape(emision_txt)}</font>", s["soft"]))
        story.append(Spacer(1, 6))

    # Presentation text (carta al cliente) — opens the document before any content
    presentation = (quotation.get("presentation_text") or "").strip()
    if presentation:
        for para in presentation.split("\n"):
            para = para.strip()
            if para:
                story.append(Paragraph(_xml_escape(para), s["body"]))
        story.append(Spacer(1, 10))

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
    is_custom = quotation.get("type") == "personalizado"
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
    elif is_services or is_custom:
        pax_desc = f"{pax.get('adultos', 0)} persona(s)"
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
    meta_rows.append(["Pax" if (is_services or is_custom) else "Habitaciones / Pax", pax_desc])
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

    # Tabla de precios por ocupación (solo paquetes) — precio por persona según el canal del cliente.
    if not is_services and not is_custom and quotation.get("hotel_selected"):
        sel_hotel = next((h for h in (package.get("hotels") or [])
                          if h.get("name") == quotation.get("hotel_selected")), None)
        if sel_hotel:
            from pricing import channel_price
            cur_occ = quotation.get("currency", "MXN")
            pc = company.get("pricing_config") or {}
            divisor = float(pc.get("margin_divisor", 0.76) or 0.76)
            commissions = pc.get("commissions", {}) or {}
            channel = (client or {}).get("channel", "directo")
            prices = sel_hotel.get("prices_by_occupancy", {}) or {}
            occ_rows = [["Ocupación", "Precio por persona"]]
            for key, label, paxlbl in [("sencilla", "Sencilla", "1 pax"), ("doble", "Doble", "2 pax"),
                                       ("triple", "Triple", "3 pax"), ("cuadruple", "Cuádruple", "4 pax")]:
                net = float(prices.get(key, 0) or 0)
                if net <= 0:
                    continue  # precio 0 = no disponible
                occ_rows.append([f"{label} ({paxlbl})", _money(channel_price(net, channel, divisor, commissions), cur_occ)])
            minor_net = float(sel_hotel.get("minor_price", 0) or 0)
            if minor_net > 0:
                occ_rows.append(["Menor", _money(channel_price(minor_net, channel, divisor, commissions), cur_occ)])
            if len(occ_rows) > 1:
                story.append(Spacer(1, 8))
                story.append(Paragraph(f"Precios por persona — {sel_hotel.get('name','')}", s["h2"]))
                ot = Table(occ_rows, colWidths=[10 * cm, 6.5 * cm])
                ot.setStyle(TableStyle([
                    ("BACKGROUND", (0, 0), (-1, 0), PRIMARY),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("ALIGN", (1, 0), (1, -1), "RIGHT"),
                    ("FONTSIZE", (0, 0), (-1, -1), 9),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8F9FA")]),
                    ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#E2E8F0")),
                    ("LEFTPADDING", (0, 0), (-1, -1), 6), ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                    ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ]))
                story.append(ot)

    # Price items
    # Salto de página automático cuando el contenido es extenso (presentación + itinerario
    # en la 1ª hoja, desglose de precios en la 2ª).
    if presentation and package.get("itinerary"):
        story.append(PageBreak())
    story.append(Paragraph("Desglose de precios", s["h2"]))
    currency = quotation.get("currency", "MXN")
    concept_style = ParagraphStyle("concept", parent=s["soft"], textColor=TEXT, fontSize=8.5, leading=11)
    rows = [["Concepto", "P. unitario", "Cant.", "Subtotal"]]
    for it in quotation.get("items", []):
        concept_html = f"<b>{_xml_escape(it.get('label',''))}</b>"
        sub = []
        if it.get("description"):
            sub.append(_xml_escape(it["description"]))
        dt = _fmt_service_datetime(it)
        if dt:
            sub.append(dt)
        if sub:
            concept_html += f"<br/><font size=7 color='#475569'>{' · '.join(sub)}</font>"
        rows.append([
            Paragraph(concept_html, concept_style),
            _money(it["unit_price"], currency), str(it["qty"]), _money(it["subtotal"], currency),
        ])
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

    price_note = (quotation.get("price_note") or "").strip()
    if price_note:
        story.append(Spacer(1, 4))
        story.append(Paragraph(
            f"<font color='#475569'><i>{_xml_escape(price_note)}</i></font>",
            ParagraphStyle("note", parent=s["soft"], alignment=TA_LEFT),
        ))
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

    # "Información importante" — texto libre por cotización (lo ve el cliente)
    important = (quotation.get("important_info") or "").strip()
    if important:
        story.append(Spacer(1, 10))
        story.append(Paragraph("Información importante", s["h2"]))
        for para in important.split("\n"):
            para = para.strip()
            if para:
                story.append(Paragraph(_xml_escape(para), s["body"]))

    # Texto fijo al pie
    story.append(Spacer(1, 10))
    story.append(Paragraph(
        "<i>Todos los precios están sujetos a cambio y disponibilidad sin previo aviso.</i>",
        s["soft"],
    ))

    # Enlace clickeable a condiciones generales y políticas de cancelación
    slug = company.get("slug", "")
    if slug:
        cond_url = f"{base_url}/c/{slug}/condiciones" if base_url else f"https://routiq.com.mx/c/{slug}/condiciones"
        story.append(Spacer(1, 4))
        story.append(Paragraph(
            f'<a href="{cond_url}"><font color="#185FA5"><u>Consultar condiciones generales y políticas de cancelación</u></font></a>',
            s["soft"],
        ))

    # Nombre del ejecutivo
    if exec_name:
        story.append(Spacer(1, 16))
        story.append(Paragraph(
            f"<b>{_xml_escape(exec_name)}</b><br/><font size=8 color='#475569'>{_xml_escape(company.get('name',''))}</font>",
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



def _load_logo(company: dict, size_cm: float = 4.0):
    from reportlab.platypus import Image as RLImage
    from pathlib import Path as _P
    logo_url = company.get("logo_url") or ""
    rel = logo_url.replace("/api/uploads/", "").replace("/uploads/", "")
    if not rel:
        return ""
    for logo_path in [_P("/app/uploads") / rel, _P(__file__).parent / "uploads" / rel]:
        if logo_path.exists() and logo_path.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp"):
            try:
                return RLImage(str(logo_path), width=size_cm * cm, height=size_cm * cm, kind="proportional")
            except Exception:
                return ""
    return ""


def _kv_table(rows, label_w=4.5, val_w=12.0):
    data = [[Paragraph(f"<b>{_xml_escape(k)}</b>", _styles()["soft"]), Paragraph(_xml_escape(str(v or "—")), _styles()["body"])] for k, v in rows]
    t = Table(data, colWidths=[label_w * cm, val_w * cm])
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ROWBACKGROUNDS", (0, 0), (-1, -1), [colors.white, colors.HexColor("#F8F9FA")]),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#E2E8F0")),
        ("LEFTPADDING", (0, 0), (-1, -1), 6), ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    return t


def _grid_table(header, rows, col_widths):
    s = _styles()
    data = [[Paragraph(f"<b>{_xml_escape(h)}</b>", s["soft"]) for h in header]]
    for r in rows:
        data.append([Paragraph(_xml_escape(str(c or "")), s["body"]) for c in r])
    t = Table(data, colWidths=[w * cm for w in col_widths], repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), PRIMARY),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8F9FA")]),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#E2E8F0")),
        ("LEFTPADDING", (0, 0), (-1, -1), 5), ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    return t


def generate_booking_confirmation_pdf(company: dict, quotation: dict, confirmation: dict,
                                      client: dict, base_url: str = "") -> bytes:
    """PDF de Confirmación de Reserva — generado por el ejecutivo desde una cotización ganada."""
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter, leftMargin=1.4 * cm, rightMargin=1.4 * cm,
                            topMargin=1.3 * cm, bottomMargin=1.3 * cm,
                            title=f"Confirmación {confirmation.get('code', '')}")
    s = _styles()
    story = []
    ccy = quotation.get("currency", "MXN")

    logo_cell = _load_logo(company, 4.0)
    company_text = Paragraph(
        f"<b><font size=12>{_xml_escape(company.get('name',''))}</font></b><br/><font size=9 color='#475569'>"
        f"{_xml_escape(company.get('contact_phone',''))}<br/>{_xml_escape(company.get('contact_email',''))}<br/>{_xml_escape(company.get('address',''))}</font>",
        s["body"])
    title_text = Paragraph(
        f"<b><font color='#185FA5' size=15>CONFIRMACIÓN DE RESERVA</font></b><br/><font size=10>{_xml_escape(confirmation.get('code',''))}</font>"
        f"<br/><font size=9 color='#475569'>{_fmt_date(confirmation.get('created_at',''))}</font>",
        s["body"])
    if logo_cell:
        header = Table([[logo_cell, company_text, title_text]], colWidths=[4.5 * cm, 6.5 * cm, 6 * cm])
    else:
        header = Table([[company_text, title_text]], colWidths=[10 * cm, 7 * cm])
    header.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ALIGN", (-1, 0), (-1, 0), "RIGHT"),
        ("LINEBELOW", (0, 0), (-1, -1), 2, PRIMARY),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 14),
    ]))
    story.append(header)
    story.append(Spacer(1, 10))

    # Header table (datos del agente/pasajero)
    story.append(_kv_table([
        ("Agente / Cliente", confirmation.get("agent_name") or client.get("name", "")),
        ("Teléfono", confirmation.get("agent_phone", "")),
        ("Empresa", confirmation.get("agent_company", "")),
        ("Fecha de reservación", confirmation.get("reservation_date", "")),
        ("Pasajero final", confirmation.get("passenger_name", "")),
        ("Teléfono del pasajero", confirmation.get("passenger_phone", "")),
        ("Número de personas", confirmation.get("num_persons", "")),
    ]))
    story.append(Spacer(1, 10))

    services = confirmation.get("services") or []
    if services:
        story.append(Paragraph("Servicios confirmados", s["h2"]))
        rows = [[x.get("date", ""), x.get("service", ""), x.get("details", ""), x.get("persons", ""), x.get("observations", "")] for x in services]
        story.append(_grid_table(["Fecha", "Servicio", "Detalles", "Pers.", "Observaciones"], rows, [2.3, 3.5, 4.2, 1.4, 5.0]))
        story.append(Spacer(1, 10))

    lodging = confirmation.get("lodging") or []
    if lodging:
        story.append(Paragraph("Hospedaje", s["h2"]))
        rows = [[x.get("hotel", ""), x.get("plan", ""), x.get("checkin", ""), x.get("checkout", ""),
                 x.get("nights", ""), x.get("room_type", ""), x.get("confirmation_number", ""), x.get("guest_name", "")] for x in lodging]
        story.append(_grid_table(["Hotel", "Plan", "Check-in", "Check-out", "Noches", "Habitación", "N° Conf.", "Huésped"],
                                 rows, [2.6, 1.9, 1.8, 1.8, 1.1, 2.1, 2.2, 2.9]))
        story.append(Spacer(1, 10))

    if (confirmation.get("general_observations") or "").strip():
        story.append(Paragraph("Observaciones generales", s["h2"]))
        for para in confirmation["general_observations"].split("\n"):
            if para.strip():
                story.append(Paragraph(_xml_escape(para.strip()), s["body"]))
        story.append(Spacer(1, 8))

    # Precio por persona + total
    pp = float(confirmation.get("price_per_person", 0) or 0)
    tot = float(confirmation.get("total_amount", 0) or 0)
    price_rows = []
    if pp > 0:
        price_rows.append(["Precio por persona", _money(pp, ccy)])
    price_rows.append(["Total a pagar", _money(tot, ccy)])
    pt = Table(price_rows, colWidths=[12.5 * cm, 4 * cm])
    pt.setStyle(TableStyle([
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ("TEXTCOLOR", (0, -1), (-1, -1), PRIMARY),
        ("FONTSIZE", (0, -1), (-1, -1), 12),
        ("LINEABOVE", (0, -1), (-1, -1), 1, PRIMARY),
        ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(pt)
    story.append(Spacer(1, 12))

    # Datos bancarios
    bank = company.get("bank") or {}
    if any(bank.get(k) for k in ("name", "clabe", "account", "holder")):
        story.append(Paragraph("Datos para transferencia bancaria", s["h2"]))
        story.append(_kv_table([
            ("Banco", bank.get("name", "")), ("Beneficiario", bank.get("holder", "")),
            ("Cuenta", bank.get("account", "")), ("Sucursal", bank.get("branch", "")),
            ("CLABE", bank.get("clabe", "")), ("SWIFT/BIC", bank.get("swift", "")),
            ("Referencia", bank.get("reference", "")),
        ]))
        story.append(Spacer(1, 8))

    if bool(company.get("stripe_allowed", True)) and ((company.get("stripe") or {}).get("secret_key") or False):
        story.append(Paragraph("<i>También puedes pagar con tarjeta de crédito/débito de forma segura; solicita el enlace de pago a tu ejecutivo.</i>", s["soft"]))
        story.append(Spacer(1, 8))

    # Políticas de cancelación + condiciones generales (completas)
    gen = (company.get("general_conditions") or "").strip()
    pol = (company.get("cancellation_policy") or "").strip()
    if gen:
        story.append(Paragraph("Condiciones generales", s["h2"]))
        for fl in _richtext_flowables(gen, s):
            story.append(fl)
    if pol:
        story.append(Paragraph("Políticas de cancelación", s["h2"]))
        for fl in _richtext_flowables(pol, s):
            story.append(fl)

    if not company.get("white_label"):
        story.append(Spacer(1, 14))
        story.append(Paragraph("<font color='#94A3B8' size=8>Generado con Routiq · routiq.com.mx</font>", s["soft"]))

    doc.build(story)
    return buf.getvalue()
