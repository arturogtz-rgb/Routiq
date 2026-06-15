"""Audit log + audit mini-dashboard metrics (company_admin)."""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends

from database import get_db
from auth import require_roles

router = APIRouter()


@router.get("/audit-log")
async def get_audit_log(action: str | None = None, user: dict = Depends(require_roles("company_admin"))):
    db = get_db()
    q = {"tenant_id": user["tenant_id"]}
    if action:
        q["action"] = action
    return await db.audit_log.find(q, {"_id": 0}).sort("at", -1).to_list(500)


@router.get("/metrics/audit")
async def get_audit_metrics(user: dict = Depends(require_roles("company_admin"))):
    """Mini-dashboard: won this month, amount recovered, top executive."""
    db = get_db()
    tid = user["tenant_id"]
    now = datetime.now(timezone.utc)
    month_prefix = now.strftime("%Y-%m")
    quotations = await db.quotations.find(
        {"tenant_id": tid, "deleted": {"$ne": True}}, {"_id": 0}).to_list(2000)
    won = [q for q in quotations if q.get("state") == "ganada"]
    won_month = [q for q in won if (q.get("last_activity_at", "") or "").startswith(month_prefix)]
    amount_recovered = round(sum(float(q.get("amount_paid", 0) or 0) for q in quotations), 2)
    # top executive by won count
    counts: dict = {}
    for q in won:
        counts[q.get("assigned_to")] = counts.get(q.get("assigned_to"), 0) + 1
    top_id, top_count = (None, 0)
    if counts:
        top_id, top_count = max(counts.items(), key=lambda kv: kv[1])
    top_name = ""
    if top_id:
        u = await db.users.find_one({"id": top_id}, {"_id": 0, "name": 1})
        top_name = (u or {}).get("name", "")
    currency_code = (await db.companies.find_one({"id": tid}, {"_id": 0, "base_currency": 1}) or {}).get("base_currency", "MXN")
    return {
        "won_this_month": len(won_month),
        "won_total": len(won),
        "amount_recovered": amount_recovered,
        "currency": currency_code,
        "top_executive": {"name": top_name, "won": top_count} if top_name else None,
    }
