import hashlib
import hmac
import json
import time
import asyncio
from pathlib import Path
from urllib.parse import parse_qsl

from aiohttp import web

import database as db
from config import ADMIN_ID, BOT_TOKEN

STATIC_DIR = Path(__file__).parent / "webapp" / "dist"

MAX_ORDERS_PER_HOUR = 3  # handlers.py bilan bir xil qiymat

# service_ad.py dagi narxlar bilan bir xil (ikkalasini bitta joyda saqlash
# uchun kelajakda service_ad.SERVICE_TYPES ni import qilib olsa ham bo'ladi,
# lekin doiraviy import muammosining oldini olish uchun shu yerda takrorlangan)
SERVICE_PRICES = {
    "gas": 50000,
    "food": 50000,
    "hotel": 70000,
    "service": 50000,
    "autosalon": 100000,
}


# ------------------------------------------------------------------ #
#  Telegram auth helpers                                             #
# ------------------------------------------------------------------ #

def validate_webapp_init_data(init_data: str, max_age: int = 86400):
    """Validates the initData string a Telegram Mini App sends (WebApp scheme)."""
    try:
        parsed = dict(parse_qsl(init_data, strict_parsing=True))
    except ValueError:
        return None
    received_hash = parsed.pop("hash", None)
    if not received_hash:
        return None
    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(parsed.items()))
    secret_key = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
    computed = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(computed, received_hash):
        return None
    auth_date = int(parsed.get("auth_date", "0"))
    if max_age and (time.time() - auth_date) > max_age:
        return None
    user_raw = parsed.get("user")
    return json.loads(user_raw) if user_raw else None


def validate_login_widget(payload: dict, max_age: int = 86400 * 7):
    """Validates the payload Telegram's Login Widget sends (browser scheme)."""
    data = dict(payload)
    received_hash = data.pop("hash", None)
    if not received_hash:
        return None
    data_check_string = "\n".join(f"{k}={data[k]}" for k in sorted(data.keys()) if data[k] is not None)
    secret_key = hashlib.sha256(BOT_TOKEN.encode()).digest()
    computed = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(computed, received_hash):
        return None
    auth_date = int(data.get("auth_date", "0"))
    if max_age and (time.time() - auth_date) > max_age:
        return None
    return data


def make_session_token(user_id, ttl: int = 86400 * 7) -> str:
    expires = int(time.time()) + ttl
    payload = f"{user_id}.{expires}"
    sig = hmac.new(BOT_TOKEN.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}.{sig}"


def verify_session_token(token: str):
    try:
        user_id_s, expires_s, sig = token.split(".")
        payload = f"{user_id_s}.{expires_s}"
        expected = hmac.new(BOT_TOKEN.encode(), payload.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, sig):
            return None
        if int(expires_s) < time.time():
            return None
        return int(user_id_s)
    except Exception:
        return None


async def get_current_user(request: web.Request):
    init_data = request.headers.get("X-Init-Data")
    if init_data:
        user = validate_webapp_init_data(init_data)
        if user:
            return user
    token = request.headers.get("X-Session-Token")
    if token:
        uid = verify_session_token(token)
        if uid:
            return {"id": uid, "first_name": "", "username": ""}
    return None


def require_auth(handler):
    async def wrapper(request):
        user = await get_current_user(request)
        if not user:
            return web.json_response({"error": "unauthorized"}, status=401)
        banned, reason = await db.is_user_banned(user["id"])
        if banned:
            return web.json_response({"error": "banned", "reason": reason}, status=403)
        request["user"] = user
        return await handler(request)
    return wrapper


def require_admin(handler):
    async def wrapper(request):
        user = await get_current_user(request)
        if not user:
            return web.json_response({"error": "unauthorized"}, status=401)
        if not await db.is_admin(user["id"], ADMIN_ID):
            return web.json_response({"error": "forbidden"}, status=403)
        request["user"] = user
        return await handler(request)
    return wrapper


def row_list(rows):
    return [dict(r) for r in rows]


# ------------------------------------------------------------------ #
#  Public endpoints (no auth required)                                #
# ------------------------------------------------------------------ #

async def auth_login_widget(request: web.Request):
    payload = await request.json()
    data = validate_login_widget(payload)
    if not data:
        return web.json_response({"error": "invalid_signature"}, status=401)
    token = make_session_token(int(data["id"]))
    return web.json_response({"token": token, "user": data})


