"""MongoDB connection, indexes, and seed logic."""
from __future__ import annotations
import os
import uuid
from datetime import datetime, timezone
from motor.motor_asyncio import AsyncIOMotorClient
from slugify import slugify

from auth import hash_password

_client: AsyncIOMotorClient | None = None
_db = None


def get_db():
    global _client, _db
    if _db is None:
        _client = AsyncIOMotorClient(os.environ["MONGO_URL"])
        _db = _client[os.environ["DB_NAME"]]
    return _db


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id() -> str:
    return str(uuid.uuid4())


async def ensure_indexes():
    db = get_db()
    await db.users.create_index("email", unique=True)
    await db.users.create_index([("tenant_id", 1), ("role", 1)])
    await db.companies.create_index("slug", unique=True)
    await db.packages.create_index([("tenant_id", 1), ("code", 1)], unique=True)
    await db.tours.create_index([("tenant_id", 1)])
    await db.transfers.create_index([("tenant_id", 1)])
    await db.services.create_index([("tenant_id", 1)])
    await db.payment_transactions.create_index("session_id", unique=True)
    await db.payment_transactions.create_index([("tenant_id", 1)])
    await db.notifications.create_index([("tenant_id", 1), ("read", 1)])
    await db.push_subscriptions.create_index("endpoint", unique=True)
    await db.push_subscriptions.create_index([("tenant_id", 1)])
    await db.clients.create_index([("tenant_id", 1)])
    await db.quotations.create_index([("tenant_id", 1), ("state", 1)])
    await db.quotations.create_index([("tenant_id", 1), ("code", 1)], unique=True)
    # Public signup funnel: index requests by status + TTL purge of rate-limit attempts (>24h)
    await db.tenant_requests.create_index([("status", 1), ("created_at", -1)])
    await db.signup_attempts.create_index("at", expireAfterSeconds=86400)
    await db.signup_attempts.create_index([("ip", 1), ("at", -1)])
    # WhatsApp (Baileys) inbound/outbound messages
    await db.whatsapp_messages.create_index([("tenant_id", 1), ("number_id", 1), ("chat_id", 1), ("timestamp", 1)])
    await db.whatsapp_messages.create_index([("tenant_id", 1), ("number_id", 1), ("message_id", 1)], unique=True)
    await db.whatsapp_links.create_index([("tenant_id", 1), ("number_id", 1), ("chat_id", 1)])
    await db.whatsapp_links.create_index([("tenant_id", 1), ("quotation_id", 1)])
    # Migration: legacy logo URLs (without /api prefix) → /api/uploads/...
    async for c in db.companies.find({"logo_url": {"$regex": "^/uploads/"}}, {"_id": 0, "id": 1, "logo_url": 1}):
        await db.companies.update_one(
            {"id": c["id"]},
            {"$set": {"logo_url": "/api" + c["logo_url"]}},
        )
    # Migration: swap quotation dates if start > end
    async for q in db.quotations.find({}, {"_id": 0, "id": 1, "dates": 1}):
        d = q.get("dates") or {}
        s, e = d.get("start"), d.get("end")
        if s and e and s > e:
            await db.quotations.update_one(
                {"id": q["id"]},
                {"$set": {"dates": {"start": e, "end": s}}},
            )


DEFAULT_PRICING_CONFIG = {
    "margin_divisor": 0.76,   # Costo / 0.76 = Publico  (margen 24%)
    "commissions": {"directo": 0.0, "agencia": 0.10, "mayorista": 0.15, "operador": 0.20},
    "minor_age_min": 3,
    "minor_age_max": 11,
    "minor_discount": 0.40,   # 40% off adult rate for menores
    "currency": "MXN",
}


async def ensure_app_config():
    """Generate and persist VAPID keys once (for Web Push)."""
    db = get_db()
    import push
    cfg = await db.app_config.find_one({"id": "vapid"})
    if not cfg:
        keys = push.generate_vapid_keys()
        await db.app_config.insert_one({"id": "vapid", **keys})


async def ensure_site_settings():
    """Create the singleton site_settings doc (Landing/Login editable content)."""
    db = get_db()
    doc = await db.site_settings.find_one({"id": "default"})
    if not doc:
        await db.site_settings.insert_one({"id": "default", "draft": {}, "published": {}})


async def seed_super_admin():
    db = get_db()
    email = os.environ["SUPER_ADMIN_EMAIL"].lower().strip()
    password = os.environ["SUPER_ADMIN_PASSWORD"]
    existing = await db.users.find_one({"email": email})
    if existing is None:
        await db.users.insert_one({
            "id": new_id(),
            "email": email,
            "password_hash": hash_password(password),
            "name": "Routiq Owner",
            "role": "super_admin",
            "tenant_id": None,
            "status": "active",
            "created_at": now_iso(),
        })


