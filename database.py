import os
import asyncpg
import datetime

from security import hash_password, verify_password

pool = None


async def init_db():
    global pool
    database_url = os.getenv("DATABASE_URL")

    pool = await asyncpg.create_pool(
        dsn=database_url,
        min_size=5,
        max_size=30,
        command_timeout=60
    )

    async with pool.acquire() as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS system_settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                telegram_id BIGINT PRIMARY KEY,
                full_name TEXT,
                phone TEXT,
                is_banned INT DEFAULT 0,
                ban_until TIMESTAMP,
                ban_reason TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS drivers (
                telegram_id BIGINT PRIMARY KEY,
                full_name TEXT,
                phone TEXT,
                service_type TEXT,
                car_model TEXT,
                car_number TEXT,
                photo_id TEXT,
                status TEXT DEFAULT 'waiting',
                subscription_until TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_active INT DEFAULT 1
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS driver_routes (
                id SERIAL PRIMARY KEY,
                telegram_id BIGINT,
                from_loc TEXT,
                to_loc TEXT,
                route_category TEXT DEFAULT 'intercity',
                seats INT DEFAULT 4,
                accepts_post INT DEFAULT 1,
                FOREIGN KEY(telegram_id) REFERENCES drivers(telegram_id)
            )
        """)
        # Dublikat marshrutlarning oldini olish uchun unikal indeks
        await db.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_driver_routes_unique
            ON driver_routes(telegram_id, from_loc, to_loc)
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS passenger_orders (
                id SERIAL PRIMARY KEY,
                user_id BIGINT,
                full_name TEXT,
                phone TEXT,
                from_loc TEXT,
                to_loc TEXT,
                seats_needed INT DEFAULT 1,
                target_driver_id BIGINT DEFAULT 0,
                service_type TEXT DEFAULT 'passenger',
                is_active INT DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("ALTER TABLE passenger_orders ADD COLUMN IF NOT EXISTS service_type TEXT DEFAULT 'passenger';")

        await db.execute("""
            CREATE TABLE IF NOT EXISTS roadside_services (
                id SERIAL PRIMARY KEY,
                service_type TEXT,
                name TEXT,
                latitude DOUBLE PRECISION,
                longitude DOUBLE PRECISION,
                phone TEXT,
                description TEXT,
                fuel_types TEXT
            )
        """)
        await db.execute("ALTER TABLE roadside_services ADD COLUMN IF NOT EXISTS fuel_types TEXT;")

        await db.execute("""
            CREATE TABLE IF NOT EXISTS activity_logs (
                id SERIAL PRIMARY KEY,
                telegram_id BIGINT,
                user_name TEXT,
                action_type TEXT,
                details TEXT,
                is_temp_admin INT DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS admins (
                telegram_id BIGINT PRIMARY KEY,
                full_name TEXT,
                added_by BIGINT,
                receive_backups INT DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Haydovchi to'lov cheklari (obuna) - atomik tasdiqlash uchun alohida jadval
        await db.execute("""
            CREATE TABLE IF NOT EXISTS driver_payments (
                id SERIAL PRIMARY KEY,
                user_id BIGINT,
                photo_id TEXT,
                status TEXT DEFAULT 'pending',
                reject_reason TEXT,
                reminded INT DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("ALTER TABLE driver_payments ADD COLUMN IF NOT EXISTS reject_reason TEXT;")
        await db.execute("ALTER TABLE driver_payments ADD COLUMN IF NOT EXISTS reminded INT DEFAULT 0;")

        # Shikoyatlar (haydovchiga nisbatan)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS complaints (
                id SERIAL PRIMARY KEY,
                from_user_id BIGINT,
                target_driver_id BIGINT,
                text TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Xizmat e'lonlari va ularning to'lovlari (service_ad.py uchun)
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
            CREATE TABLE IF NOT EXISTS service_payments (
                id SERIAL PRIMARY KEY,
                ad_id INT,
                user_id BIGINT,
                amount INT,
                photo_id TEXT,
                status TEXT DEFAULT 'pending',
                reject_reason TEXT,
                reminded INT DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("ALTER TABLE service_payments ADD COLUMN IF NOT EXISTS reject_reason TEXT;")
        await db.execute("ALTER TABLE service_payments ADD COLUMN IF NOT EXISTS reminded INT DEFAULT 0;")
        await db.execute("ALTER TABLE service_ads ADD COLUMN IF NOT EXISTS last_expiry_reminder TIMESTAMP;")

        # Obuna tugashi haqida bir martalik eslatma yuborilganini kuzatish uchun
        await db.execute("ALTER TABLE drivers ADD COLUMN IF NOT EXISTS last_expiry_reminder TIMESTAMP;")

        # Super admin paroli endi HASH holida saqlanadi (plaintext emas)
        default_hash = hash_password("admin777")
        await db.execute(
            "INSERT INTO system_settings (key, value) VALUES ('super_admin_password', $1) ON CONFLICT (key) DO NOTHING",
            default_hash
        )
        await db.execute("INSERT INTO system_settings (key, value) VALUES ('maintenance_mode', '0') ON CONFLICT (key) DO NOTHING")
        await db.execute("INSERT INTO system_settings (key, value) VALUES ('monetization_active', '0') ON CONFLICT (key) DO NOTHING")
        await db.execute("INSERT INTO system_settings (key, value) VALUES ('p2p_card_number', '8600123456789012') ON CONFLICT (key) DO NOTHING")

        await db.execute("CREATE INDEX IF NOT EXISTS idx_routes_lookup ON driver_routes(from_loc, to_loc);")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_orders_time ON passenger_orders(created_at);")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_logs_time ON activity_logs(created_at);")


async def close_db():
    global pool
    if pool:
        await pool.close()


# ---------------- Super admin parol funksiyalari (endi xavfsiz) ----------------

async def verify_super_admin_password(password: str) -> bool:
    async with pool.acquire() as db:
        row = await db.fetchrow("SELECT value FROM system_settings WHERE key = 'super_admin_password'")
        if not row:
            return False
        return verify_password(password, row["value"])


async def set_super_admin_password(new_password: str):
    hashed = hash_password(new_password)
    async with pool.acquire() as db:
        await db.execute("""
            INSERT INTO system_settings (key, value) VALUES ('super_admin_password', $1)
            ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
        """, hashed)


# ---------------- Obuna / haydovchi funksiyalari ----------------

GRACE_PERIOD_HOURS = 24  # obuna tugagach 1 kunlik imtiyoz muddati (haydovchi to'satdan yo'qolib qolmasin)
FREE_DRIVER_ROUTE_LIMIT = 5  # monetizatsiya yoqilganda, to'lamagan haydovchi uchun maksimal marshrut soni


async def is_driver_subscribed(telegram_id: int) -> bool:
    monetization = await get_setting("monetization_active", "0")
    if monetization != "1":
        return True

    async with pool.acquire() as db:
        row = await db.fetchrow("SELECT subscription_until FROM drivers WHERE telegram_id = $1", telegram_id)
        if not row or not row["subscription_until"]:
            return False
        try:
            sub_end = row["subscription_until"]
            if isinstance(sub_end, str):
                sub_end = datetime.datetime.fromisoformat(sub_end)
            grace_end = sub_end + datetime.timedelta(hours=GRACE_PERIOD_HOURS)
            return datetime.datetime.now() < grace_end
        except Exception:
            return False


async def get_drivers_expiring_soon(days_before: int = 3):
    """
    Obunasi 'days_before' kundan keyin (yoki undan kamroq vaqtda) tugaydigan,
    hali eslatma yuborilmagan haydovchilarni qaytaradi.
    """
    async with pool.acquire() as db:
        return await db.fetch("""
            SELECT telegram_id, subscription_until FROM drivers
            WHERE subscription_until IS NOT NULL
              AND subscription_until <= NOW() + ($1 || ' days')::interval
              AND subscription_until > NOW()
              AND (last_expiry_reminder IS NULL OR last_expiry_reminder < NOW() - INTERVAL '4 days')
        """, str(days_before))


async def mark_expiry_reminded(telegram_id: int):
    async with pool.acquire() as db:
        await db.execute("UPDATE drivers SET last_expiry_reminder = NOW() WHERE telegram_id = $1", telegram_id)


async def grant_grace_days_to_all_drivers(days: int = 7):
    """Monetizatsiya yangi yoqilganda barcha haydovchilarga bepul muddat beradi."""
    driver_ids = await get_all_driver_ids()
    for did in driver_ids:
        await extend_driver_subscription(did, days=days)
    return driver_ids


async def can_add_more_routes(telegram_id: int, additional_count: int) -> tuple[bool, int]:
    """
    Monetizatsiya yoqilgan va haydovchi obunachi bo'lmasa, marshrut soni
    FREE_DRIVER_ROUTE_LIMIT bilan cheklanadi. To'lagan haydovchilar uchun cheklov yo'q.
    Qaytaradi: (ruxsat_bormi, limit_qancha [0 - cheksiz]).
    """
    monetization = await get_setting("monetization_active", "0")
    if monetization != "1":
        return True, 0

    is_sub = await is_driver_subscribed(telegram_id)
    if is_sub:
        return True, 0

    current_count = await get_driver_routes_count(telegram_id)
    if current_count + additional_count > FREE_DRIVER_ROUTE_LIMIT:
        return False, FREE_DRIVER_ROUTE_LIMIT
    return True, FREE_DRIVER_ROUTE_LIMIT


async def extend_driver_subscription(telegram_id: int, days: int = 30):
    async with pool.acquire() as db:
        row = await db.fetchrow("SELECT subscription_until FROM drivers WHERE telegram_id = $1", telegram_id)
        current_end = datetime.datetime.now()
        if row and row["subscription_until"]:
            try:
                existing_end = row["subscription_until"]
                if isinstance(existing_end, str):
                    existing_end = datetime.datetime.fromisoformat(existing_end)
                if existing_end > current_end:
                    current_end = existing_end
            except Exception:
                pass

        new_end = current_end + datetime.timedelta(days=days)
        await db.execute("UPDATE drivers SET subscription_until = $1 WHERE telegram_id = $2", new_end, telegram_id)


async def get_setting(key: str, default: str = "") -> str:
    async with pool.acquire() as db:
        row = await db.fetchrow("SELECT value FROM system_settings WHERE key = $1", key)
        return row["value"] if row else default


async def set_setting(key: str, value: str):
    async with pool.acquire() as db:
        await db.execute("""
            INSERT INTO system_settings (key, value) VALUES ($1, $2)
            ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
        """, key, value)


async def log_activity(telegram_id: int, user_name: str, action_type: str, details: str = "", is_temp_admin: int = 0):
    async with pool.acquire() as db:
        await db.execute("""
            INSERT INTO activity_logs (telegram_id, user_name, action_type, details, is_temp_admin)
            VALUES ($1, $2, $3, $4, $5)
        """, telegram_id, user_name, action_type, details, is_temp_admin)


async def get_recent_admin_logs(limit: int = 20):
    async with pool.acquire() as db:
        query = """
            SELECT * FROM activity_logs
            WHERE is_temp_admin = 1 OR action_type LIKE 'ADMIN_%' OR action_type IN ('BAN_USER', 'UNBAN_USER', 'KILL_SWITCH', 'START_SWITCH', 'ADD_ADMIN', 'REMOVE_ADMIN', 'MONETIZATION_TOGGLE', 'APPROVE_PAYMENT')
            ORDER BY id DESC LIMIT $1
        """
        return await db.fetch(query, limit)


async def is_user_banned(telegram_id: int) -> tuple[bool, str]:
    async with pool.acquire() as db:
        row = await db.fetchrow("SELECT is_banned, ban_until, ban_reason FROM users WHERE telegram_id = $1", telegram_id)
        if not row or not row["is_banned"]:
            return False, ""

        if row["ban_until"]:
            try:
                ban_end = row["ban_until"]
                if isinstance(ban_end, str):
                    ban_end = datetime.datetime.fromisoformat(ban_end)
                if datetime.datetime.now() > ban_end:
                    await db.execute("UPDATE users SET is_banned = 0, ban_until = NULL, ban_reason = NULL WHERE telegram_id = $1", telegram_id)
                    return False, ""
            except Exception:
                pass
        return True, row["ban_reason"] or "Qoidalarni buzganlik uchun"


async def ban_user(telegram_id: int, reason: str, duration_hours: int = None):
    ban_until = None
    if duration_hours:
        ban_until = datetime.datetime.now() + datetime.timedelta(hours=duration_hours)
    async with pool.acquire() as db:
        await db.execute("""
            UPDATE users
            SET is_banned = 1, ban_until = $1, ban_reason = $2
            WHERE telegram_id = $3
        """, ban_until, reason, telegram_id)


async def unban_user(telegram_id: int):
    async with pool.acquire() as db:
        await db.execute("""
            UPDATE users
            SET is_banned = 0, ban_until = NULL, ban_reason = NULL
            WHERE telegram_id = $1
        """, telegram_id)


async def get_all_user_ids() -> list:
    async with pool.acquire() as db:
        rows = await db.fetch("SELECT telegram_id FROM users UNION SELECT telegram_id FROM drivers")
        return [r["telegram_id"] for r in rows]


async def get_all_driver_ids() -> list:
    async with pool.acquire() as db:
        rows = await db.fetch("SELECT telegram_id FROM drivers WHERE is_active = 1")
        return [r["telegram_id"] for r in rows]


async def get_user_phone(telegram_id: int):
    async with pool.acquire() as db:
        row = await db.fetchrow("SELECT phone FROM users WHERE telegram_id = $1", telegram_id)
        return row["phone"] if row else None


async def save_user_phone(telegram_id: int, full_name: str, phone: str):
    async with pool.acquire() as db:
        await db.execute("""
            INSERT INTO users (telegram_id, full_name, phone)
            VALUES ($1, $2, $3)
            ON CONFLICT(telegram_id) DO UPDATE SET full_name = EXCLUDED.full_name, phone = EXCLUDED.phone
        """, telegram_id, full_name, phone)


async def is_admin(telegram_id: int, super_admin_id: int) -> bool:
    if telegram_id == super_admin_id:
        return True
    async with pool.acquire() as db:
        row = await db.fetchrow("SELECT 1 FROM admins WHERE telegram_id = $1", telegram_id)
        return bool(row)


async def add_admin(telegram_id: int, full_name: str, added_by: int):
    async with pool.acquire() as db:
        await db.execute("""
            INSERT INTO admins (telegram_id, full_name, added_by, receive_backups)
            VALUES ($1, $2, $3, 1)
            ON CONFLICT (telegram_id) DO UPDATE SET full_name = EXCLUDED.full_name, added_by = EXCLUDED.added_by
        """, telegram_id, full_name, added_by)


async def remove_admin(telegram_id: int):
    async with pool.acquire() as db:
        await db.execute("DELETE FROM admins WHERE telegram_id = $1", telegram_id)


async def get_all_admins():
    async with pool.acquire() as db:
        return await db.fetch("SELECT * FROM admins ORDER BY created_at DESC")


async def get_backup_recipients(super_admin_id: int) -> list:
    async with pool.acquire() as db:
        rows = await db.fetch("SELECT telegram_id FROM admins WHERE receive_backups = 1")
        recipients = {super_admin_id}
        for r in rows:
            recipients.add(r["telegram_id"])
        return list(recipients)


async def get_driver(telegram_id: int):
    async with pool.acquire() as db:
        return await db.fetchrow("SELECT * FROM drivers WHERE telegram_id = $1", telegram_id)


async def save_driver(data: dict):
    async with pool.acquire() as db:
        await db.execute("""
            INSERT INTO drivers
            (telegram_id, full_name, phone, service_type, car_model, car_number, photo_id, status, is_active)
            VALUES ($1, $2, $3, $4, $5, $6, $7, 'waiting', 1)
            ON CONFLICT (telegram_id) DO UPDATE SET
                full_name = EXCLUDED.full_name, phone = EXCLUDED.phone,
                service_type = EXCLUDED.service_type, car_model = EXCLUDED.car_model,
                car_number = EXCLUDED.car_number, photo_id = EXCLUDED.photo_id,
                status = 'waiting', updated_at = CURRENT_TIMESTAMP
        """,
            data["telegram_id"], data["full_name"], data["phone"],
            data["service_type"], data["car_model"], data["car_number"], data["photo_id"]
        )


async def set_driver_status(telegram_id: int, status: str):
    async with pool.acquire() as db:
        await db.execute("UPDATE drivers SET status = $1, updated_at = CURRENT_TIMESTAMP WHERE telegram_id = $2", status, telegram_id)


async def clear_driver_routes(telegram_id: int):
    async with pool.acquire() as db:
        await db.execute("DELETE FROM driver_routes WHERE telegram_id = $1", telegram_id)


async def add_driver_multi_routes(telegram_id: int, from_list: list, to_list: list, route_category: str = 'intercity'):
    async with pool.acquire() as db:
        for f in from_list:
            for t in to_list:
                # ON CONFLICT DO NOTHING - bir xil marshrut ikki marta yozilmaydi
                await db.execute("""
                    INSERT INTO driver_routes (telegram_id, from_loc, to_loc, route_category, seats, accepts_post)
                    VALUES ($1, $2, $3, $4, 4, 1)
                    ON CONFLICT (telegram_id, from_loc, to_loc) DO NOTHING
                """, telegram_id, f, t, route_category)
        await db.execute("UPDATE drivers SET status = 'waiting', updated_at = CURRENT_TIMESTAMP WHERE telegram_id = $1", telegram_id)


async def add_driver_single_route(telegram_id: int, from_loc: str, to_loc: str, route_category: str = 'local'):
    async with pool.acquire() as db:
        await db.execute("""
            INSERT INTO driver_routes (telegram_id, from_loc, to_loc, route_category, seats, accepts_post)
            VALUES ($1, $2, $3, $4, 4, 1)
            ON CONFLICT (telegram_id, from_loc, to_loc) DO NOTHING
        """, telegram_id, from_loc, to_loc, route_category)
        await db.execute("UPDATE drivers SET status = 'waiting', updated_at = CURRENT_TIMESTAMP WHERE telegram_id = $1", telegram_id)


async def get_driver_routes_count(telegram_id: int):
    async with pool.acquire() as db:
        row = await db.fetchrow("SELECT COUNT(*) FROM driver_routes WHERE telegram_id = $1", telegram_id)
        return row[0] if row else 0


async def search_drivers(from_loc: str, to_loc: str):
    async with pool.acquire() as db:
        query = """
            SELECT DISTINCT d.telegram_id, d.full_name, d.phone, d.car_model, d.car_number, d.photo_id, d.status, r.seats, r.accepts_post
            FROM driver_routes r
            JOIN drivers d ON r.telegram_id = d.telegram_id
            WHERE r.from_loc = $1 AND r.to_loc = $2 AND d.is_active = 1 AND d.status = 'waiting'
        """
        return await db.fetch(query, from_loc, to_loc)


async def count_recent_orders(user_id: int, minutes: int = 60) -> int:
    """Foydalanuvchi so'nggi N daqiqada nechta buyurtma bergani (spam nazorati uchun)."""
    async with pool.acquire() as db:
        row = await db.fetchrow("""
            SELECT COUNT(*) FROM passenger_orders
            WHERE user_id = $1 AND created_at >= NOW() - ($2 || ' minutes')::interval
        """, user_id, str(minutes))
        return row[0] if row else 0


async def add_passenger_order(user_id: int, full_name: str, phone: str, from_loc: str, to_loc: str, seats: int = 1, target_driver_id: int = 0, service_type: str = 'passenger'):
    async with pool.acquire() as db:
        # Bitta foydalanuvchida bir vaqtda faqat 1 ta faol buyurtma bo'lishi uchun,
        # yangisini qo'shishdan oldin eskilarini avtomatik yopamiz.
        await db.execute("UPDATE passenger_orders SET is_active = 0 WHERE user_id = $1 AND is_active = 1", user_id)

        row = await db.fetchrow("""
            INSERT INTO passenger_orders (user_id, full_name, phone, from_loc, to_loc, seats_needed, target_driver_id, service_type, is_active)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, 1)
            RETURNING id
        """, user_id, full_name, phone, from_loc, to_loc, seats, target_driver_id, service_type)
        return row["id"] if row else None


async def get_passenger_order_owner(order_id: int):
    async with pool.acquire() as db:
        row = await db.fetchrow("SELECT user_id FROM passenger_orders WHERE id = $1", order_id)
        return row["user_id"] if row else None


async def close_passenger_order(order_id: int, requester_id: int = None, is_admin: bool = False) -> bool:
    """
    E'lonni yopadi. Agar requester_id berilgan bo'lsa va admin bo'lmasa,
    faqat e'lon egasi yopa oladi (begona odam yopa olmaydi).
    Muvaffaqiyatli yopilsa True, aks holda False qaytaradi.
    """
    async with pool.acquire() as db:
        if requester_id is not None and not is_admin:
            result = await db.execute(
                "UPDATE passenger_orders SET is_active = 0 WHERE id = $1 AND user_id = $2 AND is_active = 1",
                order_id, requester_id
            )
        else:
            result = await db.execute(
                "UPDATE passenger_orders SET is_active = 0 WHERE id = $1 AND is_active = 1",
                order_id
            )
        # asyncpg "UPDATE N" formatida qaytaradi
        try:
            affected = int(result.split()[-1])
        except Exception:
            affected = 0
        return affected > 0


async def get_passenger_orders_for_driver(telegram_id: int):
    async with pool.acquire() as db:
        query = """
            SELECT DISTINCT p.id, p.full_name, p.phone, p.from_loc, p.to_loc, p.seats_needed, p.created_at, p.target_driver_id
            FROM passenger_orders p
            JOIN driver_routes r ON p.from_loc = r.from_loc AND p.to_loc = r.to_loc
            WHERE r.telegram_id = $1
              AND p.is_active = 1
              AND (p.target_driver_id = 0 OR p.target_driver_id = $1)
              AND (
                  (p.service_type = 'cargo' AND p.created_at >= NOW() - INTERVAL '4 hours')
                  OR
                  (p.service_type != 'cargo' AND p.created_at >= NOW() - INTERVAL '2 hours')
              )
            ORDER BY p.id DESC LIMIT 15
        """
        return await db.fetch(query, telegram_id)


async def get_matching_driver_ids(from_loc: str, to_loc: str):
    async with pool.acquire() as db:
        query = """
            SELECT DISTINCT d.telegram_id
            FROM driver_routes r
            JOIN drivers d ON r.telegram_id = d.telegram_id
            WHERE r.from_loc = $1 AND r.to_loc = $2 AND d.status = 'waiting' AND d.is_active = 1
        """
        rows = await db.fetch(query, from_loc, to_loc)
        return [row["telegram_id"] for row in rows]


async def get_nearest_services(lat: float, lon: float, service_type: str, limit: int = 10, fuel_type: str = None):
    """
    Statik (roadside_services) va pullik e'lonlar (service_ads) ikkalasida ham
    fuel_type filtri bir xil tarzda qo'llaniladi (avval faqat service_ads'da ishlar edi).
    """
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
              AND ($5::text IS NULL OR fuel_types IS NULL OR fuel_types LIKE '%' || $5 || '%')

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
        return await db.fetch(query, lat, lon, service_type, limit, fuel_type)


async def get_stats():
    async with pool.acquire() as db:
        total_drivers = await db.fetchval("SELECT COUNT(*) FROM drivers")
        total_routes = await db.fetchval("SELECT COUNT(*) FROM driver_routes")
        total_orders = await db.fetchval("SELECT COUNT(*) FROM passenger_orders")
        total_logs = await db.fetchval("SELECT COUNT(*) FROM activity_logs")
        total_admins = await db.fetchval("SELECT COUNT(*) FROM admins")
        total_banned = await db.fetchval("SELECT COUNT(*) FROM users WHERE is_banned = 1")
        return {
            "drivers": total_drivers,
            "routes": total_routes,
            "orders": total_orders,
            "logs": total_logs,
            "admins": total_admins,
            "banned": total_banned
        }


async def get_all_drivers():
    async with pool.acquire() as db:
        return await db.fetch("SELECT * FROM drivers ORDER BY telegram_id DESC LIMIT 20")


# ---- Haydovchi obuna to'lovlari (atomik tasdiqlash bilan, ikki marta ishlamaydi) ----

async def save_driver_payment(user_id: int, photo_id: str) -> int:
    async with pool.acquire() as db:
        row = await db.fetchrow("""
            INSERT INTO driver_payments (user_id, photo_id, status)
            VALUES ($1, $2, 'pending')
            RETURNING id
        """, user_id, photo_id)
        return row["id"] if row else None


async def approve_driver_payment(payment_id: int):
    """
    Atomik: faqat 'pending' holatdagi to'lovni 'approved'ga o'tkazadi.
    Agar allaqachon tasdiqlangan/rad etilgan bo'lsa, None qaytaradi
    (shu orqali ikki marta bosilganda qayta ishlamaydi).
    Muvaffaqiyatli bo'lsa user_id qaytaradi va obunani uzaytiradi.
    """
    async with pool.acquire() as db:
        row = await db.fetchrow("""
            UPDATE driver_payments SET status = 'approved'
            WHERE id = $1 AND status = 'pending'
            RETURNING user_id
        """, payment_id)
        if not row:
            return None
        user_id = row["user_id"]

    await extend_driver_subscription(user_id, days=30)
    return user_id


async def reject_driver_payment(payment_id: int, reason: str):
    """Atomik: faqat 'pending' holatdagi to'lovni 'rejected'ga o'tkazadi va user_id qaytaradi."""
    async with pool.acquire() as db:
        row = await db.fetchrow("""
            UPDATE driver_payments SET status = 'rejected', reject_reason = $2
            WHERE id = $1 AND status = 'pending'
            RETURNING user_id
        """, payment_id, reason)
        return row["user_id"] if row else None


async def get_pending_driver_payments_older_than(hours: int = 6):
    async with pool.acquire() as db:
        return await db.fetch("""
            SELECT id, user_id FROM driver_payments
            WHERE status = 'pending' AND reminded = 0
              AND created_at < NOW() - ($1 || ' hours')::interval
        """, str(hours))


async def mark_driver_payment_reminded(payment_id: int):
    async with pool.acquire() as db:
        await db.execute("UPDATE driver_payments SET reminded = 1 WHERE id = $1", payment_id)


async def get_pending_service_payments_older_than(hours: int = 6):
    async with pool.acquire() as db:
        return await db.fetch("""
            SELECT id, ad_id FROM service_payments
            WHERE status = 'pending' AND reminded = 0
              AND created_at < NOW() - ($1 || ' hours')::interval
        """, str(hours))


async def mark_service_payment_reminded(payment_id: int):
    async with pool.acquire() as db:
        await db.execute("UPDATE service_payments SET reminded = 1 WHERE id = $1", payment_id)


async def save_complaint(from_user_id: int, target_driver_id: int, text: str):
    async with pool.acquire() as db:
        await db.execute("""
            INSERT INTO complaints (from_user_id, target_driver_id, text)
            VALUES ($1, $2, $3)
        """, from_user_id, target_driver_id, text)


# ---- Xizmat e'lonlari uchun funksiyalar ----

async def save_service_ad(data: dict) -> int:
    user_id = data.get("user_id") or data.get("telegram_id")
    fuel_list = data.get("fuel_types") or []
    fuel_str = ",".join(fuel_list) if fuel_list else None
    async with pool.acquire() as db:
        row = await db.fetchrow("""
            INSERT INTO service_ads
            (user_id, service_type, fuel_types, name, latitude, longitude, phone, description, photo_id, is_active)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, 0)
            RETURNING id
        """,
            user_id, data.get("service_type"), fuel_str, data.get("name"),
            data.get("latitude"), data.get("longitude"), data.get("phone"),
            data.get("description"), data.get("photo_id")
        )
        return row["id"] if row else None


async def save_service_payment(ad_id: int, user_id: int, amount: int, photo_id: str):
    async with pool.acquire() as db:
        await db.execute("""
            INSERT INTO service_payments (ad_id, user_id, amount, photo_id, status)
            VALUES ($1, $2, $3, $4, 'pending')
        """, ad_id, user_id, amount, photo_id)


async def has_pending_service_ad(user_id: int) -> bool:
    """Foydalanuvchida ko'rib chiqilayotgan (pending) e'lon bor-yo'qligini tekshiradi (spam nazorati)."""
    async with pool.acquire() as db:
        row = await db.fetchrow("""
            SELECT sa.id FROM service_ads sa
            JOIN service_payments sp ON sp.ad_id = sa.id
            WHERE sa.user_id = $1 AND sp.status = 'pending'
            LIMIT 1
        """, user_id)
        return bool(row)


async def get_user_service_ads(user_id: int, limit: int = 10):
    """Foydalanuvchining o'z e'lonlari ro'yxati - holati bilan birga ('📋 Mening e'lonlarim' uchun)."""
    async with pool.acquire() as db:
        return await db.fetch("""
            SELECT sa.id, sa.service_type, sa.name, sa.is_active, sa.expires_at, sa.created_at,
                   sp.status AS payment_status, sp.reject_reason
            FROM service_ads sa
            LEFT JOIN (
                SELECT DISTINCT ON (ad_id) ad_id, status, reject_reason
                FROM service_payments
                ORDER BY ad_id, id DESC
            ) sp ON sp.ad_id = sa.id
            WHERE sa.user_id = $1
            ORDER BY sa.created_at DESC
            LIMIT $2
        """, user_id, limit)


async def expire_service_ads():
    """
    Muddati tugagan e'lonlarni is_active=0 ga o'tkazadi (avval faqat qidiruvda
    yashiringan, lekin bazada "faol" bo'lib chalkashlik tug'dirardi).
    Xabar berish uchun (id, user_id, name) ro'yxatini qaytaradi.
    """
    async with pool.acquire() as db:
        rows = await db.fetch("""
            UPDATE service_ads SET is_active = 0
            WHERE is_active = 1 AND expires_at IS NOT NULL AND expires_at <= NOW()
            RETURNING id, user_id, name
        """)
        return rows


async def get_service_ads_expiring_soon(days_before: int = 3):
    """Muddati 'days_before' kundan keyin tugaydigan, hali eslatma yuborilmagan e'lonlar."""
    async with pool.acquire() as db:
        return await db.fetch("""
            SELECT id, user_id, name FROM service_ads
            WHERE is_active = 1
              AND expires_at IS NOT NULL
              AND expires_at <= NOW() + ($1 || ' days')::interval
              AND expires_at > NOW()
              AND (last_expiry_reminder IS NULL OR last_expiry_reminder < NOW() - INTERVAL '4 days')
        """, str(days_before))


async def mark_service_ad_expiry_reminded(ad_id: int):
    async with pool.acquire() as db:
        await db.execute("UPDATE service_ads SET last_expiry_reminder = NOW() WHERE id = $1", ad_id)


async def activate_service_ad(ad_id: int, days: int = 30):
    async with pool.acquire() as db:
        expires = datetime.datetime.now() + datetime.timedelta(days=days)
        # last_expiry_reminder ham tozalanadi - aks holda yangilangan e'lon uchun
        # eslatma tizimi "eski" holatni eslab qolib, yangi muddat uchun ishlamay qolishi mumkin
        await db.execute(
            "UPDATE service_ads SET is_active = 1, expires_at = $1, last_expiry_reminder = NULL WHERE id = $2",
            expires, ad_id
        )
        return await db.fetchrow("SELECT * FROM service_ads WHERE id = $1", ad_id)


async def reject_service_ad(ad_id: int):
    async with pool.acquire() as db:
        row = await db.fetchrow("SELECT * FROM service_ads WHERE id = $1", ad_id)
        await db.execute("UPDATE service_ads SET is_active = 0 WHERE id = $1", ad_id)
        return row


async def activate_service_ad_once(ad_id: int, days: int = 30):
    """
    Atomik: shu ad_id uchun 'pending' holatdagi to'lovni topib 'approved'ga o'tkazadi.
    Agar allaqachon tasdiqlangan/rad etilgan bo'lsa None qaytaradi (ikki marta ishlamaydi).
    """
    async with pool.acquire() as db:
        row = await db.fetchrow("""
            UPDATE service_payments SET status = 'approved'
            WHERE ad_id = $1 AND status = 'pending'
            RETURNING id
        """, ad_id)
        if not row:
            return None
    return await activate_service_ad(ad_id, days=days)


async def reject_service_ad_once(ad_id: int, reason: str = ""):
    async with pool.acquire() as db:
        row = await db.fetchrow("""
            UPDATE service_payments SET status = 'rejected', reject_reason = $2
            WHERE ad_id = $1 AND status = 'pending'
            RETURNING id
        """, ad_id, reason)
        if not row:
            return None
    return await reject_service_ad(ad_id)