async def public_stats(request: web.Request):
    return web.json_response(await db.get_stats())


async def roadside_search(request: web.Request):
    """
    Eslatma: database.get_nearest_services() natijasida hozircha `id` va
    `fuel_types` ustunlari qaytarilmaydi (faqat name/phone/description/
    latitude/longitude/distance) - shuning uchun frontend ham shunga mos
    ravishda ro'yxat indeksini kalit sifatida ishlatadi va yoqilg'i
    turlarini alohida ko'rsatmaydi. Yoqilg'i bo'yicha filtrlash serverda,
    `fuel` parametri orqali (bitta tur) amalga oshiriladi - xuddi bot
    ichidagi ⛽️ Zapravka oqimidagi kabi.
    """
    service_type = request.query.get("type", "gas")
    fuel = request.query.get("fuel") or None
    lat = float(request.query.get("lat", 41.3111))
    lon = float(request.query.get("lon", 69.2797))
    rows = await db.get_nearest_services(lat, lon, service_type, limit=20, fuel_type=fuel)
    return web.json_response(row_list(rows))


# ------------------------------------------------------------------ #
#  Authenticated endpoints                                            #
# ------------------------------------------------------------------ #

@require_auth
async def me(request: web.Request):
    uid = request["user"]["id"]
    driver = await db.get_driver(uid)
    is_admin_flag = await db.is_admin(uid, ADMIN_ID)
    return web.json_response({
        "id": uid,
        "first_name": request["user"].get("first_name", ""),
        "is_admin": is_admin_flag,
        "has_driver_profile": driver is not None,
    })


@require_auth
async def drivers_search(request: web.Request):
    """
    Botning finalize_passenger_search() bilan bir xil mantiq: oddiy
    driver_routes bo'yicha qidiruv + faol ko'p-bekatli safardagi
    haydovchilar, ikkalasi birlashtirilib, takrorlanganlar olib tashlanadi.
    """
    body = await request.json()
    from_loc, to_loc = body.get("from_loc"), body.get("to_loc")
    service_type = body.get("service_type", "passenger")
    if not from_loc or not to_loc:
        return web.json_response({"error": "missing_locations"}, status=400)

    static_drivers = await db.search_drivers(from_loc, to_loc)
    trip_drivers = await db.search_active_trip_drivers(from_loc, to_loc, service_type)

    seen_ids = set()
    matches = []
    for drv in list(static_drivers) + list(trip_drivers):
        d = dict(drv)
        if d["telegram_id"] not in seen_ids:
            seen_ids.add(d["telegram_id"])
            matches.append(d)

    return web.json_response({"matches": matches})


async def _delayed_notify(bot, driver_ids, text, delay):
    await asyncio.sleep(delay)
    for did in driver_ids:
        try:
            await bot.send_message(chat_id=did, text=text, parse_mode="HTML")
        except Exception:
            pass


