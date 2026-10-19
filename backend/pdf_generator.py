"""Generates a professional quotation PDF using ReportLab."""
from __future__ import annotations
import io
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, Flowable
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
    """Formato compacto DD/Mmm/AA (ej. 26/Sep/26) — cabe en celdas estrechas."""
    from datetime import date as _date
    try:
        d = _date.fromisoformat((iso or "")[:10])
        return f"{d.day:02d}/{_MESES_ABBR[d.month - 1].title()}/{d.year % 100:02d}"
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


def _fmt_concept_when(it: dict) -> str:
    """Fecha/hora según el tipo de concepto. Hospedaje => check-in→check-out (noches)."""
    if it.get("category") == "hospedaje" and (it.get("checkin") or it.get("checkout")):
        ci = _fmt_date(it["checkin"]) if it.get("checkin") else ""
        co = _fmt_date(it["checkout"]) if it.get("checkout") else ""
        rango = " – ".join([x for x in [ci, co] if x])
        n = int(it.get("nights", 0) or 0)
        if n:
            rango += f" ({n} {'noche' if n == 1 else 'noches'})"
        return rango
    return _fmt_service_datetime(it)


MARGIN_X = 1.0 * cm
MARGIN_Y = 0.95 * cm
PAGE_CONTENT_W = 19.5  # cm — Letter 21.59cm - 2×1.0cm margen
_CHANNEL_LABEL = {"agencia": "Agencia", "mayorista": "Mayorista", "operador": "Operador"}


class _ItinStart(Flowable):
    """Marca invisible: a partir de la siguiente página es la hoja de itinerario (sin pie de página)."""
    def wrap(self, aw, ah):
        return 0, 0

    def draw(self):
        self.canv._routiq_itin = True


def _footer_cb(company: dict):
    def _draw(canv, doc):
        if company.get("white_label") or getattr(canv, "_routiq_itin", False):
            return
        canv.saveState()
        canv.setFont("Helvetica", 7)
        canv.setFillColor(colors.HexColor("#94A3B8"))
        canv.drawString(MARGIN_X, 0.45 * cm, "Generado con Routiq · routiq.com.mx")
        canv.restoreState()
    return _draw


def _concept_cell(label: str, detail: str, style, extra: str = "") -> Paragraph:
    """Concepto en negritas con su detalle en gris pequeño debajo (misma celda)."""
    txt = f"<b>{_xml_escape(label or '')}</b>"
    for d in (detail, extra):
        d = (d or "").strip()
        if d:
            txt += f"<br/><font size='7.5' color='#64748B'>{_xml_escape(d).replace(chr(10), '<br/>')}</font>"
    return Paragraph(txt, style)


def _party_block(quotation: dict, client: dict):
    """Encabezado de la hoja de itinerario: agencia/mayorista + ejecutivo, o el cliente directo.
    Nunca incluye datos de la empresa emisora."""
    client = client or {}
    quotation = quotation or {}
    channel = client.get("channel") or "directo"
    agency = (quotation.get("contacts") or {}).get("agency") or {}
    if channel != "directo":
        exs = client.get("executives") or []
        ex = next((e for e in exs if e.get("id") == quotation.get("executive_id")), None) \
            or (exs[0] if len(exs) == 1 else {})
        name = client.get("name") or agency.get("name", "")
        lines = [("Ejecutivo", ex.get("name") or agency.get("contact", "")),
                 ("Tel.", ex.get("phone") or agency.get("phone", "") or client.get("phone", "")),
                 ("Correo", ex.get("email") or agency.get("email", "") or client.get("email", ""))]
        return _CHANNEL_LABEL.get(channel, "Agencia"), name, [x for x in lines if x[1]]
    name = client.get("name") or (quotation.get("client_snapshot") or {}).get("name", "")
    lines = [("Tel.", client.get("phone", "")), ("Correo", client.get("email", ""))]
    return "Cliente", name, [x for x in lines if x[1]]


