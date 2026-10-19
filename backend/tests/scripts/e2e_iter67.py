"""E2E Iter67: fija pricing 0.80/0.10/0.15/0.15, crea cotizaciones A y B (personalizado y a la carta), valida y restaura."""
import requests
API = open('/app/frontend/.env').read().split('REACT_APP_BACKEND_URL=')[1].split()[0] + '/api'
s = requests.Session()
r = s.post(f"{API}/auth/login", json={"email": "admin@aventurate.mx", "password": "Demo2026!"}); r.raise_for_status()
tok = r.json().get("token") or r.json().get("access_token")
if tok: s.headers["Authorization"] = f"Bearer {tok}"
orig = s.get(f"{API}/companies/me").json()["pricing_config"]
new = {**orig, "margin_divisor": 0.80, "commissions": {"directo": 0.0, "agencia": 0.10, "mayorista": 0.15, "operador": 0.15}}
print("set", s.patch(f"{API}/companies/me", json={"pricing_config": new}).status_code)
clients = {}
for c in s.get(f"{API}/clients").json():
    clients.setdefault(c["channel"], c)
def items(ht, d, c):
    return [{"category": "hospedaje", "name": "Hotel Test", "price_type": ht, "unit": "per_night", "checkin": "2026-11-04", "checkout": "2026-11-09", "nights": 5,
             "occupancy_rows": [{"ocupacion": "doble", "rooms": 1, "price": d}, {"ocupacion": "cuadruple", "rooms": 1, "price": c}]},
            {"category": "traslado", "name": "Vehículo", "price_type": "publico", "unit": "per_vehicle", "net_price": 6000, "qty": 1},
            {"category": "tour", "name": "Tour", "price_type": "publico", "unit": "per_person", "net_price": 450, "qty": 0},
            {"category": "extra", "name": "Cena", "price_type": "publico", "unit": "per_group", "net_price": 3000, "qty": 1}]
try:
    for typ in ("personalizado", "servicios"):
        for case, ch, ht, d, c in (("A", "directo", "publico", 875, 700), ("B", "agencia", "neto", 700, 560)):
            p = {"type": typ, "client_id": clients[ch]["id"], "custom_title": f"TEST_iter67 {case}", "dates": {"start": "2026-11-04", "end": "2026-11-09"},
                 "pax": {"adultos": 6, "menores": 0, "rooms": []}, "custom_items": items(ht, d, c), "services": [], "show_per_person": True,
                 "executive_id": ((clients[ch].get("executives") or [{}])[0].get("id"))}
            r = s.post(f"{API}/quotations", json=p)
            assert r.status_code == 201, r.text
            q = s.get(f"{API}/quotations/{r.json()['id']}").json()
            bd = q["per_person_breakdown"]
            print(typ, case, q["total"], [(x["key"], x["price_per_person"], x["subtotal"]) for x in bd["rows"]], bd["note"])
            s.delete(f"{API}/quotations/{q['id']}")
finally:
    print("restore", s.patch(f"{API}/companies/me", json={"pricing_config": orig}).status_code)
