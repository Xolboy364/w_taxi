import asyncio
import logging
import datetime
import os
from aiogram import Bot, Dispatcher
from aiogram.types import FSInputFile
from aiogram.fsm.storage.redis import RedisStorage
from config import BOT_TOKEN, ADMIN_ID
from handlers import router
import database as db

logging.basicConfig(level=logging.INFO)

# --- HAR 24 SOATDA AVTOMATIK ZAXIRA XABARI ---
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

# --- REJALASHTIRILGAN KUNLIK AVTO-XABARLAR (SCHEDULER) ---
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
            await asyncio.sleep(60)
        await asyncio.sleep(30)

async def main():
    await db.init_db()

    # Redis FSM Storage (Millionlab foydalanuvchilar uchun operativ xotirani boshqarish)
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    storage = RedisStorage.from_url(redis_url)

    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher(storage=storage)
    dp.include_router(router)

    await bot.delete_webhook(drop_pending_updates=True)

    asyncio.create_task(daily_backup_worker(bot))
    asyncio.create_task(scheduled_notifications_worker(bot))

    print("[+] PostgreSQL va Redis bilan yuqori unumdorlikdagi bot muvaffaqiyatli ishga tushdi!")

    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()
        await db.close_db()

if __name__ == "__main__":
    asyncio.run(main())