def _build_itinerary_page(story, s, quotation: dict, client: dict, *, title: str, description: str,
                          trip_rows: list, days: list, itin_title: str, includes: list, excludes: list,
                          code: str = ""):
    """Hoja de itinerario en página propia: sin precios, sin monedas y sin datos de la empresa emisora."""
    includes = [x for x in (includes or []) if str(x).strip()]
    excludes = [x for x in (excludes or []) if str(x).strip()]
    days = [d for d in (days or []) if d[0] or d[1]]
    if not (days or includes or excludes or (description or "").strip()):
        return
    W = PAGE_CONTENT_W
    story.append(_ItinStart())
    story.append(PageBreak())
    label, name, lines = _party_block(quotation, client)
    contact = " · ".join(f"{k} {_xml_escape(str(v))}" for k, v in lines)
    party = Paragraph(
        f"<font size=8 color='#475569'>{label.upper()}</font><br/><b><font size=12>{_xml_escape(name or '')}</font></b>"
        + (f"<br/><font size=8.5 color='#475569'>{contact}</font>" if contact else ""), s["body"])
    right = Paragraph(f"<b><font color='#185FA5' size=14>ITINERARIO</font></b>"
                      + (f"<br/><font size=9 color='#475569'>{_xml_escape(code)}</font>" if code else ""), s["body"])
    hdr = Table([[party, right]], colWidths=[(W - 5.0) * cm, 5.0 * cm])
    hdr.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("ALIGN", (-1, 0), (-1, 0), "RIGHT"),
        ("LINEBELOW", (0, 0), (-1, -1), 2, PRIMARY),
        ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(hdr)
    story.append(Spacer(1, 6))
    if title:
        story.append(Paragraph(_xml_escape(title), s["title"]))
    trip_rows = [(k, v) for k, v in trip_rows if v]
    if trip_rows:
        data = [[Paragraph(f"<b>{_xml_escape(k)}</b>", s["soft"]), Paragraph(_xml_escape(str(v)), s["body"])] for k, v in trip_rows]
        t = Table(data, colWidths=[3.5 * cm, (W - 3.5) * cm])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (0, -1), PASTEL), ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#E2E8F0")),
            ("LEFTPADDING", (0, 0), (-1, -1), 6), ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        story.append(t)
    if (description or "").strip():
        story.append(Spacer(1, 6))
        story.append(Paragraph(_xml_escape(description.strip()), s["body"]))
    if days:
        story.append(Paragraph(itin_title, s["h2"]))
        for head, desc in days:
            if head:
                story.append(Paragraph(f"<b>{_xml_escape(head)}</b>", s["h3"]))
            if desc:
                story.append(Paragraph(_xml_escape(desc).replace("\n", "<br/>"), s["body"]))
    li = ParagraphStyle("incexc_li", parent=s["body"], leftIndent=12, firstLineIndent=-10, spaceAfter=1)
    for head, items, mark, color in (("Incluye", includes, "✔", "#15803D"), ("No incluye", excludes, "✘", "#B91C1C")):
        if items:
            story.append(Paragraph(head, s["h2"]))
            for x in items:
                story.append(Paragraph(f"<font color='{color}'>{mark}</font>  {_xml_escape(str(x))}", li))