@require_auth
async def create_order(request: web.Request):
    """
    Botning psg_order_phone_submit() / finalize_passenger_search() bilan bir
    xil mantiq: soatlik limit, ikkala manbadan (oddiy + safardagi) haydovchi
    ID'lari, VIP/oddiy ustuvorlik bo'yicha darhol/kechiktirilgan yuborish.
    """
    bot = request.app["bot"]
    body = await request.json()
    uid = request["user"]["id"]
    from_loc, to_loc = body.get("from_loc"), body.get("to_loc")
    service_type = body.get("service_type", "passenger")
    full_name = body.get("full_name") or "Veb foydalanuvchi"
    phone = body.get("phone") or await db.get_user_phone(uid)

    if not phone:
        return web.json_response({"error": "phone_required"}, status=400)
    if not from_loc or not to_loc:
        return web.json_response({"error": "missing_locations"}, status=400)

    recent_count = await db.count_recent_orders(uid, minutes=60)
    if recent_count >= MAX_ORDERS_PER_HOUR:
        return web.json_response({"error": "rate_limited"}, status=429)

    await db.save_user_phone(uid, full_name, phone)
    order_id = await db.add_passenger_order(
        user_id=uid, full_name=full_name, phone=phone,
        from_loc=from_loc, to_loc=to_loc, seats=1, target_driver_id=0, service_type=service_type,
    )

    driver_ids = list(set(
        await db.get_matching_driver_ids(from_loc, to_loc) +
        await db.get_matching_driver_ids_from_trips(from_loc, to_loc, service_type)
    ))
    monetization_on = (await db.get_setting("monetization_active", "0")) == "1"
    vip_ids, free_ids = [], []
    for d_id in driver_ids:
        if monetization_on and not await db.is_driver_subscribed(d_id):
            free_ids.append(d_id)
        else:
            vip_ids.append(d_id)

    order_title = "📦 <b>Yangi Pochta/Yuk buyurtmasi!</b>" if service_type == "cargo" else "🔔 <b>Yangi yo'lovchi buyurtmasi!</b>"
    text = f"{order_title}\n\n📍 <b>Yo'nalish:</b> {from_loc} ➡️ {to_loc}\n👤 <b>Mijoz:</b> {full_name}\n📞 <b>Telefon:</b> {phone}\n\n🌐 Veb-ilova orqali yuborildi"

    for vid in vip_ids:
        try:
            await bot.send_message(chat_id=vid, text=text, parse_mode="HTML")
        except Exception:
            pass

    if monetization_on and free_ids:
        asyncio.create_task(_delayed_notify(bot, free_ids, text, 300))

    return web.json_response({"order_id": order_id, "notified_now": len(vip_ids), "notified_later": len(free_ids)})


@require_auth
async def driver_register(request: web.Request):
    uid = request["user"]["id"]
    body = await request.json()
    data = {
        "telegram_id": uid,
        "full_name": body.get("full_name", ""),
        "phone": body.get("phone", ""),
        "service_type": body.get("service_type", "passenger"),
        "car_model": body.get("car_model", ""),
        "car_number": (body.get("car_number") or "").upper(),
        "photo_id": "",
    }
    if not all([data["full_name"], data["phone"], data["car_model"], data["car_number"]]):
        return web.json_response({"error": "missing_fields"}, status=400)
    await db.save_driver(data)
    await db.extend_driver_subscription(uid, days=30)
    await db.log_activity(uid, data["full_name"], "DRIVER_REGISTER_WEB", data["car_model"])
    return web.json_response({"ok": True})


@require_auth
async def driver_me(request: web.Request):
    uid = request["user"]["id"]
    driver = await db.get_driver(uid)
    if not driver:
        return web.json_response({"driver": None})
    is_sub = await db.is_driver_subscribed(uid)
    count = await db.get_driver_routes_count(uid)
    trip = await db.get_active_trip_for_driver(uid)
    return web.json_response({
        "driver": dict(driver),
        "is_subscribed": is_sub,
        "routes_count": count,
        "has_active_trip": bool(trip),
    })


@require_auth
async def driver_set_status(request: web.Request):
    """
    Diqqat: bu faqat oddiy 'waiting'/'on_way' holatini almashtiradi (botdagi
    "🔄 Oddiy safar" varianti bilan bir xil). Ko'p-bekatli safar (bekatlar
    zanjiri) ni sozlash hozircha faqat bot chatida mavjud - bu yerda emas.
    'waiting'ga o'tishda faol safar bo'lsa (bordi-yu mavjud bo'lsa) bekor
    qilinadi, xuddi bot ichidagi "🟢 Mijoz kutmoqdaman" tugmasi kabi.
    """
    uid = request["user"]["id"]
    body = await request.json()
    status = body.get("status")
    if status not in ("waiting", "on_way"):
        return web.json_response({"error": "invalid_status"}, status=400)
    if status == "waiting":
        await db.cancel_active_trip_for_driver(uid)
    await db.set_driver_status(uid, status)
    return web.json_response({"ok": True})


