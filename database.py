import os
import asyncpg
import datetime

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

        # Yo'l bo'yi xizmatlari jadvali (Monetizatsiya va GPS uchun)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS roadside_services (
                id SERIAL PRIMARY KEY,
                service_type TEXT,
                name TEXT,
                latitude DOUBLE PRECISION,
                longitude DOUBLE PRECISION,
                phone TEXT,
                description TEXT
            )
        """)

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

        await db.execute("INSERT INTO system_settings (key, value) VALUES ('super_admin_password', 'admin777') ON CONFLICT (key) DO NOTHING")
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
            return datetime.datetime.now() < sub_end
        except Exception:
            return False

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
                await db.execute("""
                    INSERT INTO driver_routes (telegram_id, from_loc, to_loc, route_category, seats, accepts_post)
                    VALUES ($1, $2, $3, $4, 4, 1)
                """, telegram_id, f, t, route_category)
        await db.execute("UPDATE drivers SET status = 'waiting', updated_at = CURRENT_TIMESTAMP WHERE telegram_id = $1", telegram_id)

async def add_driver_single_route(telegram_id: int, from_loc: str, to_loc: str, route_category: str = 'local'):
    async with pool.acquire() as db:
        await db.execute("""
            INSERT INTO driver_routes (telegram_id, from_loc, to_loc, route_category, seats, accepts_post)
            VALUES ($1, $2, $3, $4, 4, 1)
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

async def add_passenger_order(user_id: int, full_name: str, phone: str, from_loc: str, to_loc: str, seats: int = 1, target_driver_id: int = 0, service_type: str = 'passenger'):
    async with pool.acquire() as db:
        row = await db.fetchrow("""
            INSERT INTO passenger_orders (user_id, full_name, phone, from_loc, to_loc, seats_needed, target_driver_id, service_type, is_active)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, 1)
            RETURNING id
        """, user_id, full_name, phone, from_loc, to_loc, seats, target_driver_id, service_type)
        return row["id"] if row else None

async def close_passenger_order(order_id: int):
    async with pool.acquire() as db:
        await db.execute("UPDATE passenger_orders SET is_active = 0 WHERE id = $1", order_id)

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

async def get_nearest_services(lat: float, lon: float, service_type: str, limit: int = 10):
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
            ORDER BY distance ASC
            LIMIT $4
        """
        return await db.fetch(query, lat, lon, service_type, limit)

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

# ============ SERVICE ADS FUNCTIONS ============

async def save_service_ad(data: dict) -> int:
    async with pool.acquire() as db:
        row = await db.fetchrow("""
            INSERT INTO service_ads 
            (user_id, service_type, name, latitude, longitude, phone, description, photo_id, is_active)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, 0)
            RETURNING id
        """, data.get('telegram_id'), data.get('service_type'), data.get('name'), 
            data.get('latitude'), data.get('longitude'), data.get('phone'), 
            data.get('description'), data.get('photo_id'))
        return row['id'] if row else None

async def save_service_payment(ad_id: int, user_id: int, amount: int, photo_id: str):
    async with pool.acquire() as db:
        await db.execute("""
            INSERT INTO service_payments (ad_id, user_id, amount, receipt_photo_id, status)
            VALUES ($1, $2, $3, $4, 0)
        """, ad_id, user_id, amount, photo_id)

async def activate_service_ad(ad_id: int, days: int = 30):
    async with pool.acquire() as db:
        now = datetime.datetime.now()
        end = now + datetime.timedelta(days=days)
        await db.execute("""
            UPDATE service_ads 
            SET is_active = 1, start_date = $1, end_date = $2
            WHERE id = $3
        """, now, end, ad_id)
        return await db.fetchrow("SELECT * FROM service_ads WHERE id = $1", ad_id)

async def reject_service_ad(ad_id: int):
    async with pool.acquire() as db:
        await db.execute("UPDATE service_ads SET is_active = 2 WHERE id = $1", ad_id)
        return await db.fetchrow("SELECT * FROM service_ads WHERE id = $1", ad_id)

async def get_service_ad(ad_id: int):
    async with pool.acquire() as db:
        return await db.fetchrow("SELECT * FROM service_ads WHERE id = $1", ad_id)

async def get_active_service_ads():
    async with pool.acquire() as db:
        return await db.fetch("""
            SELECT * FROM service_ads 
            WHERE is_active = 1 AND end_date > NOW()
            ORDER BY created_at DESC
        """)
