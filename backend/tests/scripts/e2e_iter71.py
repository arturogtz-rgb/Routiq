"""Smoke Iter71: TC 18.50, caso C mayorista internacional."""
import requests, io
API = open('/app/frontend/.env').read().split('REACT_APP_BACKEND_URL=')[1].split()[0] + '/api'
s = requests.Session(); s.post(f"{API}/auth/login", json={"email": "admin@aventurate.mx", "password": "Demo2026!"})
orig = s.get(f"{API}/companies/me").json()["pricing_config"]
cfg = {**orig, "margin_divisor": 0.80, "commissions": {"directo": 0.0, "agencia": 0.10, "mayorista": 0.15, "operador": 0.15}, "fx_mayorista_mxn_per_usd": 18.5}
r = s.patch(f"{API}/companies/me/pricing", json=cfg); print("pricing", r.status_code, r.json()["pricing_config"].get("fx_mayorista_updated_at"))
print("bad fx", s.patch(f"{API}/companies/me/pricing", json={**cfg, "fx_mayorista_mxn_per_usd": 18.12345}).status_code)
cl = s.post(f"{API}/clients", json={"name": "TEST71 Mayorista", "channel": "mayorista"}).json()
items = [{"category": "hospedaje", "name": "Hotel", "price_type": "neto", "unit": "per_night", "checkin": "2026-11-04", "checkout": "2026-11-09", "nights": 5,
          "occupancy_rows": [{"ocupacion": "doble", "rooms": 1, "price": 700}, {"ocupacion": "cuadruple", "rooms": 1, "price": 560}]},
         {"category": "traslado", "name": "Vehículo", "price_type": "publico", "unit": "per_vehicle", "net_price": 6000, "qty": 1},
         {"category": "tour", "name": "Tour", "price_type": "publico", "unit": "per_person", "net_price": 450, "qty": 0},
         {"category": "extra", "name": "Cena", "price_type": "publico", "unit": "per_group", "net_price": 3000, "qty": 1}]
try:
    q = s.post(f"{API}/quotations", json={"type": "personalizado", "client_id": cl["id"], "custom_title": "TEST71 C", "dates": {"start": "2026-11-04", "end": "2026-11-09"},
                                          "pax": {"adultos": 6, "menores": 0, "rooms": []}, "custom_items": items, "show_per_person": True}).json()
    d = s.get(f"{API}/quotations/{q['id']}").json(); u = d["usd_presentation"]
    print("MXN", d["total"], "fx", d.get("fx_rate_mxn_per_usd"), [(r["key"], r["price_per_person_mxn"], r["price_per_person_usd"]) for r in u["rows"]], u["total_usd"], u["direct_total_usd"], u["rounding_diff_usd"])
    s.patch(f"{API}/companies/me/pricing", json={**cfg, "fx_mayorista_mxn_per_usd": 19.0})
    d2 = s.get(f"{API}/quotations/{q['id']}").json(); print("after settings change", d2["usd_presentation"]["rate"], d2["usd_presentation"]["company_rate"])
    print("refresh", s.post(f"{API}/quotations/{q['id']}/fx/refresh").json())
    d3 = s.get(f"{API}/quotations/{q['id']}").json(); print("after refresh", d3["usd_presentation"]["rate"], d3["usd_presentation"]["total_usd"], d3["total"])
    tok = s.post(f"{API}/quotations/{q['id']}/public-link").json()["token"]
    pub = requests.get(f"{API}/public/quotations/{tok}").json()
    print("public usd", pub["quotation"]["usd_presentation"]["total_usd"], "equiv", pub["payment"]["equivalent_amount"])
    pdf = s.get(f"{API}/quotations/{q['id']}/pdf"); print("pdf", pdf.status_code, len(pdf.content))
    open('/tmp/it71.pdf', 'wb').write(pdf.content)
    s.delete(f"{API}/quotations/{q['id']}")
finally:
    s.delete(f"{API}/clients/{cl['id']}")
    print("restore", s.patch(f"{API}/companies/me/pricing", json=orig).status_code)
