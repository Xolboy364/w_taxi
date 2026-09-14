import ast

def patch(path, replacements, label):
    with open(path, 'r', encoding='utf-8') as f:
        content = f.read()
    for old, new in replacements:
        if old not in content:
            print(f"⚠️  {label}: bo'lak topilmadi — qo'lda tekshiring")
            continue
        if content.count(old) > 1:
            print(f"⚠️  {label}: bir nechta moslik topildi — qo'lda tekshiring")
            continue
        content = content.replace(old, new, 1)
    try:
        ast.parse(content)
    except SyntaxError as e:
        print(f"❌ {label}: yangi kod sintaksisi noto'g'ri, FAYL YOZILMADI. Xato: {e}")
        return
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f"✅ {label}")

# ---------------- database.py ----------------
patch('database.py', [(
'''async def _ensure_service_tables():
    async with pool.acquire() as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS service_ads (
                id SERIAL PRIMARY KEY,
                user_id BIGINT,
                service_type TEXT,
                fuel_types TEXT,
                name TEXT,
                latitude DOUBLE PRECISION,
                longitude DOUBLE PRECISION,
                phone TEXT,
                description TEXT,
                photo_id TEXT,
                is_active INT DEFAULT 0,
                expires_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("ALTER TABLE service_ads ADD COLUMN IF NOT EXISTS fuel_types TEXT;")
        await db.execute("""
            CREATE TABLE IF NOT EXISTS service_payments (''',
'''async def _ensure_service_tables():
    async with pool.acquire() as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS service_ads (
                id SERIAL PRIMARY KEY,
                user_id BIGINT,
                service_type TEXT,
                fuel_types TEXT,
                name TEXT,
                latitude DOUBLE PRECISION,
                longitude DOUBLE PRECISION,
                phone TEXT,
                description TEXT,
                photo_id TEXT,
                is_active INT DEFAULT 0,
                status TEXT DEFAULT 'pending',
                expires_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("ALTER TABLE service_ads ADD COLUMN IF NOT EXISTS fuel_types TEXT;")
        await db.execute("ALTER TABLE service_ads ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'pending';")
        await db.execute("ALTER TABLE roadside_services ADD COLUMN IF NOT EXISTS fuel_types TEXT;")
        await db.execute("""
            CREATE TABLE IF NOT EXISTS service_payments ('''
), (
'''        row = await db.fetchrow("""
            INSERT INTO service_ads
            (user_id, service_type, fuel_types, name, latitude, longitude, phone, description, photo_id, is_active)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, 0)
            RETURNING id
        """,
            user_id, data.get("service_type"), fuel_str, data.get("name"),
            data.get("latitude"), data.get("longitude"), data.get("phone"),
            data.get("description"), data.get("photo_id")
        )''',
'''        row = await db.fetchrow("""
            INSERT INTO service_ads
            (user_id, service_type, fuel_types, name, latitude, longitude, phone, description, photo_id, is_active, status)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, 0, 'pending')
            RETURNING id
        """,
            user_id, data.get("service_type"), fuel_str, data.get("name"),
            data.get("latitude"), data.get("longitude"), data.get("phone"),
            data.get("description"), data.get("photo_id")
        )'''
), (
'''        expires = datetime.datetime.now() + datetime.timedelta(days=days)
        await db.execute("UPDATE service_ads SET is_active = 1, expires_at = $1 WHERE id = $2", expires, ad_id)
        await db.execute("UPDATE service_payments SET status = 'approved' WHERE ad_id = $1", ad_id)
        return await db.fetchrow("SELECT * FROM service_ads WHERE id = $1", ad_id)''',
'''        expires = datetime.datetime.now() + datetime.timedelta(days=days)
        await db.execute("UPDATE service_ads SET is_active = 1, status = 'approved', expires_at = $1 WHERE id = $2", expires, ad_id)
        await db.execute("UPDATE service_payments SET status = 'approved' WHERE ad_id = $1", ad_id)
        return await db.fetchrow("SELECT * FROM service_ads WHERE id = $1", ad_id)'''
), (
'''        row = await db.fetchrow("SELECT * FROM service_ads WHERE id = $1", ad_id)
        await db.execute("UPDATE service_ads SET is_active = 0 WHERE id = $1", ad_id)
        await db.execute("UPDATE service_payments SET status = 'rejected' WHERE ad_id = $1", ad_id)
        return row''',
'''        row = await db.fetchrow("SELECT * FROM service_ads WHERE id = $1", ad_id)
        await db.execute("UPDATE service_ads SET is_active = 0, status = 'rejected' WHERE id = $1", ad_id)
        await db.execute("UPDATE service_payments SET status = 'rejected' WHERE ad_id = $1", ad_id)
        return row


async def get_pending_service_ads():
    await _ensure_service_tables()
    async with pool.acquire() as db:
        return await db.fetch("SELECT * FROM service_ads WHERE status = 'pending' ORDER BY id DESC LIMIT 30")'''
), (
'''async def get_nearest_services(lat: float, lon: float, service_type: str, limit: int = 10, fuel_type: str = None):
    await _ensure_service_tables()
    async with pool.acquire() as db:
        query = """
            SELECT name, phone, description, latitude, longitude,
            (
                6371 * acos(
                    cos(radians($1)) * cos(radians(latitude)) *
                    cos(radians(longitude) - radians($2)) +
                    sin(radians($1)) * sin(radians(latitude))
                )
            ) AS distance
            FROM roadside_services
            WHERE service_type = $3

            UNION ALL

            SELECT name, phone, description, latitude, longitude,
            (
                6371 * acos(
                    cos(radians($1)) * cos(radians(latitude)) *
                    cos(radians(longitude) - radians($2)) +
                    sin(radians($1)) * sin(radians(latitude))
                )
            ) AS distance
            FROM service_ads
            WHERE service_type = $3
              AND is_active = 1
              AND (expires_at IS NULL OR expires_at > NOW())
              AND ($5::text IS NULL OR fuel_types LIKE '%' || $5 || '%')

            ORDER BY distance ASC
            LIMIT $4
        """
        return await db.fetch(query, lat, lon, service_type, limit, fuel_type)''',
'''async def get_nearest_services(lat: float, lon: float, service_type: str, limit: int = 10, fuel_type: str = None):
    await _ensure_service_tables()
    async with pool.acquire() as db:
        query = """
            SELECT 'seed-' || id AS id, name, phone, description, latitude, longitude, fuel_types,
            (
                6371 * acos(
                    cos(radians($1)) * cos(radians(latitude)) *
                    cos(radians(longitude) - radians($2)) +
                    sin(radians($1)) * sin(radians(latitude))
                )
            ) AS distance
            FROM roadside_services
            WHERE service_type = $3
              AND ($5::text IS NULL OR fuel_types LIKE '%' || $5 || '%')

            UNION ALL

            SELECT 'ad-' || id AS id, name, phone, description, latitude, longitude, fuel_types,
            (
                6371 * acos(
                    cos(radians($1)) * cos(radians(latitude)) *
                    cos(radians(longitude) - radians($2)) +
                    sin(radians($1)) * sin(radians(latitude))
                )
            ) AS distance
            FROM service_ads
            WHERE service_type = $3
              AND is_active = 1
              AND status = 'approved'
              AND (expires_at IS NULL OR expires_at > NOW())
              AND ($5::text IS NULL OR fuel_types LIKE '%' || $5 || '%')

            ORDER BY distance ASC
            LIMIT $4
        """
        return await db.fetch(query, lat, lon, service_type, limit, fuel_type)'''
)], 'database.py')

