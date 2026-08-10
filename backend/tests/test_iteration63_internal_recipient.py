"""Iter 63 — Test resolución del destinatario INTERNO (notify_acceptance / notify_payment).
La notificación interna debe ir al EJECUTIVO DE ROUTIQ dueño de la cotización:
`created_by` (fallback `assigned_to`) → users.email; luego company.notify_email;
finalmente company.contact_email. `company.notify_email` NO se usa cuando el
ejecutivo tiene correo. NO confundir con `executive_id` (ejecutivo de la agencia
cliente, iter62 — externo).
"""
import os
import sys
import uuid
import asyncio
import pytest

sys.path.insert(0, "/app/backend")

# Asegurar env cargado
from dotenv import load_dotenv
load_dotenv("/app/backend/.env")

import database as _database  # noqa: E402
from database import get_db  # noqa: E402
import notifications as notif_mod  # noqa: E402
from notifications import _recipient  # noqa: E402


# Single shared event loop for motor (motor binds to first loop it sees)
_LOOP = asyncio.new_event_loop()
asyncio.set_event_loop(_LOOP)


def _run(coro):
    return _LOOP.run_until_complete(coro)


# ---------- Fake DB para unit tests puros ----------
class _FakeUsersColl:
    def __init__(self, users_by_id):
        self._users = users_by_id  # {"uid": {"email": "..."} | None}

    async def find_one(self, query, projection=None):
        uid = query.get("id")
        return self._users.get(uid)


class _FakeDB:
    def __init__(self, users_by_id):
        self.users = _FakeUsersColl(users_by_id)


# ---------- UNIT TESTS on _recipient ----------
class TestRecipientUnit:

    def _run(self, coro):
        return asyncio.get_event_loop().run_until_complete(coro) if False else _run(coro)

    def test_a_created_by_with_email_beats_notify_email(self):
        db = _FakeDB({"u1": {"email": "ejec@routiq.com"}})
        company = {"notify_email": "ceo@company.com", "contact_email": "contact@company.com"}
        q = {"created_by": "u1", "assigned_to": None}
        to = _run(_recipient(db, company, q))
        assert to == "ejec@routiq.com", f"expected user email, got {to!r}"
        assert to != "ceo@company.com"

    def test_b_created_by_no_email_falls_back_to_assigned_to(self):
        db = _FakeDB({
            "u1": {"email": ""},           # created_by sin email
            "u2": {"email": "assn@routiq.com"},  # assigned_to con email
        })
        company = {"notify_email": "ceo@company.com", "contact_email": "contact@company.com"}
        q = {"created_by": "u1", "assigned_to": "u2"}
        to = _run(_recipient(db, company, q))
        assert to == "assn@routiq.com", f"expected assigned_to email, got {to!r}"

    def test_b2_created_by_missing_user_falls_back_to_assigned_to(self):
        db = _FakeDB({
            "u1": None,  # user not found
            "u2": {"email": "assn@routiq.com"},
        })
        company = {"notify_email": "ceo@company.com"}
        q = {"created_by": "u1", "assigned_to": "u2"}
        to = _run(_recipient(db, company, q))
        assert to == "assn@routiq.com"

    def test_c_no_executives_falls_back_to_notify_email(self):
        db = _FakeDB({})
        company = {"notify_email": "ceo@company.com", "contact_email": "contact@company.com"}
        q = {"created_by": None, "assigned_to": None}
        to = _run(_recipient(db, company, q))
        assert to == "ceo@company.com"

    def test_c2_executives_without_email_falls_back_to_notify_email(self):
        db = _FakeDB({"u1": {"email": ""}, "u2": {"email": ""}})
        company = {"notify_email": "ceo@company.com", "contact_email": "contact@company.com"}
        q = {"created_by": "u1", "assigned_to": "u2"}
        to = _run(_recipient(db, company, q))
        assert to == "ceo@company.com"

    def test_d_no_notify_email_falls_back_to_contact_email(self):
        db = _FakeDB({})
        company = {"contact_email": "contact@company.com"}
        q = {}
        to = _run(_recipient(db, company, q))
        assert to == "contact@company.com"

    def test_d2_no_recipient_at_all(self):
        db = _FakeDB({})
        company = {}
        q = {}
        to = _run(_recipient(db, company, q))
        assert to == ""

    def test_critical_notify_email_ignored_when_created_by_has_email(self):
        """Bug de raíz: el buzón general no debe recibir cuando hay ejecutivo con correo."""
        db = _FakeDB({"u1": {"email": "vendedor@routiq.com"}})
        company = {"notify_email": "buzon_saturado_ceo@company.com"}
        q = {"created_by": "u1"}
        to = _run(_recipient(db, company, q))
        assert to != "buzon_saturado_ceo@company.com"
        assert to == "vendedor@routiq.com"