async def seed_demo_tenant():
    """Seed 'Aventúrate por Jalisco' demo tenant with sample data."""
    db = get_db()
    slug = "aventurate"
    company = await db.companies.find_one({"slug": slug}, {"_id": 0})
    if company is None:
        company = {
            "id": new_id(),
            "name": "Aventúrate por Jalisco",
            "slug": slug,
            "logo_url": "",
            "primary_color": "#185FA5",
            "contact_email": "contacto@aventurateporjalisco.com",
            "contact_phone": "+52 33 0000 0000",
            "address": "Guadalajara, Jalisco, México",
            "pricing_config": DEFAULT_PRICING_CONFIG.copy(),
            "whatsapp_numbers": [
                {"id": new_id(), "number": "+52 33 1111 1111", "label": "Ventas GDL", "status": "disconnected"}
            ],
            "status": "active",
            "created_at": now_iso(),
        }
        await db.companies.insert_one(dict(company))

    tenant_id = company["id"]

    # Seed company admin
    admin_email = os.environ["DEMO_COMPANY_ADMIN_EMAIL"].lower().strip()
    if await db.users.find_one({"email": admin_email}) is None:
        await db.users.insert_one({
            "id": new_id(),
            "email": admin_email,
            "password_hash": hash_password(os.environ["DEMO_COMPANY_ADMIN_PASSWORD"]),
            "name": "María González",
            "role": "company_admin",
            "tenant_id": tenant_id,
            "status": "active",
            "created_at": now_iso(),
        })
    exec_email = os.environ["DEMO_EXECUTIVE_EMAIL"].lower().strip()
    exec_user = await db.users.find_one({"email": exec_email}, {"_id": 0})
    if exec_user is None:
        exec_id = new_id()
        await db.users.insert_one({
            "id": exec_id,
            "email": exec_email,
            "password_hash": hash_password(os.environ["DEMO_EXECUTIVE_PASSWORD"]),
            "name": "Carlos Hernández",
            "role": "executive",
            "tenant_id": tenant_id,
            "status": "active",
            "created_at": now_iso(),
        })
    else:
        exec_id = exec_user["id"]

    # Seed demo packages
    if await db.packages.count_documents({"tenant_id": tenant_id}) == 0:
        packages = [
            {
                "id": new_id(), "tenant_id": tenant_id,
                "code": "GDL-TEQ-3N",
                "name": "Guadalajara Clásica + Tequila 4 días",
                "nights": 3,
                "description": "Recorrido por el centro histórico de Guadalajara, Tlaquepaque y un día completo en Tequila con cata y comida tradicional.",
                "itinerary": [
                    {"day": 1, "title": "Llegada a Guadalajara", "description": "Recepción en aeropuerto, traslado al hotel y city tour por el centro histórico."},
                    {"day": 2, "title": "Tlaquepaque y Tonalá", "description": "Visita a los pueblos mágicos artesanales con tiempo libre para compras."},
                    {"day": 3, "title": "Ruta del Tequila", "description": "Tour a una fábrica de tequila con cata guiada y campos de agave azul."},
                    {"day": 4, "title": "Traslado de salida", "description": "Desayuno y traslado al aeropuerto."},
                ],
                "hotels": [
                    {"name": "Hotel Riu Plaza Guadalajara", "category": "5*",
                     "prices_by_occupancy": {"sencilla": 12500, "doble": 8900, "triple": 7800, "cuadruple": 7200}, "minor_price": 4500},
                    {"name": "Hotel Demetria", "category": "4*",
                     "prices_by_occupancy": {"sencilla": 9800, "doble": 6900, "triple": 6200, "cuadruple": 5800}, "minor_price": 3800},
                ],
                "includes": ["Hospedaje", "Desayunos diarios", "Traslados aeropuerto", "City tour", "Tour Tequila con cata"],
                "excludes": ["Vuelos", "Propinas", "Gastos personales"],
                "season_start": "2026-01-01", "season_end": "2026-12-15",
                "status": "active", "created_at": now_iso(),
            },
            {
                "id": new_id(), "tenant_id": tenant_id,
                "code": "PV-LUX-5N",
                "name": "Puerto Vallarta Lujo 6 días",
                "nights": 5,
                "description": "Escapada de lujo todo incluido en Puerto Vallarta con tour al Malecón y Islas Marietas.",
                "itinerary": [
                    {"day": 1, "title": "Llegada a PVR", "description": "Recepción y check-in en hotel de lujo todo incluido."},
                    {"day": 2, "title": "Día libre en playa", "description": "Disfruta de todas las amenidades del resort."},
                    {"day": 3, "title": "Islas Marietas", "description": "Tour en yate a las famosas Islas Marietas con snorkel."},
                    {"day": 4, "title": "Malecón y Centro", "description": "Visita al Malecón, Zona Romántica y degustación gastronómica."},
                    {"day": 5, "title": "Día libre", "description": "Actividad opcional (no incluida): avistamiento de ballenas."},
                    {"day": 6, "title": "Traslado de salida", "description": "Desayuno y traslado al aeropuerto."},
                ],
                "hotels": [
                    {"name": "Hyatt Ziva PV", "category": "5* AI",
                     "prices_by_occupancy": {"sencilla": 28500, "doble": 19500, "triple": 17800, "cuadruple": 16500}, "minor_price": 9500},
                ],
                "includes": ["Todo incluido", "Traslados aeropuerto", "Tour Islas Marietas", "Tour Malecón"],
                "excludes": ["Vuelos", "Propinas", "Avistamiento de ballenas"],
                "season_start": "2026-01-01", "season_end": "2026-12-15",
                "status": "active", "created_at": now_iso(),
            },
        ]
        await db.packages.insert_many([p.copy() for p in packages])

    # Seed sample a la carte services
    if await db.services.count_documents({"tenant_id": tenant_id}) == 0:
        await db.services.insert_many([
            {"id": new_id(), "tenant_id": tenant_id, "name": "Tour privado Tequila con cata",
             "category": "tour", "description": "Visita a destilería con cata guiada y transporte privado.",
             "net_price": 1200.0, "public_price": round(1200 / 0.76, 2), "unit": "per_person", "per_person": True,
             "status": "active", "created_at": now_iso()},
            {"id": new_id(), "tenant_id": tenant_id, "name": "Traslado aeropuerto privado",
             "category": "traslado", "description": "Traslado privado aeropuerto–hotel (por trayecto).",
             "net_price": 650.0, "public_price": round(650 / 0.76, 2), "unit": "per_group", "per_person": False,
             "status": "active", "created_at": now_iso()},
            {"id": new_id(), "tenant_id": tenant_id, "name": "Acceso Hospicio Cabañas",
             "category": "acceso", "description": "Entrada al museo Hospicio Cabañas, Patrimonio de la Humanidad.",
             "net_price": 90.0, "public_price": round(90 / 0.76, 2), "unit": "per_access", "per_person": True,
             "status": "active", "created_at": now_iso()},
            {"id": new_id(), "tenant_id": tenant_id, "name": "Guía privado certificado (día completo)",
             "category": "extra", "description": "Guía de turistas certificado por día.",
             "net_price": 2500.0, "public_price": round(2500 / 0.76, 2), "unit": "per_day", "per_person": False,
             "status": "active", "created_at": now_iso()},
        ])

    # Seed sample clients
    if await db.clients.count_documents({"tenant_id": tenant_id}) == 0:
        await db.clients.insert_many([
            {"id": new_id(), "tenant_id": tenant_id, "name": "Laura Ramírez",
             "phone": "+52 55 2233 4455", "email": "laura@example.com",
             "channel": "directo", "notes": "Cliente recurrente", "created_at": now_iso()},
            {"id": new_id(), "tenant_id": tenant_id, "name": "Agencia Viajes del Sol",
             "phone": "+52 33 5566 7788", "email": "ventas@viajesdelsol.mx",
             "channel": "agencia", "notes": "Pide tarifa agencia", "created_at": now_iso()},
        ])

    # Seed sample quotations across kanban states
    if await db.quotations.count_documents({"tenant_id": tenant_id}) == 0:
        clients = await db.clients.find({"tenant_id": tenant_id}, {"_id": 0}).to_list(10)
        packages = await db.packages.find({"tenant_id": tenant_id}, {"_id": 0}).to_list(10)
        if clients and packages:
            states = [
                ("nueva_consulta", 0), ("nueva_consulta", 1),
                ("cotizando", 1),
                ("enviada", 0),
                ("negociacion", 1),
                ("ganada", 0),
            ]
            for idx, (state, pack_i) in enumerate(states):
                pack = packages[pack_i % len(packages)]
                client = clients[idx % len(clients)]
                hotel = pack["hotels"][0]
                pax = {"adultos": 2, "menores": 0, "ocupacion": "doble"}
                precio_hotel = hotel["prices_by_occupancy"]["doble"]
                subtotal = precio_hotel * 2
                comision = 0.0
                if client["channel"] == "agencia":
                    comision = subtotal * 0.10
                await db.quotations.insert_one({
                    "id": new_id(), "tenant_id": tenant_id,
                    "code": f"COT-{2026000 + idx + 1}",
                    "client_id": client["id"], "client_snapshot": {"name": client["name"], "channel": client["channel"]},
                    "type": "paquete", "package_id": pack["id"], "package_snapshot": {"name": pack["name"], "code": pack["code"]},
                    "hotel_selected": hotel["name"],
                    "dates": {"start": "2026-03-15", "end": "2026-03-18"},
                    "pax": pax,
                    "items": [{"label": f"{pack['name']} - {hotel['name']} (doble x2)", "unit_price": precio_hotel, "qty": 2, "subtotal": subtotal}],
                    "subtotal": subtotal, "commission": comision, "total": subtotal - comision,
                    "state": state,
                    "assigned_to": exec_id,
                    "created_by": exec_id,
                    "notes": "",
                    "last_activity_at": now_iso(),
                    "created_at": now_iso(),
                })
