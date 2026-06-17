"""Bulk catalog import via Excel (.xlsx).

Provides a downloadable template (Paquetes / Tours / Traslados) and an import
endpoint that validates row-by-row and returns a per-row report of what was
imported and what failed. Admin-only.
"""
import io
import logging

import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from fastapi.responses import StreamingResponse

from database import get_db, new_id, now_iso
from auth import require_roles

log = logging.getLogger("routiq.catalog_import")
router = APIRouter()

XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
UNITS = {"per_person", "per_group", "per_day", "per_access"}

PKG_COLS = ["code", "name", "nights", "description", "includes", "excludes",
            "hotel_name", "sencilla", "doble", "triple", "cuadruple", "menor"]
SVC_COLS = ["name", "description", "net_price", "public_price", "unit"]

# Multi-hotel example: PKG-001 has TWO hotels — second row repeats the code and
# leaves the package-level columns blank (only the hotel columns are filled).
PKG_EXAMPLES = [
    ["PKG-001", "Tequila Express 2N", 2, "Tour a Tequila con cata",
     "Hospedaje;Desayunos;Tour", "Vuelos;Propinas",
     "Hotel Solar de las Ánimas", 3500, 2400, 2100, 1900, 1500],
    ["PKG-001", "", "", "", "", "",
     "Hotel Matices de Amatitán", 3900, 2700, 2300, 2050, 1600],
]
TOUR_EXAMPLES = [["City Tour Guadalajara", "Recorrido por el centro histórico", 600, 0, "per_person"]]
TRASLADO_EXAMPLES = [["Traslado Aeropuerto-Hotel", "Sedán privado hasta 4 pax", 800, 0, "per_group"]]


def _coerce_num(v, default=0.0):
    if v is None or v == "":
        return default
    try:
        return float(str(v).replace(",", "").replace("$", "").strip())
    except (ValueError, TypeError):
        raise ValueError("valor numérico inválido")


def _split_list(v):
    if not v:
        return []
    return [p.strip() for p in str(v).replace("\n", ";").replace(",", ";").split(";") if p.strip()]


# ---------------------------------------------------------------------------
# Template download
# ---------------------------------------------------------------------------
@router.get("/catalog/template")
async def download_template(user: dict = Depends(require_roles("company_admin"))):
    wb = openpyxl.Workbook()
    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill("solid", fgColor="185FA5")

    def build(ws, cols, examples):
        ws.append(cols)
        for c in ws[1]:
            c.font = header_font
            c.fill = header_fill
            c.alignment = Alignment(horizontal="center")
        for ex in examples:
            ws.append(ex)
        for i, _ in enumerate(cols, start=1):
            ws.column_dimensions[openpyxl.utils.get_column_letter(i)].width = 20

    ws1 = wb.active
    ws1.title = "Paquetes"
    build(ws1, PKG_COLS, PKG_EXAMPLES)
    build(wb.create_sheet("Tours"), SVC_COLS, TOUR_EXAMPLES)
    build(wb.create_sheet("Traslados"), SVC_COLS, TRASLADO_EXAMPLES)

    # Instructions sheet
    info = wb.create_sheet("Instrucciones")
    info.append(["Cómo usar esta plantilla"])
    info["A1"].font = Font(bold=True, size=14)
    for line in [
        "",
        "1. Llena cada hoja: Paquetes, Tours y Traslados.",
        "2. NO borres la fila de encabezados (fila 1). Las filas de ejemplo puedes reemplazarlas o borrarlas.",
        "",
        "PAQUETES — columnas obligatorias: code, name, nights.",
        "   • includes/excludes: separa cada elemento con punto y coma (;).",
        "   • sencilla/doble/triple/cuadruple/menor: precios por ocupación de ESE hotel (numéricos).",
        "",
        "MÚLTIPLES HOTELES EN UN MISMO PAQUETE  ← (formato correcto):",
        "   • Usa UNA FILA POR HOTEL repitiendo el MISMO 'code' en cada fila.",
        "   • En la PRIMERA fila del paquete escribe todos los datos (code, name, nights,",
        "     description, includes, excludes) y los datos del primer hotel.",
        "   • En las filas siguientes repite SOLO el 'code' y llena las columnas del hotel",
        "     (hotel_name, sencilla, doble, triple, cuadruple, menor). Deja vacías name, nights,",
        "     description, includes y excludes: se toman de la primera fila.",
        "   • Ejemplo: en la hoja 'Paquetes', las filas 2 y 3 son el paquete PKG-001 con dos hoteles.",
        "   • También funciona si dejas la columna 'code' vacía en las filas de hoteles adicionales:",
        "     se asignarán automáticamente al paquete de la fila anterior.",
        "",
        "TOURS / TRASLADOS — columna obligatoria: name.",
        "   • net_price = costo; public_price = precio de venta (déjalo en 0 para autocalcular con tu margen).",
        "   • unit: per_person, per_group, per_day o per_access.",
        "",
        "3. Guarda el archivo y súbelo desde el panel: Catálogo → Importar Excel.",
    ]:
        info.append([line])
    info.column_dimensions["A"].width = 95

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return StreamingResponse(
        buf, media_type=XLSX_MIME,
        headers={"Content-Disposition": 'attachment; filename="routiq-catalogo-template.xlsx"'},
    )


