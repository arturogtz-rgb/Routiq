"""Iter 69 E2E helper: setup/teardown TEST quotation + invalid Stripe key on demo tenant.
Usage: python it69_e2e_setup.py setup|teardown|state"""
import json
import sys
import uuid
from datetime import datetime, timezone, timedelta

from dotenv import load_dotenv
import os
load_dotenv("/app/backend/.env")
from pymongo import MongoClient

db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
STATE = "/tmp/it69_state.json"


def setup():
    user = db.users.find_one({"email": "admin@aventurate.mx"})
    tid = user["tenant_id"]
    comp = db.companies.find_one({"id": tid})
    orig_stripe = comp.get("stripe")
    src = db.quotations.find_one({"tenant_id": tid, "type": "servicios"}) or db.quotations.find_one({"tenant_id": tid})
    src.pop("_id")
    qid, token = str(uuid.uuid4()), f"TESTit69{uuid.uuid4().hex[:10]}"
    exp = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()
    src.update({"id": qid, "code": "TEST-IT69", "total": 1000.0, "final_total": 1000.0, "amount_paid": 0,
                "payment_status": "unpaid", "state": "enviada", "credited_sessions": [], "checkout_lock_at": None,
                "public_link": {"token": token, "expires_at": exp, "created_at": exp, "accepted_at": None}})
    for k in ("discount",):
        src.pop(k, None)
    db.quotations.insert_one(src)
    db.companies.update_one({"id": tid}, {"$set": {"stripe.secret_key": "rk_test_invalid000"}})
    json.dump({"tid": tid, "qid": qid, "token": token, "orig_stripe": orig_stripe}, open(STATE, "w"), default=str)
    print(json.dumps({"tid": tid, "qid": qid, "token": token, "orig_stripe": orig_stripe}, default=str))


def teardown():
    s = json.load(open(STATE))
    orig = s.get("orig_stripe")
    if orig and orig.get("secret_key"):
        db.companies.update_one({"id": s["tid"]}, {"$set": {"stripe.secret_key": orig["secret_key"]}})
    else:
        db.companies.update_one({"id": s["tid"]}, {"$unset": {"stripe.secret_key": ""}})
    c = db.companies.find_one({"id": s["tid"]}, {"_id": 0, "stripe": 1})
    print("company stripe now:", c.get("stripe"))
    print("txns deleted:", db.payment_transactions.delete_many({"quotation_id": s["qid"]}).deleted_count)
    print("quot deleted:", db.quotations.delete_many({"id": s["qid"]}).deleted_count)
    db.quotation_history.delete_many({"quotation_id": s["qid"]}) if "quotation_history" in db.list_collection_names() else None


def state():
    s = json.load(open(STATE))
    print(db.quotations.find_one({"id": s["qid"]}, {"_id": 0, "amount_paid": 1, "payment_status": 1, "state": 1, "payment_enabled": 1, "credited_sessions": 1}))
    for t in db.payment_transactions.find({"quotation_id": s["qid"]}, {"_id": 0}):
        print(t)


if __name__ == "__main__":
    {"setup": setup, "teardown": teardown, "state": state}[sys.argv[1]]()
