"""Iter 68 — búsqueda del listado de cotizaciones (solo lectura, no toca cálculos).

- `trip_start(q)`: inicio del viaje (paquete: fecha de llegada; a la carta / personalizado:
  dates.start o, si falta, la primera fecha del programa / primer check-in).
- `matches(doc, text)`: texto libre sin mayúsculas ni acentos sobre código, cliente, paquete,
  cliente final, ejecutivo de la agencia y agente que elaboró, más fechas de viaje
  ("nov", "11/2026", "04/Nov", "04/11/2026").
"""
import re
import unicodedata

_FULL = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
         "septiembre", "octubre", "noviembre", "diciembre"]


def norm(s) -> str:
    s = unicodedata.normalize("NFD", str(s or ""))
    return "".join(c for c in s if unicodedata.category(c) != "Mn").lower().strip()


def _iso(d) -> str:
    d = str(d or "")[:10]
    return d if re.match(r"^\d{4}-\d{2}-\d{2}$", d) else ""


def trip_start(q: dict) -> str:
    start = _iso((q.get("dates") or {}).get("start"))
    if start:
        return start
    cands = []
    for it in (q.get("custom_items") or []) + (q.get("items") or []):
        cands += [_iso(it.get("checkin")), _iso(it.get("service_date"))]
    for s in (q.get("services") or []):
        cands.append(_iso(s.get("service_date") or s.get("date")))
    cands = sorted(c for c in cands if c)
    return cands[0] if cands else ""


def _month_idx(tok: str):
    if len(tok) < 3 or tok.isdigit():
        return None
    for i, full in enumerate(_FULL):
        if full.startswith(tok):
            return i + 1
    return None


def _year(tok: str):
    if not tok.isdigit():
        return None
    return int(tok) if len(tok) == 4 else (2000 + int(tok) if len(tok) == 2 else None)


def _date_match(text: str, iso: str) -> bool:
    """¿El texto es un patrón de fecha que coincide con `iso` (YYYY-MM-DD)?
    Acepta: "nov", "noviembre", "04/nov", "nov/2026", "04/nov/26", "11/2026", "04/11", "04/11/2026"."""
    if not iso:
        return False
    y, m, d = int(iso[:4]), int(iso[5:7]), int(iso[8:10])
    p = [x for x in re.split(r"[/\-\s.]+", text) if x]
    if not p or len(p) > 3 or not all(x.isdigit() or _month_idx(x) for x in p):
        return False
    names = [i for i, x in enumerate(p) if not x.isdigit()]
    if len(names) > 1:
        return False
    if names:
        k = names[0]
        if _month_idx(p[k]) != m:
            return False
        if len(p) == 1:
            return True
        if len(p) == 2:
            other = p[1 - k]
            return (k == 1 and other.isdigit() and int(other) == d and len(other) <= 2) or \
                   (k == 0 and _year(other) == y)
        return k == 1 and p[0].isdigit() and int(p[0]) == d and _year(p[2]) == y
    if len(p) == 2:
        if len(p[1]) == 4:
            return int(p[0]) == m and int(p[1]) == y
        return int(p[0]) == d and int(p[1]) == m
    if len(p) == 3:
        return int(p[0]) == d and int(p[1]) == m and _year(p[2]) == y
    return False


def haystack(doc: dict) -> str:
    fields = [doc.get("code"), (doc.get("client_snapshot") or {}).get("name"),
              (doc.get("package_snapshot") or {}).get("name"), doc.get("custom_title"),
              ((doc.get("contacts") or {}).get("agency") or {}).get("name"),
              ((doc.get("contacts") or {}).get("agency") or {}).get("contact"),
              doc.get("executive_name"), doc.get("agent_name"), *(doc.get("final_client_names") or [])]
    return " | ".join(norm(f) for f in fields if f)


def matches(doc: dict, text: str) -> bool:
    t = norm(text)
    if not t:
        return True
    if t in doc.get("_hay", ""):
        return True
    return _date_match(t, doc.get("trip_start", ""))
