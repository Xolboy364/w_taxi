import asyncio
import logging
import datetime
import os
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.redis import RedisStorage
from aiohttp import web
from config import BOT_TOKEN, ADMIN_ID
from handlers import router
from service_ad import router as service_ad_router
import database as db

logging.basicConfig(level=logging.INFO)


async def handle_ping(request):
    return web.Response(text="Bot is running and healthy!")


async def start_web_server():
    app = web.Application()
    app.add_routes([web.get('/', handle_ping), web.get('/ping', handle_ping)])
    port = int(os.getenv("PORT", 8080))
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    print(f"[+] Web-server {port}-portda ishga tushdi.")


async def daily_backup_worker(bot: Bot):
    while True:
        await asyncio.sleep(86400)
        try:
            recipients = await db.get_backup_recipients(ADMIN_ID)
            now_str = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            stats = await db.get_stats()

            caption = (
                f"🛡 <b>24 Soatlik Tizim Statistikasi va Zaxirasi</b>\n"
                f"📅 Sana: <code>{now_str}</code>\n\n"
                f"👥 Haydovchilar: {stats['drivers']} ta\n"
                f"🛣 Yo‘nalishlar: {stats['routes']} ta\n"
                f"🙋‍♂️ Buyurtmalar: {stats['orders']} ta\n"
                f"📝 Audit loglari: {stats['logs']} ta"
            )

            for user_id in recipients:
                try:
                    await bot.send_message(chat_id=user_id, text=caption, parse_mode="HTML")
                except Exception as send_err:
                    logging.error(f"Zaxira yuborishda xatolik (ID {user_id}): {send_err}")
        except Exception as e:
            logging.error(f"Avto-zaxira tizimida xatolik: {e}")


async def scheduled_notifications_worker(bot: Bot):
    while True:
        now = datetime.datetime.now()
        if now.hour == 8 and now.minute == 0:
            maint = await db.get_setting("maintenance_mode", "0")
            if maint == "0":
                drivers = await db.get_all_drivers()
                for d in drivers:
                    try:
                        await bot.send_message(
                            chat_id=d["telegram_id"],
                            text="☀️ <b>Xayrli tong!</b>\nBugun yo‘lga chiqasizmi? Marshrutlaringizni tekshirib, faol holatga keltirib qo‘ying.",
                            parse_mode="HTML"
                        )
                    except Exception:
                        pass

                # Obunasi 3 kundan keyin tugaydigan haydovchilarga eslatma
                monet = await db.get_setting("monetization_active", "0")
                if monet == "1":
                    expiring = await db.get_drivers_expiring_soon(days_before=3)
                    for row in expiring:
                        try:
                            await bot.send_message(
                                chat_id=row["telegram_id"],
                                text=(
                                    "⏰ <b>Obunangiz muddati tez orada tugaydi!</b>\n\n"
                                    "Xizmatdan uzluksiz foydalanishni davom ettirish uchun "
                                    "<b>[ 🌟 Tarif va Obuna ]</b> bo‘limidan obunani uzaytiring."
                                ),
                                parse_mode="HTML"
                            )
                            await db.mark_expiry_reminded(row["telegram_id"])
                        except Exception:
                            pass
            await asyncio.sleep(60)
        await asyncio.sleep(30)


async def admin_payment_reminder_worker(bot: Bot):
    """
    6 soatdan beri ko'rib chiqilmagan (pending) to'lovlar haqida adminlarga
    bir martalik eslatma yuboradi (adminni tezlashtirish uchun).
    """
    while True:
        await asyncio.sleep(1800)  # har 30 daqiqada tekshiradi
        try:
            admin_recipients = await db.get_backup_recipients(ADMIN_ID)

            pending_driver = await db.get_pending_driver_payments_older_than(hours=6)
            if pending_driver:
                text = f"🔔 <b>Diqqat!</b> {len(pending_driver)} ta haydovchi to‘lovi 6 soatdan beri ko‘rib chiqilmagan."
                for aid in admin_recipients:
                    try:
                        await bot.send_message(chat_id=aid, text=text, parse_mode="HTML")
                    except Exception:
                        pass
                for row in pending_driver:
                    await db.mark_driver_payment_reminded(row["id"])

            pending_service = await db.get_pending_service_payments_older_than(hours=6)
            if pending_service:
                text = f"🔔 <b>Diqqat!</b> {len(pending_service)} ta xizmat e'loni to‘lovi 6 soatdan beri ko‘rib chiqilmagan."
                for aid in admin_recipients:
                    try:
                        await bot.send_message(chat_id=aid, text=text, parse_mode="HTML")
                    except Exception:
                        pass
                for row in pending_service:
                    await db.mark_service_payment_reminded(row["id"])
        except Exception as e:
            logging.error(f"Admin eslatma workerida xatolik: {e}")


async def service_ad_lifecycle_worker(bot: Bot):
    """
    1) Muddati tugagan xizmat e'lonlarini avtomatik is_active=0 qiladi va egasiga xabar beradi
       (avval faqat qidiruvdan yashirinardi, bazada "faol" bo'lib chalkashlik tug'dirardi).
    2) Muddati 3 kundan keyin tugaydigan e'lonlar egalariga eslatma yuboradi.
    """
    while True:
        await asyncio.sleep(3600)  # har soatda tekshiradi
        try:
            expired = await db.expire_service_ads()
            for row in expired:
                try:
                    await bot.send_message(
                        chat_id=row["user_id"],
                        text=(
                            f"⌛ <b>E'loningiz muddati tugadi:</b> {row['name']}\n\n"
                            "Endi u foydalanuvchilarga ko'rinmaydi. Davom ettirish uchun "
                            "<b>📢 E'lon joylashtirish</b> orqali qaytadan joylashtiring."
                        ),
                        parse_mode="HTML"
                    )
                except Exception:
                    pass

            expiring_soon = await db.get_service_ads_expiring_soon(days_before=3)
            for row in expiring_soon:
                try:
                    await bot.send_message(
                        chat_id=row["user_id"],
                        text=(
                            f"⏰ <b>E'loningiz muddati tez orada tugaydi:</b> {row['name']}\n\n"
                            "Uzluksiz ko'rinib turishi uchun muddat tugashidan oldin yangilab qo'ying."
                        ),
                        parse_mode="HTML"
                    )
                    await db.mark_service_ad_expiry_reminded(row["id"])
                except Exception:
                    pass
        except Exception as e:
            logging.error(f"Xizmat e'lonlari lifecycle workerida xatolik: {e}")


async def main():
    await db.init_db()

    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    # State/data 1 soatdan keyin avtomatik tozalanadi - foydalanuvchi jarayonni
    # tashlab ketsa, "osilib qolgan" holat keyingi safar chalkashlik keltirmaydi
    storage = RedisStorage.from_url(redis_url, state_ttl=3600, data_ttl=3600)

    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher(storage=storage)
    dp.include_router(router)
    dp.include_router(service_ad_router)

    await bot.delete_webhook(drop_pending_updates=True)

    asyncio.create_task(start_web_server())
    asyncio.create_task(daily_backup_worker(bot))
    asyncio.create_task(scheduled_notifications_worker(bot))
    asyncio.create_task(admin_payment_reminder_worker(bot))
    asyncio.create_task(service_ad_lifecycle_worker(bot))

    print("[+] PostgreSQL va Redis bilan yuqori unumdorlikdagi bot muvaffaqiyatli ishga tushdi!")

    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()
        await db.close_db()


if __name__ == "__main__":
    asyncio.run(main())