def build_booking_totals(price_per_person: float, total: float, currency: str, width_cm: float = PAGE_CONTENT_W) -> Table:
    """Bloque de totales de la Confirmación (Precio por persona + Total a pagar). Reutilizable."""
    rows = []
    if price_per_person > 0:
        rows.append(["Precio por persona", _money(price_per_person, currency)])
    rows.append(["Total a pagar", _money(total, currency)])
    t = Table(rows, colWidths=[(width_cm - 4.5) * cm, 4.5 * cm])
    t.setStyle(TableStyle([
        ("ALIGN", (0, 0), (-1, -1), "RIGHT"),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ("TEXTCOLOR", (0, -1), (-1, -1), PRIMARY),
        ("FONTSIZE", (0, -1), (-1, -1), 12),
        ("LINEABOVE", (0, -1), (-1, -1), 1, PRIMARY),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    return t


def _important_info(story, s, quotation: dict):
    important = [p.strip() for p in (quotation.get("important_info") or "").split("\n") if p.strip()]
    if not important:
        return
    story.append(Spacer(1, 6))
    story.append(Paragraph("Información importante", s["h2"]))
    for para in important:
        story.append(Paragraph(_xml_escape(para), s["body"]))


def generate_quotation_pdf(company: dict, quotation: dict, package: dict, client: dict,
                           exec_name: str = "", base_url: str = "") -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter,
                            leftMargin=MARGIN_X, rightMargin=MARGIN_X,
                            topMargin=MARGIN_Y, bottomMargin=MARGIN_Y,
                            title=f"Cotización {quotation.get('code', '')}")
    s = _styles()
    story = []
    CONTENT_W = PAGE_CONTENT_W

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
                    logo_cell = RLImage(str(logo_path), width=3.2 * cm, height=3.2 * cm, kind="proportional")
                    break
                except Exception:
                    logo_cell = ""

    company_text = Paragraph(
        f"<b><font size=12>{company['name']}</font></b><br/><font size=8.5 color='#475569'>"
        f"{company.get('contact_phone','')}<br/>{company.get('contact_email','')}<br/>{company.get('address','')}</font>",
        s["body"],
    )
    cot_text = Paragraph(
        f"<b><font color='#185FA5' size=16>COTIZACIÓN</font></b><br/><font size=10>{quotation.get('code','')}</font><br/><font size=8.5 color='#475569'>{_fmt_date(quotation.get('created_at',''))}</font>",
        s["body"],
    )
    if logo_cell:
        header_data = [[logo_cell, company_text, cot_text]]
        col_widths = [3.5 * cm, (CONTENT_W - 9.0) * cm, 5.5 * cm]
    else:
        header_data = [[company_text, cot_text]]
        col_widths = [(CONTENT_W - 6.0) * cm, 6.0 * cm]
    header = Table(header_data, colWidths=col_widths)
    header.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (-1, 0), (-1, 0), "RIGHT"),
        ("LINEBELOW", (0, 0), (-1, -1), 2, PRIMARY),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    story.append(header)
    story.append(Spacer(1, 6))

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

    # Datos del cliente — un solo recuadro (sin línea suelta que duplique la info).
    contacts = quotation.get("contacts") or {}
    agency = contacts.get("agency") or {}
    traveler = contacts.get("traveler") or {}
    ct_rows = []
    if any(agency.values()) or any(traveler.values()):
        if any(agency.values()):
            agency_line = " · ".join([x for x in [agency.get('contact', ''), agency.get('phone', ''), agency.get('email', '')] if x])
            ct_rows.append([
                Paragraph("<b>Agencia / Vendedor</b>", s["body"]),
                Paragraph(f"{agency.get('name','')}<br/><font color='#475569' size=8>{agency_line}</font>", s["soft"]),
            ])
        if any(traveler.values()):
            ct_rows.append([
                Paragraph("<b>Cliente final / Turista</b>", s["body"]),
                Paragraph(f"{traveler.get('name','')}<br/><font color='#475569' size=8>Tel: {traveler.get('phone','')}</font>", s["soft"]),
            ])
    else:
        ct_rows.append([
            Paragraph("<b>Cliente</b>", s["body"]),
            Paragraph(f"{client.get('name','')}<br/><font color='#475569' size=8>{client.get('email','')} · {client.get('phone','')}</font>", s["soft"]),
        ])
    story.append(Paragraph("Datos del cliente", s["h2"]))
    ct = Table(ct_rows, colWidths=[4.3 * cm, (CONTENT_W - 4.3) * cm])
    ct.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), PASTEL),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
        ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(ct)

    # Detalles de reservación
    is_services = quotation.get("type") == "servicios" or not package.get("name")
    is_custom = quotation.get("type") == "personalizado"
    title_txt = "Servicios a la carta" if is_services else package.get("name", "")
    dates = quotation.get("dates", {}) or {}
    # Defensive: ensure start <= end (some legacy quotations may have them swapped)
    d_start = dates.get("start", "") or ""
    d_end = dates.get("end", "") or ""
    if d_start and d_end and d_start > d_end:
        d_start, d_end = d_end, d_start
    pax = quotation.get("pax", {})
    story.append(Paragraph("Detalles de reservación", s["h2"]))

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
    if not is_services and package.get("name"):
        meta_rows.append(["Paquete", package.get("name", "")])
    if quotation.get("hotel_selected"):
        meta_rows.append(["Hotel", quotation.get("hotel_selected", "")])
    if d_start or d_end:
        meta_rows.append(["Fechas", f"{_fmt_date(d_start)} – {_fmt_date(d_end)}"])
    if not is_services and nights_total:
        meta_rows.append(["Noches", nights_label])
    meta_rows.append(["Pax" if (is_services or is_custom) else "Habitaciones / Pax", pax_desc])
    meta = Table(meta_rows, colWidths=[3.5 * cm, (CONTENT_W - 3.5) * cm])
    meta.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), PASTEL),
        ("TEXTCOLOR", (0, 0), (0, -1), PRIMARY),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9.5),
        ("ROWBACKGROUNDS", (1, 0), (1, -1), [colors.white, colors.HexColor("#F8F9FA")]),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    story.append(meta)

    # Tabla de opciones de ocupación — SOLO cuando el ejecutivo activa "Mostrar todas las opciones".
    # Cuando está desactivado, el desglose línea por línea es la única referencia de precios.
    if (not is_services and not is_custom and quotation.get("hotel_selected")
            and bool(quotation.get("show_all_occupancies"))):
        sel_hotel = next((h for h in (package.get("hotels") or [])
                          if h.get("name") == quotation.get("hotel_selected")), None)
        if sel_hotel:
            from pricing import occupancy_rows_all
            cur_occ = quotation.get("currency", "MXN")
            pc = company.get("pricing_config") or {}
            divisor = float(pc.get("margin_divisor", 0.76) or 0.76)
            commissions = pc.get("commissions", {}) or {}
            channel = (client or {}).get("channel", "directo")
            data_rows = occupancy_rows_all(sel_hotel, channel, divisor, commissions)
            has_total = any(r.get("total") is not None for r in data_rows)
            if data_rows:
                if has_total:
                    occ_rows = [["Ocupación", "Precio por persona", "Total"]]
                    occ_rows += [[r["label"], _money(r["per_person"], cur_occ), _money(r["total"], cur_occ)] for r in data_rows]
                    col_widths = [8 * cm, 5.5 * cm, (CONTENT_W - 13.5) * cm]
                else:
                    occ_rows = [["Ocupación", "Precio por persona"]]
                    occ_rows += [[r["label"], _money(r["per_person"], cur_occ)] for r in data_rows]
                    col_widths = [11 * cm, (CONTENT_W - 11) * cm]
                story.append(Spacer(1, 8))
                story.append(Paragraph(f"Opciones de ocupación — {sel_hotel.get('name','')}", s["h2"]))
                ot = Table(occ_rows, colWidths=col_widths)
                ot.setStyle(TableStyle([
                    ("BACKGROUND", (0, 0), (-1, 0), PRIMARY),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
                    ("FONTSIZE", (0, 0), (-1, -1), 9),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8F9FA")]),
                    ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#E2E8F0")),
                    ("LEFTPADDING", (0, 0), (-1, -1), 6), ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                    ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ]))
                story.append(ot)
                note = (quotation.get("price_note") or "").strip()
                if note:
                    story.append(Spacer(1, 3))
                    story.append(Paragraph(f"<font color='#475569'><i>{_xml_escape(note)}</i></font>", s["soft"]))

    # Desglose de precios — punto 1: detallado (columnas) vs simple (solo conceptos + total).
    show_breakdown = quotation.get("show_price_breakdown", True)
    if show_breakdown is None:
        show_breakdown = True
    story.append(Spacer(1, 8))
    currency = quotation.get("currency", "MXN")
    concept_style = ParagraphStyle("concept", parent=s["soft"], textColor=TEXT, fontSize=8.5, leading=11)
    items = quotation.get("items", [])
    # Iter 71: Mayorista internacional -> USD primero (presentación; el cobro sigue en MXN).
    import fx_presentation
    bd_pp = None
    if quotation.get("show_per_person"):
        try:
            from pricing_breakdown import build_per_person_breakdown
            bd_pp = build_per_person_breakdown(quotation)
        except Exception:
            bd_pp = None
    usd = fx_presentation.build(quotation, bd_pp)
    usd = usd if usd and usd.get("available") else None
    small = "<font size='7' color='#64748B'>"
    if show_breakdown:
        story.append(Paragraph("Desglose de precios" + (" <font size='9' color='#64748B'>(detalle en MXN)</font>" if usd else ""), s["h2"]))
        if not is_services and package.get("name"):
            story.append(Paragraph(f"<b>Paquete:</b> {_xml_escape(package.get('name',''))}", s["soft"]))
        rows = [["Fecha", "Concepto", "Cant.", "$ unitario", "Subtotal"]]
        for it in items:
            fecha = _fmt_concept_when(it) or "—"
            rows.append([
                Paragraph(_xml_escape(fecha), concept_style),
                _concept_cell(it.get("label", ""), it.get("description", ""), concept_style),
                str(it.get("qty", "")),
                _money(it["unit_price"], currency), _money(it["subtotal"], currency),
            ])
        price_table = Table(rows, colWidths=[2.6 * cm, (CONTENT_W - 10.4) * cm, 1.3 * cm, 3.1 * cm, 3.4 * cm], repeatRows=1)
        price_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), PRIMARY),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("ALIGN", (2, 1), (-1, -1), "RIGHT"),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("FONTSIZE", (0, 0), (-1, -1), 8.5),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8F9FA")]),
            ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#E2E8F0")),
            ("LEFTPADDING", (0, 0), (-1, -1), 5),
            ("RIGHTPADDING", (0, 0), (-1, -1), 5),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        story.append(price_table)
    else:
        story.append(Paragraph("Conceptos incluidos", s["h2"]))
        if not is_services and package.get("name"):
            story.append(Paragraph(f"<b>Paquete:</b> {_xml_escape(package.get('name',''))}", s["soft"]))
        li_style = ParagraphStyle("concept_li", parent=concept_style, leftIndent=10, spaceAfter=2)
        for it in items:
            story.append(_concept_cell(f"• {it.get('label', '')}", it.get("description", ""), li_style))
    story.append(Spacer(1, 8))

    # Totals — en modo simple solo se muestra el TOTAL.
    tot_rows = []
    if show_breakdown:
        tot_rows.append(["Subtotal", _money(quotation.get("subtotal", 0), currency)])
        if quotation.get("commission", 0) > 0:
            tot_rows.append(["Comisión canal", f"- {_money(quotation['commission'], currency)}"])
    if usd:
        tot_rows.append(["TOTAL", Paragraph(f"<para alignment='right'><font size='13' color='{PRIMARY.hexval().replace('0x', '#')}'><b>US${usd['total_usd']:,.2f}</b></font><br/>{small}{_money(usd['total_mxn'], currency)}</font></para>", s["soft"])])
    else:
        tot_rows.append(["TOTAL", _money(quotation.get("total", 0), currency)])
    tot = Table(tot_rows, colWidths=[(CONTENT_W - 4.5) * cm, 4.5 * cm])
    tot.setStyle(TableStyle([
        ("ALIGN", (0, 0), (-1, -1), "RIGHT"),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ("TEXTCOLOR", (0, -1), (-1, -1), PRIMARY),
        ("FONTSIZE", (0, -1), (-1, -1), 13),
        ("LINEABOVE", (0, -1), (-1, -1), 1.5, PRIMARY),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    story.append(tot)

    # Precio por persona según ocupación (presentación; Iter 6). Suma exacta al total.
    if quotation.get("show_per_person"):
        bd = bd_pp
        if bd and bd.get("rows") and usd and usd.get("rows"):
            story.append(Spacer(1, 12))
            story.append(Paragraph("Precio por persona según ocupación", s["h2"]))
            pp_rows = [["Concepto", "Personas", "Subtotal"]]
            for r in usd["rows"]:
                txt = (f"{r.get('title') or r['label']}: <font size='11'><b>US${r['price_per_person_usd']:,.2f}</b></font> ({r['pax']} personas)"
                       f"<br/>{small}{_money(r['price_per_person_mxn'], currency)}</font>")
                sub = f"<para alignment='right'><b>US${r['subtotal_usd']:,.2f}</b><br/>{small}{_money(r['subtotal_mxn'], currency)}</font></para>"
                pp_rows.append([Paragraph(txt, concept_style), str(r["pax"]), Paragraph(sub, concept_style)])
            pp_rows.append(["Total", str(bd["total_pax"]), Paragraph(
                f"<para alignment='right'><b>US${usd['total_usd']:,.2f}</b><br/>{small}{_money(bd['total'], currency)}</font></para>", concept_style)])
            ppt = Table(pp_rows, colWidths=[(CONTENT_W - 7) * cm, 2.5 * cm, 4.5 * cm])
            ppt.setStyle(TableStyle([
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EAF1FA")),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
                ("LINEABOVE", (0, -1), (-1, -1), 1, PRIMARY),
                ("ALIGN", (1, 0), (-1, -1), "RIGHT"), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]))
            story.append(ppt)
            if bd.get("note"):
                story.append(Spacer(1, 3))
                story.append(Paragraph(f"<font color='#475569'><i>{_xml_escape(bd['note'])}</i></font>", s["soft"]))
        elif bd and bd.get("rows"):
            story.append(Spacer(1, 12))
            story.append(Paragraph("Precio por persona según ocupación", s["h2"]))
            pp_rows = [["Concepto", "Personas", "Subtotal"]]
            for r in bd["rows"]:
                txt = f"{r.get('title') or r['label']}: <b>{_money(r['price_per_person'], currency)}</b> ({r['pax']} personas)"
                pp_rows.append([Paragraph(txt, concept_style), str(r["pax"]), _money(r["subtotal"], currency)])
            pp_rows.append(["Total", str(bd["total_pax"]), _money(bd["total"], currency)])
            ppt = Table(pp_rows, colWidths=[(CONTENT_W - 6) * cm, 2.5 * cm, 3.5 * cm])
            ppt.setStyle(TableStyle([
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EAF1FA")),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
                ("TEXTCOLOR", (0, -1), (-1, -1), PRIMARY),
                ("LINEABOVE", (0, -1), (-1, -1), 1, PRIMARY),
                ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
                ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]))
            story.append(ppt)
            if bd.get("note"):
                story.append(Spacer(1, 3))
                story.append(Paragraph(f"<font color='#475569'><i>{_xml_escape(bd['note'])}</i></font>", s["soft"]))

    if usd:
        story.append(Spacer(1, 4))
        story.append(Paragraph(f"<font color='#475569'><i>{_xml_escape(usd['note'])}</i></font>", s["soft"]))
    price_note = (quotation.get("price_note") or "").strip()
    if price_note:
        story.append(Spacer(1, 4))
        story.append(Paragraph(
            f"<font color='#475569'><i>{_xml_escape(price_note)}</i></font>",
            ParagraphStyle("note", parent=s["soft"], alignment=TA_LEFT),
        ))

    _important_info(story, s, quotation)

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


    # ---- Hoja de itinerario (página propia, sin precios ni datos de la empresa) ----
    hotel_desc = quotation.get("hotel_selected") or ", ".join(
        dict.fromkeys(it.get("label", "") for it in items if it.get("category") == "hospedaje" and it.get("label")))
    _build_itinerary_page(
        story, s, quotation, client, code=quotation.get("code", ""),
        title=title_txt,
        description=(package.get("description") or "") if not is_services else "",
        trip_rows=[("Fechas", f"{_fmt_date(d_start)} – {_fmt_date(d_end)}" if (d_start or d_end) else ""),
                   ("Noches", str(nights_total) if not is_services and nights_total else ""),
                   ("Pasajeros", pax_desc), ("Hospedaje", hotel_desc)],
        days=[(f"Día {d.get('day', '')}: {d.get('title', '')}".strip(), (d.get("description") or "").strip())
              for d in (package.get("itinerary") or [])],
        itin_title="Itinerario día a día",
        includes=package.get("includes") or [], excludes=package.get("excludes") or [])

    doc.build(story, onFirstPage=_footer_cb(company), onLaterPages=_footer_cb(company))
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


def _kv2_table(pairs, width_cm: float):
    """Datos generales en dos columnas (etiqueta | valor | etiqueta | valor)."""
    st = _styles()
    cells = [[Paragraph(f"<b>{_xml_escape(k)}</b>", st["soft"]), Paragraph(_xml_escape(str(v or "—")), st["body"])] for k, v in pairs]
    data = [cells[i] + (cells[i + 1] if i + 1 < len(cells) else ["", ""]) for i in range(0, len(cells), 2)]
    lw = 3.3
    vw = width_cm / 2 - lw
    t = Table(data, colWidths=[lw * cm, vw * cm, lw * cm, vw * cm])
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BACKGROUND", (0, 0), (0, -1), PASTEL), ("BACKGROUND", (2, 0), (2, -1), PASTEL),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#E2E8F0")),
        ("LEFTPADDING", (0, 0), (-1, -1), 5), ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    return t


def _grid_table(header, rows, col_widths):
    s = _styles()
    hdr_style = ParagraphStyle("gridhdr", parent=s["soft"], textColor=colors.white, fontName="Helvetica-Bold", fontSize=8.5)
    data = [[Paragraph(f"<b>{_xml_escape(h)}</b>", hdr_style) for h in header]]
    for r in rows:
        data.append([c if isinstance(c, Paragraph) else Paragraph(_xml_escape(str(c or "")), s["body"]) for c in r])
    t = Table(data, colWidths=[w * cm for w in col_widths], repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), PRIMARY),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8F9FA")]),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#E2E8F0")),
        ("LEFTPADDING", (0, 0), (-1, -1), 5), ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    return t