@require_auth
async def driver_add_routes(request: web.Request):
    """Botdagi bepul tarif marshrut limiti (can_add_more_routes) bu yerda ham tekshiriladi."""
    uid = request["user"]["id"]
    body = await request.json()
    category = body.get("category", "intercity")

    if category == "local":
        from_loc, to_loc = body.get("from_loc"), body.get("to_loc")
        if not from_loc or not to_loc:
            return web.json_response({"error": "missing_locations"}, status=400)
        allowed, limit = await db.can_add_more_routes(uid, 1)
        if not allowed:
            return web.json_response({"error": "route_limit_reached", "limit": limit}, status=403)
        await db.add_driver_single_route(uid, from_loc, to_loc, route_category="local")
    else:
        from_list = body.get("from_list", [])
        to_list = body.get("to_list", [])
        if not from_list or not to_list:
            return web.json_response({"error": "missing_locations"}, status=400)
        allowed, limit = await db.can_add_more_routes(uid, len(from_list) * len(to_list))
        if not allowed:
            return web.json_response({"error": "route_limit_reached", "limit": limit}, status=403)
        await db.add_driver_multi_routes(uid, from_list, to_list, route_category="intercity")

    return web.json_response({"ok": True})


@require_auth
async def driver_clear_routes(request: web.Request):
    uid = request["user"]["id"]
    await db.clear_driver_routes(uid)
    await db.cancel_active_trip_for_driver(uid)
    return web.json_response({"ok": True})


@require_auth
async def driver_orders(request: web.Request):
    uid = request["user"]["id"]
    rows = await db.get_passenger_orders_for_driver(uid)
    return web.json_response(row_list(rows))


@require_auth
async def submit_ad(request: web.Request):
    """
    Botdagi service_receipt_received() bilan bir xil ikki bosqich:
    save_service_ad() (e'lon yozuvi) + save_service_payment() (kutilayotgan
    to'lov yozuvi) - ikkinchisi bo'lmasa, admin uni hech qachon tasdiqlay
    olmaydi (activate_service_ad_once shu jadvaldan qidiradi).
    Chek rasmi hozircha veb orqali yuklanmaydi (photo_id bo'sh qoladi) -
    admin buni bot ichida ko'rgan holatidagidek emas, faqat matn ko'radi.
    """
    uid = request["user"]["id"]
    body = await request.json()

    if await db.has_pending_service_ad(uid):
        return web.json_response({"error": "already_pending"}, status=409)

    required = ["service_type", "name", "phone", "description", "latitude", "longitude"]
    if not all(body.get(f) not in (None, "") for f in required):
        return web.json_response({"error": "missing_fields"}, status=400)

    svc_type = body.get("service_type")
    if svc_type not in SERVICE_PRICES:
        return web.json_response({"error": "invalid_service_type"}, status=400)

    data = {
        "user_id": uid,
        "service_type": svc_type,
        "fuel_types": body.get("fuel_types", []),
        "name": body.get("name"),
        "latitude": body.get("latitude"),
        "longitude": body.get("longitude"),
        "phone": body.get("phone"),
        "description": body.get("description"),
        "photo_id": "",
    }
    ad_id = await db.save_service_ad(data)
    amount = SERVICE_PRICES[svc_type]
    await db.save_service_payment(ad_id, uid, amount, photo_id="")
    await db.log_activity(uid, body.get("name", ""), "AD_SUBMIT_WEB", "Veb-ilova orqali")

    admin_recipients = await db.get_backup_recipients(ADMIN_ID)
    bot = request.app["bot"]
    caption = (
        f"🔔 <b>Yangi to'lovli e'lon (veb-ilova orqali)!</b>\n\n"
        f"🏷 Tur: {svc_type}\n"
        f"📌 Nomi: {data['name']}\n"
        f"💰 Summa: {amount:,} so'm\n\n"
        f"⚠️ Chek rasmi yo'q — veb-ilova orqali yuborilgan, tasdiqlashdan oldin "
        f"foydalanuvchi bilan bog'lanib tekshiring: {data['phone']}"
    )
    for aid in admin_recipients:
        try:
            await bot.send_message(chat_id=aid, text=caption, parse_mode="HTML")
        except Exception:
            pass

    return web.json_response({"ad_id": ad_id, "amount": amount})


