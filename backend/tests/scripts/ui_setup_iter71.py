"""Setup/cleanup data for Iter71 UI tests. usage: python ui_setup_iter71.py setup|cleanup"""
import json, sys, requests
API = open('/app/frontend/.env').read().split('REACT_APP_BACKEND_URL=')[1].split()[0] + '/api'
s = requests.Session(); s.post(f"{API}/auth/login", json={"email": "admin@aventurate.mx", "password": "Demo2026!"})
ORIG = {'margin_divisor': 0.75, 'commissions': {'directo': 0.0, 'agencia': 0.12, 'mayorista': 0.15, 'operador': 0.2}, 'minor_age_min': 3, 'minor_age_max': 11, 'minor_discount': 0.4, 'currency': 'MXN', 'fx_mayorista_mxn_per_usd': None}
ITEMS = [{"category": "hospedaje", "name": "Hotel", "price_type": "neto", "unit": "per_night", "checkin": "2026-11-04", "checkout": "2026-11-09", "nights": 5,
          "occupancy_rows": [{"ocupacion": "doble", "rooms": 1, "price": 700}, {"ocupacion": "cuadruple", "rooms": 1, "price": 560}]},
         {"category": "traslado", "name": "Vehículo", "price_type": "publico", "unit": "per_vehicle", "net_price": 6000, "qty": 1},
         {"category": "tour", "name": "Tour", "price_type": "publico", "unit": "per_person", "net_price": 450, "qty": 0},
         {"category": "extra", "name": "Cena", "price_type": "publico", "unit": "per_group", "net_price": 3000, "qty": 1}]
cfg = {**ORIG, "margin_divisor": 0.80, "commissions": {"directo": 0.0, "agencia": 0.10, "mayorista": 0.15, "operador": 0.15}}


def quote(ch, title):
    cl = s.post(f"{API}/clients", json={"name": f"TEST71UI {title}", "channel": ch}).json()
    q = s.post(f"{API}/quotations", json={"type": "personalizado", "client_id": cl["id"], "custom_title": f"TEST71UI {title}", "dates": {"start": "2026-11-04", "end": "2026-11-09"},
                                         "pax": {"adultos": 6, "menores": 0, "rooms": []}, "custom_items": ITEMS, "show_per_person": True}).json()
    s.patch(f"{API}/quotations/{q['id']}/payment-config", json={"payment_enabled": True, "allowed_pay_type": "full", "card_fee_enabled": True, "card_fee_percent": 5.5})
    tok = s.post(f"{API}/quotations/{q['id']}/public-link").json()["token"]
    return {"client": cl["id"], "q": q["id"], "tok": tok}


if sys.argv[1] == "setup":
    s.patch(f"{API}/companies/me/pricing", json={**cfg, "fx_mayorista_mxn_per_usd": None})
    out = {"notc": quote("mayorista", "SinTC")}
    s.patch(f"{API}/companies/me/pricing", json={**cfg, "fx_mayorista_mxn_per_usd": 18.5})
    out["may"] = quote("mayorista", "May")
    out["dir"] = quote("directo", "Dir")
    json.dump(out, open('/tmp/it71ui.json', 'w')); print(out)
elif sys.argv[1] == "notc":
    s.patch(f"{API}/companies/me/pricing", json={**cfg, "fx_mayorista_mxn_per_usd": None}); print("tc cleared")
else:
    for c in s.get(f"{API}/clients", params={"q": "TEST71", "limit": 100}).json().get("items", []) if isinstance(s.get(f"{API}/clients").json(), dict) else s.get(f"{API}/clients").json():
        pass
    out = json.load(open('/tmp/it71ui.json'))
    for v in out.values():
        s.delete(f"{API}/quotations/{v['q']}"); s.delete(f"{API}/clients/{v['client']}")
    print("restore", s.patch(f"{API}/companies/me/pricing", json=ORIG).status_code, s.get(f"{API}/companies/me").json()["pricing_config"])