# ---------------------------------------------------------------------------
# Export current catalog (same format as the template)
# ---------------------------------------------------------------------------
@router.get("/catalog/export")
async def export_catalog(user: dict = Depends(require_roles("company_admin"))):
    db = get_db()
    tenant_id = user["tenant_id"]
    packages = await db.packages.find({"tenant_id": tenant_id}, {"_id": 0}).sort("created_at", -1).to_list(2000)
    services = await db.services.find({"tenant_id": tenant_id}, {"_id": 0}).sort("created_at", -1).to_list(2000)

    wb = openpyxl.Workbook()
    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill("solid", fgColor="185FA5")

    def header(ws, cols):
        ws.append(cols)
        for c in ws[1]:
            c.font = header_font
            c.fill = header_fill
            c.alignment = Alignment(horizontal="center")
        for i, _ in enumerate(cols, start=1):
            ws.column_dimensions[openpyxl.utils.get_column_letter(i)].width = 20

    ws_pkg = wb.active
    ws_pkg.title = "Paquetes"
    header(ws_pkg, PKG_COLS)
    for p in packages:
        hotels = p.get("hotels") or [{}]
        for i, hotel in enumerate(hotels):
            occ = hotel.get("prices_by_occupancy", {}) if hotel else {}
            if i == 0:
                ws_pkg.append([
                    p.get("code", ""), p.get("name", ""), p.get("nights", 0), p.get("description", ""),
                    ";".join(p.get("includes", [])), ";".join(p.get("excludes", [])),
                    hotel.get("name", "") if hotel else "",
                    occ.get("sencilla", 0), occ.get("doble", 0), occ.get("triple", 0),
                    occ.get("cuadruple", 0), hotel.get("minor_price", 0) if hotel else 0,
                ])
            else:
                # Continuation row: repeat the code, leave package columns blank, add the extra hotel.
                ws_pkg.append([
                    p.get("code", ""), "", "", "", "", "",
                    hotel.get("name", ""),
                    occ.get("sencilla", 0), occ.get("doble", 0), occ.get("triple", 0),
                    occ.get("cuadruple", 0), hotel.get("minor_price", 0),
                ])

    def svc_sheet(title, category):
        ws = wb.create_sheet(title)
        header(ws, SVC_COLS)
        for s in services:
            if s.get("category") != category:
                continue
            ws.append([s.get("name", ""), s.get("description", ""),
                       s.get("net_price", 0), s.get("public_price", 0), s.get("unit", "per_group")])

    svc_sheet("Tours", "tour")
    svc_sheet("Traslados", "traslado")

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    from datetime import datetime, timezone
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
    return StreamingResponse(
        buf, media_type=XLSX_MIME,
        headers={"Content-Disposition": f'attachment; filename="routiq-catalogo-{stamp}.xlsx"'},
    )


