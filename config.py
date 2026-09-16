import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("❌ BOT_TOKEN topilmadi!")

_admin_id_raw = os.getenv("ADMIN_ID")
if not _admin_id_raw or not _admin_id_raw.isdigit():
    raise RuntimeError("❌ ADMIN_ID noto'g'ri!")

ADMIN_ID = int(_admin_id_raw)

_raw = (os.getenv("WEBAPP_URL") or "https://wtaxi-production.up.railway.app").strip().rstrip("/")
if _raw.endswith("/app"):
    _raw = _raw[:-4].strip().rstrip("/")
WEBAPP_URL = _raw
