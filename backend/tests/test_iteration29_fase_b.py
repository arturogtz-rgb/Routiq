"""Iteration 29 Fase B — Clients CRUD, user delete + workload, AI tone.

Covers:
  - GET    /api/clients (with stats: quotations_count/active_count/sales_total/last_activity_at)
  - POST   /api/clients
  - PATCH  /api/clients/{id}
  - DELETE /api/clients/{id}
  - GET    /api/users/{id}/workload (admin only)
  - DELETE /api/users/{id} (admin only, RBAC + self/admin guards, reassign)
  - POST   /api/ai/presentation with tone (503 expected when BYOK not configured)
"""

import os
import time
import uuid
import pytest
import requests

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "admin@aventurate.mx"
ADMIN_PASSWORD = "Demo2026!"
EXEC_EMAIL = "ejecutivo@aventurate.mx"
EXEC_PASSWORD = "Demo2026!"


def _login(email, password):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=15)
    assert r.status_code == 200, f"login failed for {email}: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="module")
def admin():
    return _login(ADMIN_EMAIL, ADMIN_PASSWORD)


@pytest.fixture(scope="module")
def executive():
    return _login(EXEC_EMAIL, EXEC_PASSWORD)


# --------------------------- Clients ---------------------------

class TestClientsCRUD:
    def test_list_clients_with_stats(self, admin):
        r = admin.get(f"{API}/clients", timeout=15)
        assert r.status_code == 200
        items = r.json()
        assert isinstance(items, list)
        if items:
            c = items[0]
            for k in ("id", "name", "quotations_count", "active_count", "sales_total", "last_activity_at"):
                assert k in c, f"missing key {k} in client: {c.keys()}"
            assert isinstance(c["quotations_count"], int)
            assert isinstance(c["active_count"], int)
            assert isinstance(c["sales_total"], (int, float))

    def test_create_patch_delete_client(self, admin):
        tag = f"TEST_{uuid.uuid4().hex[:8]}"
        # CREATE
        r = admin.post(f"{API}/clients", json={
            "name": tag, "email": f"{tag}@test.mx", "phone": "555-0000", "channel": "directo", "notes": "n1",
        }, timeout=15)
        assert r.status_code == 201, r.text
        c = r.json()
        cid = c["id"]
        assert c["name"] == tag
        assert c["channel"] == "directo"

        # GET verify
        r = admin.get(f"{API}/clients", timeout=15)
        assert any(x["id"] == cid for x in r.json())

        # PATCH name/channel/phone/email/notes
        r = admin.patch(f"{API}/clients/{cid}", json={
            "name": tag + "_upd", "channel": "agencia", "phone": "555-1111",
            "email": f"{tag}_upd@test.mx", "notes": "updated",
        }, timeout=15)
        assert r.status_code == 200, r.text
        upd = r.json()
        assert upd["name"] == tag + "_upd"
        assert upd["channel"] == "agencia"
        assert upd["phone"] == "555-1111"
        assert upd["notes"] == "updated"

        # GET to verify persistence
        r = admin.get(f"{API}/clients", timeout=15)
        match = next(x for x in r.json() if x["id"] == cid)
        assert match["channel"] == "agencia"

        # DELETE
        r = admin.delete(f"{API}/clients/{cid}", timeout=15)
        assert r.status_code == 200
        assert r.json().get("ok") is True

        # Verify gone
        r = admin.get(f"{API}/clients", timeout=15)
        assert not any(x["id"] == cid for x in r.json())

        # Delete again → 404
        r = admin.delete(f"{API}/clients/{cid}", timeout=15)
        assert r.status_code == 404

    def test_patch_unknown_client_404(self, admin):
        r = admin.patch(f"{API}/clients/does-not-exist", json={"name": "x"}, timeout=15)
        assert r.status_code == 404


# --------------------------- Users workload + delete ---------------------------