@require_auth
async def my_orders(request: web.Request):
    """database.py da 'foydalanuvchining o'z buyurtmalari' funksiyasi yo'q
    (faqat haydovchi tomoni bor), shuning uchun database.py ga tegmasdan
    shu yerda to'g'ridan-to'g'ri (faqat o'qish) so'rov yuboriladi."""
    uid = request["user"]["id"]
    async with db.pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT id, from_loc, to_loc, phone, service_type, is_active, created_at
            FROM passenger_orders WHERE user_id = $1
            ORDER BY id DESC LIMIT 20
        """, uid)
    return web.json_response(row_list(rows))


@require_auth
async def my_ads(request: web.Request):
    uid = request["user"]["id"]
    rows = await db.get_user_service_ads(uid)
    return web.json_response(row_list(rows))


@require_auth
async def my_settings_get(request: web.Request):
    uid = request["user"]["id"]
    phone = await db.get_user_phone(uid)
    return web.json_response({"phone": phone})


@require_auth
async def my_settings_save(request: web.Request):
    uid = request["user"]["id"]
    body = await request.json()
    phone = (body.get("phone") or "").strip()
    if not phone:
        return web.json_response({"error": "phone_required"}, status=400)
    full_name = request["user"].get("first_name") or "Veb foydalanuvchi"
    await db.save_user_phone(uid, full_name, phone)
    return web.json_response({"ok": True})


# ------------------------------------------------------------------ #
#  Admin-only endpoints                                                #
# ------------------------------------------------------------------ #

@require_admin
async def admin_stats(request: web.Request):
    return web.json_response(await db.get_stats())


@require_admin
async def admin_logs(request: web.Request):
    rows = await db.get_recent_admin_logs(30)
    return web.json_response(row_list(rows))


@require_admin
async def admin_set_monetization(request: web.Request):
    """Botning mon_start_2_cb / mon_stop_2_cb bilan bir xil: yoqilganda barcha haydovchilarga 7 kunlik bepul muhlat beriladi."""
    bot = request.app["bot"]
    body = await request.json()
    active = bool(body.get("active"))
    await db.set_setting("monetization_active", "1" if active else "0")
    await db.log_activity(request["user"]["id"], "Admin", "MONETIZATION_TOGGLE_WEB", str(active))

    if active:
        driver_ids = await db.grant_grace_days_to_all_drivers(days=7)
        text = (
            "🌟 <b>Hurmatli haydovchilar!</b>\n\nTizimimizda oylik obuna rejimi ishga tushirildi.\n\n"
            "Sizga <b>7 kunlik bepul muhlat</b> berildi. Shu muddat davomida kabinetingizdagi "
            "<b>[ 🌟 Tarif va Obuna ]</b> tugmasi orqali obunangizni faollashtirib qo'ying."
        )
        for did in driver_ids:
            try:
                await bot.send_message(chat_id=did, text=text, parse_mode="HTML")
            except Exception:
                pass
    else:
        text = "🛑 Monetizatsiya to'xtatildi. Bot yana to'liq bepul rejimga o'tkazildi."
        for uid in await db.get_all_user_ids():
            try:
                await bot.send_message(chat_id=uid, text=text)
            except Exception:
                pass

    return web.json_response({"ok": True})


@require_admin
async def admin_set_maintenance(request: web.Request):
    bot = request.app["bot"]
    body = await request.json()
    active = bool(body.get("active"))
    await db.set_setting("maintenance_mode", "1" if active else "0")
    await db.log_activity(
        request["user"]["id"], "Admin", "KILL_SWITCH_WEB" if active else "START_SWITCH_WEB", str(active)
    )
    text = "🛠 Bot texnik xizmat uchun vaqtincha to'xtatildi." if active else "🎉 Bot yana faol!"
    for uid in await db.get_all_user_ids():
        try:
            await bot.send_message(chat_id=uid, text=text)
        except Exception:
            pass
    return web.json_response({"ok": True})


@require_admin
async def admin_ban(request: web.Request):
    body = await request.json()
    uid = int(body["telegram_id"])
    hours = body.get("duration_hours")
    await db.ban_user(uid, body.get("reason", "Qoidalarni buzganlik uchun"), duration_hours=hours)
    await db.log_activity(request["user"]["id"], "Admin", "BAN_USER_WEB", f"Bloklandi: {uid}")
    return web.json_response({"ok": True})


@require_admin
async def admin_unban(request: web.Request):
    body = await request.json()
    uid = int(body["telegram_id"])
    await db.unban_user(uid)
    await db.log_activity(request["user"]["id"], "Admin", "UNBAN_USER_WEB", f"Blokdan chiqarildi: {uid}")
    return web.json_response({"ok": True})


@require_admin
async def admin_drivers(request: web.Request):
    rows = await db.get_all_drivers()
    return web.json_response(row_list(rows))


@require_admin
async def admin_ads_pending(request: web.Request):
    """
    database.py da tayyor 'barcha kutilayotgan e'lonlar' funksiyasi yo'q
    (faqat bitta foydalanuvchi uchun has_pending_service_ad bor), shuning
    uchun database.py ga tegmasdan, shu yerda to'g'ridan-to'g'ri
    (faqat o'qish uchun) so'rov yuboramiz - har bir e'lon uchun eng oxirgi
    to'lov yozuvi 'pending' bo'lsagina ro'yxatga kiradi.
    """
    async with db.pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT sa.id, sa.user_id, sa.service_type, sa.fuel_types, sa.name,
                   sa.phone, sa.description, sa.latitude, sa.longitude,
                   sp.id AS payment_id, sp.amount
            FROM service_ads sa
            JOIN LATERAL (
                SELECT * FROM service_payments
                WHERE ad_id = sa.id ORDER BY id DESC LIMIT 1
            ) sp ON true
            WHERE sp.status = 'pending'
            ORDER BY sa.id DESC
            LIMIT 30
        """)
    return web.json_response(row_list(rows))