# ---------- E2E-ish integration test capturing send_email("to") ----------
class TestNotifyEndToEnd:
    """Crea usuario+cotización en Mongo real, monkeypatch send_email en el módulo notifications,
    invoca notify_acceptance/notify_payment y valida el destinatario resuelto."""

    @pytest.fixture
    def captured_email(self, monkeypatch):
        captured = {"calls": []}

        async def fake_send_email(company, to_email, subject, html, attachments=None):
            captured["calls"].append({"to": to_email, "subject": subject})
            return True

        monkeypatch.setattr(notif_mod, "send_email", fake_send_email)
        return captured

    @pytest.fixture
    def seed(self):
        """Crea un tenant/company + user (created_by) + user (assigned_to) + quotation en Mongo."""
        db = get_db()
        tenant_id = f"TEST_tenant_{uuid.uuid4().hex[:8]}"
        creator_id = f"TEST_creator_{uuid.uuid4().hex[:8]}"
        assignee_id = f"TEST_assignee_{uuid.uuid4().hex[:8]}"
        q_id = f"TEST_q_{uuid.uuid4().hex[:8]}"
        creator_email = f"TEST_creator_{uuid.uuid4().hex[:6]}@routiq.test"
        assignee_email = f"TEST_assignee_{uuid.uuid4().hex[:6]}@routiq.test"

        async def _setup():
            await db.companies.insert_one({
                "id": tenant_id,
                "name": "TEST Company",
                "slug": tenant_id,
                "notify_email": "TEST_ceo_saturado@company.test",
                "contact_email": "TEST_contact@company.test",
            })
            await db.users.insert_one({
                "id": creator_id, "email": creator_email, "tenant_id": tenant_id,
            })
            await db.users.insert_one({
                "id": assignee_id, "email": assignee_email, "tenant_id": tenant_id,
            })
            await db.quotations.insert_one({
                "id": q_id, "tenant_id": tenant_id,
                "code": "TEST-Q-001",
                "created_by": creator_id,
                "assigned_to": assignee_id,
                "final_total": 1000.0, "total": 1000.0, "currency": "MXN",
                "client_snapshot": {"name": "TEST Cliente"},
                "package_snapshot": {"name": "TEST Paquete"},
            })

        _run(_setup())
        yield {
            "tenant_id": tenant_id, "q_id": q_id,
            "creator_id": creator_id, "assignee_id": assignee_id,
            "creator_email": creator_email, "assignee_email": assignee_email,
            "notify_email": "TEST_ceo_saturado@company.test",
            "contact_email": "TEST_contact@company.test",
        }

        async def _cleanup():
            await db.companies.delete_one({"id": tenant_id})
            await db.users.delete_many({"id": {"$in": [creator_id, assignee_id]}})
            await db.quotations.delete_one({"id": q_id})
            await db.notifications.delete_many({"tenant_id": tenant_id})
            await db.push_subscriptions.delete_many({"tenant_id": tenant_id})

        _run(_cleanup())

    def _get_q(self, q_id):
        db = get_db()

        async def _fetch():
            return await db.quotations.find_one({"id": q_id}, {"_id": 0})
        return _run(_fetch())

    def _update_q(self, q_id, updates):
        db = get_db()

        async def _upd():
            await db.quotations.update_one({"id": q_id}, {"$set": updates})
        _run(_upd())

    def _update_user(self, uid, updates):
        db = get_db()

        async def _upd():
            await db.users.update_one({"id": uid}, {"$set": updates})
        _run(_upd())

    def test_acceptance_goes_to_created_by(self, seed, captured_email):
        db = get_db()
        q = self._get_q(seed["q_id"])
        _run(notif_mod.notify_acceptance(db, q))
        assert captured_email["calls"], "send_email no fue llamado"
        to = captured_email["calls"][-1]["to"]
        assert to == seed["creator_email"], f"expected creator, got {to!r}"
        assert to != seed["notify_email"], "❌ fue al buzón general"

    def test_payment_goes_to_created_by(self, seed, captured_email):
        db = get_db()
        q = self._get_q(seed["q_id"])
        txn = {"amount": 500.0, "currency": "MXN"}
        _run(notif_mod.notify_payment(db, q, txn, 500.0, "partial"))
        assert captured_email["calls"]
        to = captured_email["calls"][-1]["to"]
        assert to == seed["creator_email"]
        assert to != seed["notify_email"]

    def test_falls_back_to_assigned_to_when_creator_has_no_email(self, seed, captured_email):
        db = get_db()
        # Quitar email del creator
        self._update_user(seed["creator_id"], {"email": ""})
        q = self._get_q(seed["q_id"])
        _run(notif_mod.notify_acceptance(db, q))
        to = captured_email["calls"][-1]["to"]
        assert to == seed["assignee_email"]
        assert to != seed["notify_email"]

    def test_falls_back_to_notify_email_when_no_exec_has_email(self, seed, captured_email):
        db = get_db()

        async def _unset_emails():
            await db.users.delete_many(
                {"id": {"$in": [seed["creator_id"], seed["assignee_id"]]}},
            )
        _run(_unset_emails())
        q = self._get_q(seed["q_id"])
        _run(notif_mod.notify_acceptance(db, q))
        to = captured_email["calls"][-1]["to"]
        assert to == seed["notify_email"]

    def test_falls_back_to_contact_email_when_no_notify(self, seed, captured_email):
        db = get_db()
        # Sin created_by/assigned_to y sin notify_email
        self._update_q(seed["q_id"], {"created_by": None, "assigned_to": None})

        async def _rm():
            await db.companies.update_one({"id": seed["tenant_id"]},
                                          {"$unset": {"notify_email": ""}})
        _run(_rm())
        q = self._get_q(seed["q_id"])
        _run(notif_mod.notify_acceptance(db, q))
        to = captured_email["calls"][-1]["to"]
        assert to == seed["contact_email"]


