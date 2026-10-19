"""Iter 71 — presentación USD del canal Mayorista internacional (solo presentación).

El MXN es la fuente de verdad: no cambia ningún cálculo, cobro ni moneda de Stripe.
  - Precio por persona USD = round(pp MXN ÷ TC, 2) por ocupación.
  - Total USD = Σ (pp USD × personas). Si difiere de total MXN ÷ TC se reporta (`rounding_diff_usd`).
  - Sin desglose por persona: total USD = round(total MXN ÷ TC, 2).
"""
CHANNEL = "mayorista"
LABEL = "Mayorista internacional"
MISSING = "Captura el tipo de cambio en Ajustes"


def fmt_rate(rate: float) -> str:
    return f"{rate:,.2f}" if round(rate, 2) == rate else f"{rate:,.4f}".rstrip("0")


def note(rate: float) -> str:
    return (f"Montos en dólares solo como referencia, al tipo de cambio de ${fmt_rate(rate)} MXN por USD. "
            "El cobro se realiza en pesos mexicanos (MXN) y el tipo de cambio puede variar según su banco.")


def valid_rate(rate) -> float:
    """TC capturado: > 0 y hasta 4 decimales. ValueError si no cumple."""
    r = float(rate)
    if not r > 0:
        raise ValueError("El tipo de cambio debe ser mayor que 0.")
    if abs(round(r, 4) - r) > 1e-9:
        raise ValueError("El tipo de cambio admite hasta 4 decimales.")
    return round(r, 4)


def usd(mxn: float, rate: float) -> float:
    return round(float(mxn or 0) / float(rate), 2)


def company_rate(company: dict):
    pc = (company or {}).get("pricing_config") or {}
    rate = pc.get("fx_mayorista_mxn_per_usd")
    return (float(rate), pc.get("fx_mayorista_updated_at")) if rate else (None, None)


def snapshot_fields(company: dict, channel: str) -> dict:
    """Campos a guardar en una cotización nueva del canal (vacío para otros canales)."""
    if channel != CHANNEL:
        return {}
    rate, date = company_rate(company)
    return {"fx_rate_mxn_per_usd": rate, "fx_rate_date": date} if rate else {}


def is_international(q: dict) -> bool:
    return ((q.get("client_snapshot") or {}).get("channel")) == CHANNEL


def build(q: dict, bd: dict | None) -> dict | None:
    """Presentación USD o None si la cotización no es del canal."""
    if not is_international(q):
        return None
    rate = q.get("fx_rate_mxn_per_usd")
    if not rate:
        return {"available": False, "warning": MISSING}
    rate = float(rate)
    total_mxn = round(float(q.get("final_total") if q.get("final_total") is not None else q.get("total", 0) or 0), 2)
    direct = round(total_mxn / rate, 2)
    out = {"available": True, "rate": rate, "rate_label": fmt_rate(rate), "rate_date": q.get("fx_rate_date"),
           "total_mxn": total_mxn, "note": note(rate), "rows": []}
    if bd and bd.get("rows"):
        for r in bd["rows"]:
            pp_usd = round(r["price_per_person"] / rate, 2)
            out["rows"].append({"key": r["key"], "label": r["label"], "title": r.get("title"), "pax": r["pax"],
                                "price_per_person_usd": pp_usd, "subtotal_usd": round(pp_usd * r["pax"], 2),
                                "price_per_person_mxn": r["price_per_person"], "subtotal_mxn": r["subtotal"]})
        out["total_usd"] = round(sum(x["subtotal_usd"] for x in out["rows"]), 2)
    else:
        out["total_usd"] = direct
    out["direct_total_usd"] = direct
    out["rounding_diff_usd"] = round(out["total_usd"] - direct, 2)
    return out
