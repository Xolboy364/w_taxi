import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError(
        "❌ BOT_TOKEN topilmadi! .env fayliga BOT_TOKEN=... qatorini qo'shing."
    )

_admin_id_raw = os.getenv("ADMIN_ID")
if not _admin_id_raw or not _admin_id_raw.isdigit():
    raise RuntimeError(
        "❌ ADMIN_ID topilmadi yoki noto'g'ri! .env fayliga ADMIN_ID=123456789 "
        "(o'zingizning Telegram ID'ingiz) qatorini qo'shing."
    )

ADMIN_ID = int(_admin_id_raw)  # Super Admin ID (endi hardcode emas, faqat .env dan)
