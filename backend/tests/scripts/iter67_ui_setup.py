"""Iter67 UI setup/restore: `python iter67_ui_setup.py setup|restore` (pricing 0.80 + TEST_ clients)."""
import json, sys, requests
API = open('/app/frontend/.env').read().split('REACT_APP_BACKEND_URL=')[1].split()[0] + '/api'
F = '/tmp/iter67_ui_state.json'
s = requests.Session()
s.post(f"{API}/auth/login", json={"email": "admin@aventurate.mx", "password": "Demo2026!"}).raise_for_status()
if sys.argv[1] == 'setup':
    orig = s.get(f"{API}/companies/me").json()["pricing_config"]
    new = {**orig, "margin_divisor": 0.80, "commissions": {"directo": 0.0, "agencia": 0.10, "mayorista": 0.15, "operador": 0.15}}
    print(s.patch(f"{API}/companies/me", json={"pricing_config": new}).status_code)
    cl = {ch: s.post(f"{API}/clients", json={"name": f"TEST_UI67_{ch}", "channel": ch}).json() for ch in ("directo", "agencia")}
    json.dump({"orig": orig, "clients": {k: v["id"] for k, v in cl.items()}}, open(F, 'w'))
    print(json.load(open(F))["clients"])
else:
    st = json.load(open(F))
    for qid in [q["id"] for q in s.get(f"{API}/quotations").json() if isinstance(q, dict) and str(q.get("custom_title", "")).startswith("TEST_UI67")]:
        print("del q", s.delete(f"{API}/quotations/{qid}").status_code)
    for cid in st["clients"].values():
        print("del c", s.delete(f"{API}/clients/{cid}").status_code)
    print("restore", s.patch(f"{API}/companies/me", json={"pricing_config": st["orig"]}).status_code)
    pc = s.get(f"{API}/companies/me").json()["pricing_config"]
    print(pc["margin_divisor"], pc["commissions"])