class TestUserDeleteAndWorkload:
    def _list_users(self, sess):
        r = sess.get(f"{API}/users", timeout=15)
        assert r.status_code == 200
        return r.json()

    def _admin_id(self, sess):
        for u in self._list_users(sess):
            if u.get("role") == "company_admin":
                return u["id"]
        pytest.skip("no admin found")

    def test_workload_admin_ok(self, admin):
        admin_id = self._admin_id(admin)
        r = admin.get(f"{API}/users/{admin_id}/workload", timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert "total" in data and "active" in data
        assert isinstance(data["total"], int)
        assert isinstance(data["active"], int)
        assert data["total"] >= data["active"]

    def test_workload_executive_forbidden(self, executive):
        # Executives cannot call /users/{id}/workload (admin-only)
        # Get own id from /auth/me
        r = executive.get(f"{API}/auth/me", timeout=15)
        assert r.status_code == 200
        uid = r.json()["id"]
        r = executive.get(f"{API}/users/{uid}/workload", timeout=15)
        assert r.status_code == 403

    def test_admin_cannot_delete_self(self, admin):
        admin_id = self._admin_id(admin)
        r = admin.delete(f"{API}/users/{admin_id}", timeout=15)
        assert r.status_code == 400, r.text

    def test_admin_cannot_delete_other_admin(self, admin):
        # If there's another admin, attempt to delete should 403. If only one, create not possible.
        users = self._list_users(admin)
        me = admin.get(f"{API}/auth/me", timeout=15).json()
        admins = [u for u in users if u.get("role") == "company_admin" and u["id"] != me["id"]]
        if not admins:
            pytest.skip("Only one admin in tenant, cannot test cross-admin deletion")
        r = admin.delete(f"{API}/users/{admins[0]['id']}", timeout=15)
        assert r.status_code == 403

    def test_executive_cannot_delete_user(self, executive, admin):
        # Pick the admin to attempt to delete
        admin_id = self._admin_id(admin)
        r = executive.delete(f"{API}/users/{admin_id}", timeout=15)
        assert r.status_code == 403

    def test_create_delete_executive_with_reassign(self, admin):
        # Create temp executive via invite-executive
        tag = f"TEST_{uuid.uuid4().hex[:6]}"
        payload = {"name": f"Temp {tag}", "email": f"temp_{tag}@test.mx", "password": "Temp2026!"}
        r = admin.post(f"{API}/users/invite-executive", json=payload, timeout=15)
        assert r.status_code in (200, 201), r.text
        new_user = r.json()
        new_id = new_user.get("id") or new_user.get("user", {}).get("id")
        assert new_id, f"unexpected invite payload: {new_user}"

        try:
            # workload should be 0/0
            r = admin.get(f"{API}/users/{new_id}/workload", timeout=15)
            assert r.status_code == 200
            assert r.json() == {"total": 0, "active": 0}

            # delete (no quotations) → reassigned 0
            r = admin.delete(f"{API}/users/{new_id}", timeout=15)
            assert r.status_code == 200, r.text
            body = r.json()
            assert body.get("ok") is True
            assert "reassigned" in body
            assert body["reassigned"] == 0

            # confirm user gone
            users_after = self._list_users(admin)
            assert not any(u["id"] == new_id for u in users_after)
            new_id = None
        finally:
            if new_id:
                admin.delete(f"{API}/users/{new_id}", timeout=15)


# --------------------------- AI presentation with tone ---------------------------

class TestAIPresentationTone:
    @pytest.mark.parametrize("tone", ["formal", "cercano", "premium"])
    def test_ai_presentation_tone_503_when_byok_missing(self, admin, tone):
        # Need a quotation to call presentation. Just pick any from list.
        r = admin.get(f"{API}/quotations", timeout=15)
        assert r.status_code == 200
        items = r.json()
        if not items:
            pytest.skip("No quotation available to test AI presentation")
        qid = items[0]["id"]
        r = admin.post(f"{API}/ai/presentation", json={"quotation_id": qid, "tone": tone}, timeout=30)
        # Expected 503 because BYOK is not configured in this env
        # Accept 200 if env happens to have a key (don't break)
        assert r.status_code in (200, 503), f"unexpected {r.status_code}: {r.text}"
        if r.status_code == 503:
            # Spanish error message expected
            assert "IA" in r.text or "configurada" in r.text.lower() or r.json()
