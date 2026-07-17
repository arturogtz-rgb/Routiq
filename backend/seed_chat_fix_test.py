import os
from datetime import datetime, timezone, timedelta
from pymongo import MongoClient

url = os.environ["MONGO_URL"]
dbname = os.environ["DB_NAME"]
db = MongoClient(url)[dbname]

NUM = "975c561c-b0ee-45f6-b59e-de2653d46f6f"
company = db.companies.find_one({"whatsapp_numbers.id": NUM})
tenant = company["id"]
chat = "5213339990000@s.whatsapp.net"

db.whatsapp_messages.delete_many({"chat_id": chat, "number_id": NUM})
base = datetime.now(timezone.utc)
docs = [
    {"id": "t1", "message_id": "m1", "tenant_id": tenant, "number_id": NUM, "chat_id": chat,
     "from_me": False, "text": "Hola, me interesa", "contact_name": "Juan Test",
     "timestamp": (base - timedelta(minutes=10)).isoformat(), "created_at": (base - timedelta(minutes=10)).isoformat(), "read": True},
    {"id": "t2", "message_id": "m2", "tenant_id": tenant, "number_id": NUM, "chat_id": chat,
     "from_me": True, "text": "Con gusto, te comparto info", "contact_name": "",
     "timestamp": base.isoformat(), "created_at": base.isoformat(), "read": True},
]
db.whatsapp_messages.insert_many(docs)
print("seeded tenant=", tenant, "chat=", chat, "(inbound named, latest outbound empty)")