# ---------- Regresión: iter62 independiente ----------
class TestRegressionIter62Independent:
    """Confirma que _recipient (interno) y _resolve_client_email (externo)
    son funciones separadas y no se confundieron."""

    def test_functions_are_distinct(self):
        from deps import _resolve_client_email
        assert _recipient is not _resolve_client_email
        # Firma distinta: _recipient es async y toma (db, company, q); _resolve_client_email
        # es sync y toma (client, quotation).
        assert asyncio.iscoroutinefunction(_recipient)
        assert not asyncio.iscoroutinefunction(_resolve_client_email)

    def test_resolve_client_email_still_uses_executive_id(self):
        """Iter62 regresión: el follow-up externo sigue usando executive_id de la agencia."""
        from deps import _resolve_client_email
        client = {"channel": "agencia", "email": "ceo@agencia.com",
                  "executives": [{"id": "e1", "email": "exec@agencia.com"}]}
        q = {"executive_id": "e1"}
        email, err = _resolve_client_email(client, q)
        assert email == "exec@agencia.com" and err == ""

    def test_recipient_does_not_use_executive_id(self):
        """_recipient (interno) NO debe leer executive_id — ese es de la agencia cliente."""
        db = _FakeDB({})  # no users
        company = {"notify_email": "ceo@company.com"}
        # Cotización con executive_id (agencia) pero sin created_by/assigned_to
        q = {"executive_id": "agencia_exec_1"}
        to = _run(_recipient(db, company, q))
        # Debe caer a notify_email, no intentar resolver executive_id
        assert to == "ceo@company.com"
