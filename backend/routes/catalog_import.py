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

PKG_EXAMPLE = ["PKG-001", "Tequila Express 2N", 2, "Tour a Tequila con cata",
               "Hospedaje;Desayunos;Tour", "Vuelos;Propinas",
               "Hotel Solar de las Ánimas", 3500, 2400, 2100, 1900, 1500]
TOUR_EXAMPLE = ["City Tour Guadalajara", "Recorrido por el centro histórico", 600, 0, "per_person"]
TRASLADO_EXAMPLE = ["Traslado Aeropuerto-Hotel", "Sedán privado hasta 4 pax", 800, 0, "per_group"]


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

    def build(ws, cols, example):
        ws.append(cols)
        for c in ws[1]:
            c.font = header_font
            c.fill = header_fill
            c.alignment = Alignment(horizontal="center")
        ws.append(example)
        for i, _ in enumerate(cols, start=1):
            ws.column_dimensions[openpyxl.utils.get_column_letter(i)].width = 20

    ws1 = wb.active
    ws1.title = "Paquetes"
    build(ws1, PKG_COLS, PKG_EXAMPLE)
    build(wb.create_sheet("Tours"), SVC_COLS, TOUR_EXAMPLE)
    build(wb.create_sheet("Traslados"), SVC_COLS, TRASLADO_EXAMPLE)

    # Instructions sheet
    info = wb.create_sheet("Instrucciones")
    info.append(["Cómo usar esta plantilla"])
    info["A1"].font = Font(bold=True, size=14)
    for line in [
        "",
        "1. Llena cada hoja: Paquetes, Tours y Traslados.",
        "2. NO borres la fila de encabezados (fila 1). La fila 2 es un ejemplo: puedes reemplazarla o borrarla.",
        "Paquetes — columnas obligatorias: code, name, nights.",
        "   includes/excludes: separa cada elemento con punto y coma (;).",
        "   sencilla/doble/triple/cuadruple/menor: precios por ocupación (numéricos).",
        "Tours/Traslados — columna obligatoria: name.",
        "   net_price = costo; public_price = precio de venta (déjalo en 0 para autocalcular con tu margen).",
        "   unit: per_person, per_group, per_day o per_access.",
        "3. Guarda el archivo y súbelo desde el panel: Catálogo → Importar Excel.",
    ]:
        info.append([line])
    info.column_dimensions["A"].width = 90

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return StreamingResponse(
        buf, media_type=XLSX_MIME,
        headers={"Content-Disposition": 'attachment; filename="routiq-catalogo-template.xlsx"'},
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

    # --- Paquetes ---
    if "Paquetes" in wb.sheetnames:
        ws = wb["Paquetes"]
        for idx, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
            if not row or all(c is None or str(c).strip() == "" for c in row):
                continue
            d = dict(zip(PKG_COLS, list(row) + [None] * len(PKG_COLS)))
            try:
                code = str(d["code"] or "").strip()
                pname = str(d["name"] or "").strip()
                if not code or not pname:
                    raise ValueError("code y name son obligatorios")
                nights = int(_coerce_num(d["nights"], 0))
                if nights <= 0:
                    raise ValueError("nights debe ser un entero > 0")
                if await db.packages.find_one({"tenant_id": tenant_id, "code": code}, {"_id": 1}):
                    raise ValueError(f"el código '{code}' ya existe")
                hotels = []
                if str(d.get("hotel_name") or "").strip():
                    hotels.append({
                        "name": str(d["hotel_name"]).strip(), "category": "",
                        "prices_by_occupancy": {
                            "sencilla": _coerce_num(d["sencilla"]), "doble": _coerce_num(d["doble"]),
                            "triple": _coerce_num(d["triple"]), "cuadruple": _coerce_num(d["cuadruple"]),
                        },
                        "minor_price": _coerce_num(d["menor"]), "season_prices": {},
                    })
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
                errors.append({"sheet": "Paquetes", "row": idx, "message": str(e)})

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