def generate_booking_confirmation_pdf(company: dict, quotation: dict, confirmation: dict,
                                      client: dict, base_url: str = "") -> bytes:
    """PDF de Confirmación de Reserva — generado por el ejecutivo desde una cotización ganada."""
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter, leftMargin=MARGIN_X, rightMargin=MARGIN_X,
                            topMargin=MARGIN_Y, bottomMargin=MARGIN_Y,
                            title=f"Confirmación {confirmation.get('code', '')}")
    s = _styles()
    story = []
    ccy = quotation.get("currency", "MXN")
    W = PAGE_CONTENT_W

    logo_cell = _load_logo(company, 3.2)
    company_text = Paragraph(
        f"<b><font size=12>{_xml_escape(company.get('name',''))}</font></b><br/><font size=8.5 color='#475569'>"
        f"{_xml_escape(company.get('contact_phone',''))}<br/>{_xml_escape(company.get('contact_email',''))}<br/>{_xml_escape(company.get('address',''))}</font>",
        s["body"])
    title_text = Paragraph(
        f"<b><font color='#185FA5' size=13>CONFIRMACIÓN DE RESERVA</font></b><br/><font size=10>{_xml_escape(confirmation.get('code',''))}</font>"
        f"<br/><font size=8.5 color='#475569'>{_fmt_date(confirmation.get('created_at',''))}</font>",
        s["body"])
    if logo_cell:
        header = Table([[logo_cell, company_text, title_text]], colWidths=[3.5 * cm, (W - 10.0) * cm, 6.5 * cm])
    else:
        header = Table([[company_text, title_text]], colWidths=[(W - 7.0) * cm, 7.0 * cm])
    header.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (-1, 0), (-1, 0), "RIGHT"),
        ("LINEBELOW", (0, 0), (-1, -1), 2, PRIMARY),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    story.append(header)
    story.append(Spacer(1, 4))

    # Sello de estado de pago (Iter 4 punto 3). auto = deriva de payment_status; el ejecutivo puede sobrescribir.
    _stamp = confirmation.get("payment_stamp", "auto")
    _paid = (quotation.get("payment_status") == "paid") if _stamp == "auto" else (_stamp == "paid")
    _stamp_txt = "PAGADO" if _paid else "PENDIENTE DE PAGO"
    _stamp_bg = colors.HexColor("#DCFCE7") if _paid else colors.HexColor("#FEF3C7")
    _stamp_fg = "#15803D" if _paid else "#B45309"
    _stamp_bd = colors.HexColor("#16A34A") if _paid else colors.HexColor("#D97706")
    _stamp_cell = Paragraph(f"<b><font size=12 color='{_stamp_fg}'>{_stamp_txt}</font></b>", s["body"])
    _stamp_tbl = Table([[_stamp_cell]], colWidths=[5.2 * cm], hAlign="RIGHT")
    _stamp_tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), _stamp_bg),
        ("BOX", (0, 0), (-1, -1), 1.2, _stamp_bd),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(_stamp_tbl)
    story.append(Spacer(1, 6))
    story.append(_kv2_table([
        ("Ejecutivo", confirmation.get("agent_name", "")), ("Empresa", confirmation.get("agent_company", "")),
        ("Correo del ejecutivo", confirmation.get("agent_email", "")), ("Teléfono", confirmation.get("agent_phone", "")),
        ("Fecha de reservación", _fmt_date(confirmation.get("reservation_date", ""))), ("Número de personas", confirmation.get("num_persons", "")),
        ("Pasajero final", confirmation.get("passenger_name", "")), ("Teléfono del pasajero", confirmation.get("passenger_phone", "")),
    ], W))
    story.append(Spacer(1, 6))

    qtype = quotation.get("type", "paquete")
    if qtype == "servicios":
        sec_label = "Servicios a la carta"
    elif qtype == "personalizado":
        sec_label = quotation.get("custom_title") or "Programa personalizado"
    else:
        sec_label = (quotation.get("package_snapshot") or {}).get("name") or "Paquete"
    body = s["body"]
    services = confirmation.get("services") or []
    if services:
        story.append(Paragraph(f"Servicios confirmados · {_xml_escape(sec_label)}", s["h2"]))
        rows = [[Paragraph(_xml_escape(_fmt_date(x.get("date", ""))), body),
                 _concept_cell(x.get("service", ""), x.get("details", ""), body, x.get("observations", "")),
                 Paragraph(_xml_escape(str(x.get("persons", "") or "")), body)] for x in services]
        story.append(_grid_table(["Fecha", "Servicio", "Pers."], rows, [2.6, W - 4.2, 1.6]))
        story.append(Spacer(1, 6))

    lodging = confirmation.get("lodging") or []
    if lodging:
        story.append(Paragraph("Hospedaje", s["h2"]))
        rows = [[x.get("hotel", ""), x.get("plan", ""), _fmt_date(x.get("checkin", "")), _fmt_date(x.get("checkout", "")),
                 x.get("nights", ""), x.get("room_type", ""), x.get("confirmation_number", ""), x.get("guest_name", "")] for x in lodging]
        story.append(_grid_table(["Hotel", "Plan", "Check-in", "Check-out", "Noches", "Habitación", "N° Conf.", "Huésped"],
                                 rows, [3.2, 2.0, 1.9, 1.9, 1.6, 2.6, 2.5, 3.8]))
        story.append(Spacer(1, 6))

    if (confirmation.get("general_observations") or "").strip():
        story.append(Paragraph("Observaciones generales", s["h2"]))
        for para in confirmation["general_observations"].split("\n"):
            if para.strip():
                story.append(Paragraph(_xml_escape(para.strip()), s["body"]))
        story.append(Spacer(1, 6))

    _important_info(story, s, quotation)
    story.append(Spacer(1, 6))

    story.append(build_booking_totals(float(confirmation.get("price_per_person", 0) or 0),
                                      float(confirmation.get("total_amount", 0) or 0), ccy, W))
    story.append(Spacer(1, 8))

    # Datos bancarios
    bank = company.get("bank") or {}
    if any(bank.get(k) for k in ("name", "clabe", "account", "holder")):
        story.append(Paragraph("Datos para transferencia bancaria", s["h2"]))
        story.append(_kv2_table([
            ("Banco", bank.get("name", "")), ("Beneficiario", bank.get("holder", "")),
            ("Cuenta", bank.get("account", "")), ("CLABE", bank.get("clabe", "")),
            ("Sucursal", bank.get("branch", "")), ("SWIFT/BIC", bank.get("swift", "")),
            ("Referencia", bank.get("reference", "")),
        ], W))
        story.append(Spacer(1, 8))

    if bool(company.get("stripe_allowed", True)) and ((company.get("stripe") or {}).get("secret_key") or False):
        story.append(Paragraph("<i>También puedes pagar con tarjeta de crédito/débito de forma segura; solicita el enlace de pago a tu ejecutivo.</i>", s["soft"]))
        story.append(Spacer(1, 8))

    # Enlace clickeable a condiciones generales y políticas de cancelación (en vez del texto completo)
    slug = company.get("slug", "")
    if (company.get("general_conditions") or company.get("cancellation_policy")) and slug:
        cond_url = f"{base_url}/c/{slug}/condiciones" if base_url else f"https://routiq.com.mx/c/{slug}/condiciones"
        story.append(Spacer(1, 6))
        story.append(Paragraph(
            f'<a href="{cond_url}"><font color="#185FA5"><u>Consultar condiciones generales y políticas de cancelación</u></font></a>',
            s["soft"],
        ))


    # ---- Hoja de itinerario (página propia, sin precios ni datos de la empresa) ----
    itinerary = confirmation.get("itinerary") or []
    dates = quotation.get("dates") or {}
    d_start, d_end = dates.get("start", "") or "", dates.get("end", "") or ""
    if d_start and d_end and d_start > d_end:
        d_start, d_end = d_end, d_start
    _build_itinerary_page(
        story, s, quotation, client, code=confirmation.get("code", ""),
        title=sec_label, description="",
        trip_rows=[("Fechas", f"{_fmt_date(d_start)} – {_fmt_date(d_end)}" if (d_start or d_end) else ""),
                   ("Noches", str(quotation.get("nights_total") or "") if qtype != "servicios" else ""),
                   ("Pasajeros", f"{confirmation.get('num_persons')} persona(s)" if confirmation.get("num_persons") else ""),
                   ("Pasajero titular", confirmation.get("passenger_name", "")),
                   ("Hospedaje", ", ".join(dict.fromkeys(x.get("hotel", "") for x in lodging if x.get("hotel"))))],
        days=[((e.get("title") or "").strip(), (e.get("description") or "").strip()) for e in itinerary],
        itin_title=("Itinerario día a día" if qtype == "paquete"
                    else "Descripción de servicios" if qtype == "servicios" else "Programa detallado"),
        includes=confirmation.get("_includes") or [], excludes=confirmation.get("_excludes") or [])

    doc.build(story, onFirstPage=_footer_cb(company), onLaterPages=_footer_cb(company))
    return buf.getvalue()
