"""Automated sales summary emails (weekly / monthly).

Each company can enable a recurring email with the period KPIs + the full XLSX
report attached. A lightweight background loop (started in server startup) checks
hourly which tenants are due and sends via their configured email provider
(Resend / SMTP / Gmail) with the always-on platform fallback.
"""
import logging
from datetime import datetime, timezone, timedelta

try:
    from zoneinfo import ZoneInfo
    _TZ = ZoneInfo("America/Mexico_City")
except Exception:  # pragma: no cover
    _TZ = timezone.utc

from database import get_db, now_iso
import notifications
from routes import stats  # sales aggregation + workbook builder

log = logging.getLogger("routiq")

XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _money(v, ccy):
    return f"${float(v or 0):,.0f} {ccy}"


def _kpi_html(company: dict, data: dict, period_label: str) -> str:
    ccy = data["currency"]
    conv = data["conversion"]
    top_exec = data["executives"][0]["name"] if data["executives"] else "—"
    cards = [
        ("Ingresos", _money(data["revenue_total"], ccy)),
        ("Cotizaciones creadas", str(conv["total"])),
        ("Tasa de conversión", f"{conv['rate']}%"),
        ("Ejecutivo top", top_exec),
    ]

    def _cell(label, val):
        return (f"<td style='padding:14px 18px;background:#f8fafc;border-radius:12px;width:50%'>"
                f"<div style='font-size:11px;text-transform:uppercase;letter-spacing:1px;color:#94a3b8;font-weight:700'>{label}</div>"
                f"<div style='font-size:22px;font-weight:700;color:#0f172a;margin-top:4px'>{val}</div></td>")

    row1 = f"<tr>{_cell(*cards[0])}<td style='width:12px'></td>{_cell(*cards[1])}</tr>"
    row2 = f"<tr>{_cell(*cards[2])}<td style='width:12px'></td>{_cell(*cards[3])}</tr>"
    return (
        f"<div style='font-family:system-ui,Arial,sans-serif;max-width:560px'>"
        f"<h2 style='color:#185FA5;margin-bottom:2px'>Resumen de ventas · {period_label}</h2>"
        f"<p style='color:#64748b;margin-top:0'>{company.get('name','')}</p>"
        f"<table style='border-collapse:separate;border-spacing:0 12px;width:100%'>{row1}{row2}</table>"
        f"<p style='color:#475569'>Ganadas: <b>{conv['won']}</b> · Perdidas: <b>{conv['lost']}</b> · "
        f"Cobrado: <b>{_money(data['collected_total'], ccy)}</b></p>"
        f"<p style='color:#64748b;font-size:13px'>Adjuntamos el reporte completo en Excel (ejecutivos, clientes, "
        f"paquetes, servicios y cotizaciones perdidas).</p></div>"
    )


async def send_company_report(db, company: dict, period: str):
    """Build and send the sales report email for one company.
    Returns (ok: bool, to: str, error: str)."""
    if not company:
        return False, "", "Empresa no encontrada"
    tenant_id = company["id"]
    data = await stats._compute(db, tenant_id, period)
    period_label = {"week": "Última semana", "month": "Último mes"}.get(period, period)
    html = _kpi_html(company, data, period_label)
    buf = stats.build_workbook(data)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
    attachments = [{
        "filename": f"routiq-ventas-{period}-{stamp}.xlsx",
        "data": buf.getvalue(),
        "mime": XLSX_MIME,
    }]
    to = company.get("notify_email") or company.get("contact_email") or ""
    if not to:
        return False, "", "La empresa no tiene correo de avisos ni de contacto configurado."
    subject = f"📊 Resumen de ventas ({period_label}) — {company.get('name','Routiq')}"
    ok = await notifications.send_email(company, to, subject, html, attachments)
    if not ok:
        return False, to, "El proveedor de correo rechazó el envío (revisa Resend/SMTP)."
    return True, to, ""


def _is_due(cfg: dict, now_local: datetime, last_sent_iso: str) -> bool:
    freq = cfg.get("frequency", "weekly")
    hour = int(cfg.get("hour", 8) or 0)
    if now_local.hour != hour:
        return False
    if freq == "weekly":
        if now_local.weekday() != int(cfg.get("day", 0) or 0):
            return False
    else:  # monthly
        if now_local.day != int(cfg.get("day", 1) or 1):
            return False
    # de-dupe: avoid re-sending within the same ~day window
    if last_sent_iso:
        try:
            last = datetime.fromisoformat(last_sent_iso)
            if (datetime.now(timezone.utc) - last) < timedelta(hours=23):
                return False
        except Exception:
            pass
    return True


async def run_sales_reports(db=None) -> dict:
    """Check all companies and send due sales reports. Idempotent per day window."""
    db = db or get_db()
    now_local = datetime.now(_TZ)
    companies = await db.companies.find(
        {"sales_report.enabled": True}, {"_id": 0}
    ).to_list(1000)
    sent, checked = 0, 0
    for company in companies:
        cfg = company.get("sales_report") or {}
        checked += 1
        if not _is_due(cfg, now_local, company.get("sales_report_last_sent_at", "")):
            continue
        period = "week" if cfg.get("frequency", "weekly") == "weekly" else "month"
        try:
            ok, to, err = await send_company_report(db, company, period)
            if ok:
                await db.companies.update_one(
                    {"id": company["id"]}, {"$set": {"sales_report_last_sent_at": now_iso()}})
                sent += 1
                log.info("sales report sent to %s (%s)", to, company.get("name"))
            else:
                log.warning("sales report not sent for %s: %s", company.get("name"), err)
        except Exception:
            log.exception("sales report failed for %s", company.get("name"))
    return {"checked": checked, "sent": sent}