# ---------------- main.py ----------------
patch('main.py', [(
    "from handlers import router\nimport database as db",
    "from handlers import router\nfrom webapp_api import register_webapp_routes\nimport database as db"
), (
    "async def start_web_server():\n    app = web.Application()\n    app.add_routes([web.get('/', handle_ping), web.get('/ping', handle_ping)])",
    "async def start_web_server(bot: Bot):\n    app = web.Application()\n    app.add_routes([web.get('/', handle_ping), web.get('/ping', handle_ping)])\n    register_webapp_routes(app, bot)"
), (
    "    asyncio.create_task(start_web_server())",
    "    asyncio.create_task(start_web_server(bot))"
)], 'main.py')

# ---------------- config.py ----------------
patch('config.py', [(
    'BOT_TOKEN = os.getenv("BOT_TOKEN")\nADMIN_ID = int(os.getenv("ADMIN_ID", "8053001172"))  # Super Admin ID',
    'BOT_TOKEN = os.getenv("BOT_TOKEN")\nADMIN_ID = int(os.getenv("ADMIN_ID", "8053001172"))  # Super Admin ID\nWEBAPP_URL = os.getenv("WEBAPP_URL", "").rstrip("/")  # masalan: https://sizning-domeningiz.uz'
)], 'config.py')

# ---------------- keyboards.py ----------------
patch('keyboards.py', [(
'''from aiogram.types import (
    ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton
)
from aiogram.utils.keyboard import InlineKeyboardBuilder''',
'''from aiogram.types import (
    ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
)
from aiogram.utils.keyboard import InlineKeyboardBuilder'''
), (
'''def get_main_menu(is_super: bool = False, is_sub: bool = False) -> ReplyKeyboardMarkup:
    keyboard = [
        [KeyboardButton(text="🚗 Haydovchi"), KeyboardButton(text="🙋‍♂️ Yo‘lovchi")],
        [KeyboardButton(text="📦 Pochta berish"), KeyboardButton(text="🚚 Yuk yuborish")],
        [KeyboardButton(text="🗺 Yo‘l bo‘yi xizmatlari")]
    ]
    if is_super:
        keyboard.append([KeyboardButton(text="👑 Super Admin Panel")])
    elif is_sub:
        keyboard.append([KeyboardButton(text="🛠 Admin Panel")])
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)''',
'''def get_main_menu(is_super: bool = False, is_sub: bool = False, webapp_url: str = "") -> ReplyKeyboardMarkup:
    keyboard = [
        [KeyboardButton(text="🚗 Haydovchi"), KeyboardButton(text="🙋‍♂️ Yo‘lovchi")],
        [KeyboardButton(text="📦 Pochta berish"), KeyboardButton(text="🚚 Yuk yuborish")],
        [KeyboardButton(text="🗺 Yo‘l bo‘yi xizmatlari")]
    ]
    if webapp_url:
        keyboard.append([KeyboardButton(text="🌐 Veb-ilova", web_app=WebAppInfo(url=f"{webapp_url}/app"))])
    if is_super:
        keyboard.append([KeyboardButton(text="👑 Super Admin Panel")])
    elif is_sub:
        keyboard.append([KeyboardButton(text="🛠 Admin Panel")])
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)'''
)], 'keyboards.py')

# ---------------- handlers.py ----------------
patch('handlers.py', [(
    "from config import ADMIN_ID",
    "from config import ADMIN_ID, WEBAPP_URL"
), (
    "    return get_main_menu(is_super=is_super, is_sub=is_sub)",
    "    return get_main_menu(is_super=is_super, is_sub=is_sub, webapp_url=WEBAPP_URL)"
)], 'handlers.py')

print("\n🎯 Barcha patchlar tugadi.")