# ---------------------------------------------------------------------------
# Import
# ---------------------------------------------------------------------------
@router.post("/catalog/import")
async def import_catalog(file: UploadFile = File(...), user: dict = Depends(require_roles("company_admin"))):
    name = (file.filename or "").lower()
    if not name.endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="Sube un archivo .xlsx (usa la plantilla descargable).")
    content = await file.read()
    if len(content) > 5 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Archivo muy grande (máx 5 MB).")
    try:
        wb = openpyxl.load_workbook(io.BytesIO(content), data_only=True, read_only=True)
    except Exception:
        raise HTTPException(status_code=400, detail="No se pudo leer el Excel. ¿Está corrupto o no es .xlsx?")

    db = get_db()
    tenant_id = user["tenant_id"]
    company = await db.companies.find_one({"id": tenant_id}, {"_id": 0, "pricing_config": 1})
    divisor = float((company or {}).get("pricing_config", {}).get("margin_divisor") or 0.76) or 0.76

    errors: list[dict] = []
    imported = {"paquetes": 0, "tours": 0, "traslados": 0}

    # --- Paquetes (grouped by code; one row per hotel) ---
    if "Paquetes" in wb.sheetnames:
        ws = wb["Paquetes"]
        # 1) Group rows into packages. Rows sharing a 'code' (or with a blank
        #    'code' that continues the previous package) become one package with
        #    multiple hotels. Package-level fields come from the first row.
        groups: dict[str, dict] = {}
        order: list[str] = []
        current_code: str | None = None
        for idx, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
            if not row or all(c is None or str(c).strip() == "" for c in row):
                continue
            d = dict(zip(PKG_COLS, list(row) + [None] * len(PKG_COLS)))
            code = str(d.get("code") or "").strip()
            if not code:
                # Continuation row -> belongs to the previous package.
                if not current_code:
                    errors.append({"sheet": "Paquetes", "row": idx,
                                   "message": "falta 'code' y no hay un paquete previo al que pertenezca esta fila"})
                    continue
                code = current_code
            else:
                current_code = code
            grp = groups.get(code)
            if grp is None:
                grp = {"code": code, "base": d, "first_row": idx, "hotel_rows": []}
                groups[code] = grp
                order.append(code)
            # Collect the hotel defined on this row (if any).
            if str(d.get("hotel_name") or "").strip():
                grp["hotel_rows"].append((idx, d))

        # 2) Validate and insert one package per group.
        for code in order:
            grp = groups[code]
            d = grp["base"]
            first_row = grp["first_row"]
            try:
                pname = str(d.get("name") or "").strip()
                if not pname:
                    raise ValueError("name es obligatorio (en la primera fila del paquete)")
                nights = int(_coerce_num(d.get("nights"), 0))
                if nights <= 0:
                    raise ValueError("nights debe ser un entero > 0 (en la primera fila del paquete)")
                if await db.packages.find_one({"tenant_id": tenant_id, "code": code}, {"_id": 1}):
                    raise ValueError(f"el código '{code}' ya existe")
                hotels = []
                for (hidx, hd) in grp["hotel_rows"]:
                    try:
                        hotels.append({
                            "name": str(hd["hotel_name"]).strip(), "category": "",
                            "prices_by_occupancy": {
                                "sencilla": _coerce_num(hd["sencilla"]), "doble": _coerce_num(hd["doble"]),
                                "triple": _coerce_num(hd["triple"]), "cuadruple": _coerce_num(hd["cuadruple"]),
                            },
                            "minor_price": _coerce_num(hd["menor"]), "season_prices": {},
                        })
                    except Exception as he:
                        errors.append({"sheet": "Paquetes", "row": hidx,
                                       "message": f"hotel '{hd.get('hotel_name')}': {he}"})
                doc = {
                    "id": new_id(), "tenant_id": tenant_id, "created_at": now_iso(),
                    "code": code, "name": pname, "nights": nights,
                    "description": str(d.get("description") or ""),
                    "image_url": "", "itinerary": [], "hotels": hotels, "seasons": [],
                    "includes": _split_list(d.get("includes")), "excludes": _split_list(d.get("excludes")),
                    "allowed_start_days": [], "special_departure_dates": [], "status": "active",
                }
                await db.packages.insert_one(dict(doc))
                imported["paquetes"] += 1
            except Exception as e:
                errors.append({"sheet": "Paquetes", "row": first_row, "message": str(e)})

    # --- Tours / Traslados (services) ---
    for sheet, category in (("Tours", "tour"), ("Traslados", "traslado")):
        if sheet not in wb.sheetnames:
            continue
        ws = wb[sheet]
        for idx, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
            if not row or all(c is None or str(c).strip() == "" for c in row):
                continue
            d = dict(zip(SVC_COLS, list(row) + [None] * len(SVC_COLS)))
            try:
                sname = str(d["name"] or "").strip()
                if not sname:
                    raise ValueError("name es obligatorio")
                net = _coerce_num(d["net_price"])
                pub = _coerce_num(d["public_price"])
                if pub <= 0:
                    pub = round(net / divisor, 2) if net else 0.0
                unit = str(d.get("unit") or "per_group").strip()
                if unit not in UNITS:
                    unit = "per_group"
                doc = {
                    "id": new_id(), "tenant_id": tenant_id, "created_at": now_iso(),
                    "name": sname, "category": category,
                    "description": str(d.get("description") or ""),
                    "net_price": net, "public_price": pub, "unit": unit,
                    "per_person": unit == "per_person", "status": "active",
                }
                await db.services.insert_one(dict(doc))
                imported["tours" if category == "tour" else "traslados"] += 1
            except Exception as e:
                errors.append({"sheet": sheet, "row": idx, "message": str(e)})

    wb.close()
    total = sum(imported.values())
    return {"ok": True, "imported": imported, "total_imported": total, "errors": errors, "error_count": len(errors)}
