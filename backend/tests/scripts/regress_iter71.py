"""Iter71 regression: existing quotations detail/public/pdf open; no-TC mayorista PDF MXN only."""
import io, json, requests
from pypdf import PdfReader
API = open('/app/frontend/.env').read().split('REACT_APP_BACKEND_URL=')[1].split()[0] + '/api'
s = requests.Session(); s.post(f"{API}/auth/login", json={"email": "admin@aventurate.mx", "password": "Demo2026!"})
d = json.load(open('/tmp/it71ui.json'))
lst = s.get(f"{API}/quotations", params={"limit": 40}).json()
items = lst.get("items", lst) if isinstance(lst, dict) else lst
bad = 0
for q in items[:40]:
    r = s.get(f"{API}/quotations/{q['id']}")
    ok = r.status_code == 200
    if ok and q.get("public_token"):
        ok = requests.get(f"{API}/public/quotations/{q['public_token']}").status_code == 200
    if not ok:
        bad += 1; print("FAIL", q.get("code"), r.status_code)
print("checked", len(items[:40]), "bad", bad)
# no-TC mayorista new quotation PDF
cl = d["notc"]["client"]
q = s.post(f"{API}/quotations", json={"type": "personalizado", "client_id": cl, "custom_title": "TEST71UI pdfnotc", "dates": {"start": "2026-11-04", "end": "2026-11-09"},
                                     "pax": {"adultos": 2, "menores": 0, "rooms": []}, "custom_items": [{"category": "extra", "name": "Cena", "price_type": "publico", "unit": "per_group", "net_price": 3000, "qty": 1}], "show_per_person": True}).json()
pdf = s.get(f"{API}/quotations/{q['id']}/pdf")
txt = " ".join(" ".join(p.extract_text() for p in PdfReader(io.BytesIO(pdf.content)).pages).split())
print("notc pdf", pdf.status_code, "US$" in txt, "Montos en dólares" in txt, "(detalle en MXN)" in txt)
s.delete(f"{API}/quotations/{q['id']}")
# mayorista pdf text sample
pdf = s.get(f"{API}/quotations/{d['notc']['q']}/pdf")
txt = " ".join(" ".join(p.extract_text() for p in PdfReader(io.BytesIO(pdf.content)).pages).split())
i = txt.find("US$"); print("may pdf snippet:", txt[max(0, i - 200): i + 600])