@require_admin
async def admin_ads_approve(request: web.Request):
    bot = request.app["bot"]
    ad_id = int(request.match_info["ad_id"])
    ad = await db.activate_service_ad_once(ad_id, days=30)
    if ad is None:
        return web.json_response({"error": "already_processed"}, status=409)
    try:
        await bot.send_message(
            chat_id=ad["user_id"],
            text=f"🎉 <b>Tabriklaymiz! E'loningiz tasdiqlandi!</b>\n\n📌 {ad['name']}\n📅 30 kun davomida faol bo'ladi.",
            parse_mode="HTML",
        )
    except Exception:
        pass
    return web.json_response({"ok": True})


@require_admin
async def admin_ads_reject(request: web.Request):
    bot = request.app["bot"]
    ad_id = int(request.match_info["ad_id"])
    body = await request.json()
    reason = (body.get("reason") or "Admin tomonidan rad etildi").strip()
    ad = await db.reject_service_ad_once(ad_id, reason)
    if ad is None:
        return web.json_response({"error": "already_processed"}, status=409)
    try:
        await bot.send_message(
            chat_id=ad["user_id"],
            text=f"❌ <b>E'loningiz bekor qilindi.</b>\n\nSabab: {reason}",
            parse_mode="HTML",
        )
    except Exception:
        pass
    return web.json_response({"ok": True})


@require_admin
async def admin_broadcast(request: web.Request):
    bot = request.app["bot"]
    body = await request.json()
    text = (body.get("text") or "").strip()
    if not text:
        return web.json_response({"error": "empty_text"}, status=400)
    sent = 0
    for uid in await db.get_all_user_ids():
        try:
            await bot.send_message(chat_id=uid, text=text)
            sent += 1
            await asyncio.sleep(0.04)
        except Exception:
            pass
    await db.log_activity(request["user"]["id"], "Admin", "BROADCAST_WEB", f"{sent} ta")
    return web.json_response({"sent": sent})


@require_admin
async def admin_get_admins(request: web.Request):
    rows = await db.get_all_admins()
    return web.json_response(row_list(rows))


@require_admin
async def admin_add_admin(request: web.Request):
    body = await request.json()
    tid = body.get("telegram_id")
    name = (body.get("full_name") or "").strip()
    if not tid or not name:
        return web.json_response({"error": "missing_fields"}, status=400)
    await db.add_admin(int(tid), name, request["user"]["id"])
    await db.log_activity(request["user"]["id"], "Admin", "ADD_ADMIN_WEB", f"Admin qo'shildi: {tid}")
    return web.json_response({"ok": True})


@require_admin
async def admin_remove_admin(request: web.Request):
    tid = int(request.match_info["admin_id"])
    await db.remove_admin(tid)
    await db.log_activity(request["user"]["id"], "Admin", "REMOVE_ADMIN_WEB", f"Admin o'chirildi: {tid}")
    return web.json_response({"ok": True})


@require_admin
async def admin_get_bans(request: web.Request):
    """database.py da 'barcha bloklanganlar' funksiyasi yo'q, shuning uchun
    (o'zgartirmasdan) shu yerda to'g'ridan-to'g'ri o'qish so'rovi yuboriladi."""
    async with db.pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT telegram_id, ban_reason, ban_until FROM users
            WHERE is_banned = 1 ORDER BY telegram_id DESC LIMIT 50
        """)
    return web.json_response(row_list(rows))


@require_admin
async def admin_get_card(request: web.Request):
    card = await db.get_setting("p2p_card_number", "8600123456789012")
    return web.json_response({"card_number": card})


@require_admin
async def admin_set_card(request: web.Request):
    body = await request.json()
    card = "".join(ch for ch in (body.get("card_number") or "") if ch.isdigit())
    if len(card) != 16:
        return web.json_response({"error": "invalid_card"}, status=400)
    await db.set_setting("p2p_card_number", card)
    await db.log_activity(request["user"]["id"], "Admin", "ADMIN_CHANGE_CARD_WEB", f"Yangi karta: {card}")
    return web.json_response({"ok": True})


@require_admin
async def admin_set_password(request: web.Request):
    body = await request.json()
    new_pass = body.get("new_password") or ""
    if len(new_pass) < 4:
        return web.json_response({"error": "password_too_short"}, status=400)
    await db.set_super_admin_password(new_pass)
    await db.log_activity(request["user"]["id"], "Admin", "ADMIN_CHANGE_PASSWORD_WEB", "Parol o'zgartirildi (veb orqali)")
    return web.json_response({"ok": True})


# ------------------------------------------------------------------ #
#  Route registration                                                 #
# ------------------------------------------------------------------ #

def register_webapp_routes(app: web.Application, bot):
    app["bot"] = bot

    app.router.add_post("/api/auth/login-widget", auth_login_widget)
    app.router.add_get("/api/stats/public", public_stats)
    app.router.add_get("/api/roadside", roadside_search)

    app.router.add_get("/api/me", me)
    app.router.add_post("/api/drivers/search", drivers_search)
    app.router.add_post("/api/orders", create_order)
    app.router.add_post("/api/driver/register", driver_register)
    app.router.add_get("/api/driver/me", driver_me)
    app.router.add_post("/api/driver/status", driver_set_status)
    app.router.add_post("/api/driver/routes", driver_add_routes)
    app.router.add_delete("/api/driver/routes", driver_clear_routes)
    app.router.add_get("/api/driver/orders", driver_orders)
    app.router.add_post("/api/ads", submit_ad)
    app.router.add_get("/api/me/orders", my_orders)
    app.router.add_get("/api/me/ads", my_ads)
    app.router.add_get("/api/me/settings", my_settings_get)
    app.router.add_post("/api/me/settings", my_settings_save)

    app.router.add_get("/api/admin/stats", admin_stats)
    app.router.add_get("/api/admin/logs", admin_logs)
    app.router.add_post("/api/admin/monetization", admin_set_monetization)
    app.router.add_post("/api/admin/maintenance", admin_set_maintenance)
    app.router.add_post("/api/admin/ban", admin_ban)
    app.router.add_post("/api/admin/unban", admin_unban)
    app.router.add_get("/api/admin/drivers", admin_drivers)
    app.router.add_get("/api/admin/admins", admin_get_admins)
    app.router.add_post("/api/admin/admins", admin_add_admin)
    app.router.add_delete("/api/admin/admins/{admin_id}", admin_remove_admin)
    app.router.add_get("/api/admin/bans", admin_get_bans)
    app.router.add_get("/api/admin/settings/card", admin_get_card)
    app.router.add_post("/api/admin/settings/card", admin_set_card)
    app.router.add_post("/api/admin/settings/password", admin_set_password)
    app.router.add_get("/api/admin/ads/pending", admin_ads_pending)
    app.router.add_post("/api/admin/ads/{ad_id}/approve", admin_ads_approve)
    app.router.add_post("/api/admin/ads/{ad_id}/reject", admin_ads_reject)
    app.router.add_post("/api/admin/broadcast", admin_broadcast)

    if STATIC_DIR.exists():
        async def spa_index(request):
            return web.FileResponse(STATIC_DIR / "index.html")

        app.router.add_get("/app", spa_index)
        app.router.add_get("/app/", spa_index)
        app.router.add_static("/app/static", STATIC_DIR, show_index=False)
