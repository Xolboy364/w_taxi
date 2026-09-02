import re
import os
import time
import asyncio
import datetime
import logging
import tempfile
from urllib.parse import urlparse

from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, ReplyKeyboardRemove, FSInputFile, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import CommandStart, Command, StateFilter
from aiogram.fsm.context import FSMContext

from config import ADMIN_ID
from keyboards import (
    REGIONS_DATA, get_main_menu, get_super_admin_kb, sub_admin_kb,
    driver_type_kb, get_cars_kb, get_route_scope_kb,
    get_regions_kb, get_districts_kb, get_multi_districts_kb,
    phone_keyboard, get_driver_cabinet_kb, get_driver_card_kb,
    ban_management_kb, ban_duration_kb,
    kill_confirm_1_kb, kill_confirm_2_kb,
    start_confirm_1_kb, start_confirm_2_kb,
    monetization_start_1_kb, monetization_start_2_kb,
    monetization_stop_1_kb, monetization_stop_2_kb,
    get_close_order_kb, get_roadside_services_kb,
    get_fuel_types_kb, get_location_request_kb
)
from states import (
    DriverReg, DriverMultiRoute, DriverLocalRoute, PassengerSearch,
    PassengerOrderState, AdminManage, SuperAdminAuth,
    ChangePasswordState, ChangeCardState, BroadcastState, BanUserManage, DriverPaymentState, ServiceAdStates,
    RoadsideSearchState, AdminRejectState, ComplaintState
)

MAX_ORDERS_PER_HOUR = 3  # bitta foydalanuvchi 1 soatda nechta buyurtma bera oladi (spam nazorati)
import database as db

router = Router()
TEMP_SESSIONS = {}

# Admin login uchun brute-force himoyasi: {user_id: [timestamp, ...]}
LOGIN_ATTEMPTS = {}
MAX_LOGIN_ATTEMPTS = 5
LOGIN_WINDOW_SECONDS = 900  # 15 daqiqa
LOGIN_LOCKOUT_SECONDS = 900  # 15 daqiqa bloklash


def clean_phone(phone_raw: str) -> str | None:
    digits = re.sub(r"\D", "", phone_raw)
    if digits.startswith("998") and len(digits) == 12:
        return f"+{digits}"
    elif len(digits) == 9:
        return f"+998{digits}"
    return None


def is_super_admin(user_id: int) -> bool:
    if user_id == ADMIN_ID:
        return True
    if user_id in TEMP_SESSIONS:
        if time.time() - TEMP_SESSIONS[user_id] < 180:
            TEMP_SESSIONS[user_id] = time.time()
            return True
        else:
            del TEMP_SESSIONS[user_id]
    return False


def is_temp_admin_user(user_id: int) -> bool:
    return user_id in TEMP_SESSIONS and user_id != ADMIN_ID


def _check_login_lockout(user_id: int) -> tuple[bool, int]:
    """(bloklanganmi, qolgan_soniya) qaytaradi."""
    attempts = LOGIN_ATTEMPTS.get(user_id, [])
    now = time.time()
    attempts = [t for t in attempts if now - t < LOGIN_WINDOW_SECONDS]
    LOGIN_ATTEMPTS[user_id] = attempts
    if len(attempts) >= MAX_LOGIN_ATTEMPTS:
        oldest = min(attempts)
        remaining = int(LOGIN_LOCKOUT_SECONDS - (now - oldest))
        if remaining > 0:
            return True, remaining
    return False, 0


def _register_failed_login(user_id: int):
    LOGIN_ATTEMPTS.setdefault(user_id, []).append(time.time())


def _clear_login_attempts(user_id: int):
    LOGIN_ATTEMPTS.pop(user_id, None)


async def check_access(message_or_callback) -> bool:
    user_id = message_or_callback.from_user.id
    banned, reason = await db.is_user_banned(user_id)
    if banned:
        text = f"⛔️ <b>Sizning profilingiz bloklangan!</b>\nSabab: {reason}\n\nMa'lumot uchun admin bilan bog'laning."
        if isinstance(message_or_callback, Message):
            await message_or_callback.answer(text, parse_mode="HTML")
        else:
            await message_or_callback.message.answer(text, parse_mode="HTML")
        return False

    maint = await db.get_setting("maintenance_mode", "0")
    if maint == "1" and not is_super_admin(user_id):
        maint_text = (
            "🛠 <b>Botda yangilanish va texnik xizmat olib borilayapti.</b>\n\n"
            "Bot faoliyatida uzulish va to‘xtatilishlar kuzatilishi mumkin. Yangilanish bu yangi imkoniyatlar."
        )
        if isinstance(message_or_callback, Message):
            await message_or_callback.answer(maint_text, parse_mode="HTML")
        else:
            await message_or_callback.message.answer(maint_text, parse_mode="HTML")
        return False
    return True


async def render_user_menu(user_id: int):
    is_super = is_super_admin(user_id)
    is_sub = False
    if not is_super:
        is_sub = await db.is_admin(user_id, ADMIN_ID)
    return get_main_menu(is_super=is_super, is_sub=is_sub)


async def delayed_dispatch_to_free_drivers(bot: Bot, driver_ids: list, message_text: str, delay_seconds: int = 300):
    await asyncio.sleep(delay_seconds)
    for did in driver_ids:
        try:
            await bot.send_message(chat_id=did, text=message_text, parse_mode="HTML")
        except Exception:
            pass


@router.message(Command("admin_login"))
async def secret_admin_login(message: Message, state: FSMContext):
    await state.clear()
    locked, remaining = _check_login_lockout(message.from_user.id)
    if locked:
        minutes = max(1, remaining // 60)
        await message.answer(f"⛔️ Juda ko‘p noto‘g‘ri urinish. {minutes} daqiqadan so‘ng qayta urinib ko‘ring.")
        return
    await message.answer("🔑 <b>Super Admin maxfiy parolini kiriting:</b>", parse_mode="HTML")
    await state.set_state(SuperAdminAuth.enter_password)


@router.message(SuperAdminAuth.enter_password)
async def secret_admin_password_check(message: Message, state: FSMContext):
    user_id = message.from_user.id
    locked, remaining = _check_login_lockout(user_id)
    if locked:
        await state.clear()
        minutes = max(1, remaining // 60)
        await message.answer(f"⛔️ Juda ko‘p noto‘g‘ri urinish. {minutes} daqiqadan so‘ng qayta urinib ko‘ring.")
        return

    is_valid = await db.verify_super_admin_password(message.text.strip())

    # Kiritilgan parolni chatdan darhol o'chirishga urinib ko'ramiz (maxfiylik uchun)
    try:
        await message.delete()
    except Exception:
        pass

    if is_valid:
        _clear_login_attempts(user_id)
        TEMP_SESSIONS[user_id] = time.time()
        await state.clear()
        await db.log_activity(user_id, message.from_user.full_name or "Noma'lum", "TEMP_SUPER_ADMIN_LOGIN", "Begona qurilmadan kirildi", is_temp_admin=1)

        maint = (await db.get_setting("maintenance_mode", "0")) == "1"
        monet = (await db.get_setting("monetization_active", "0")) == "1"
        await message.answer(
            "👑 <b>Super Admin sessiyasi faollashtirildi!</b>\n\n⚠️ <i>3 daqiqa harakatsiz qolsangiz, sessiya yopiladi.</i>",
            reply_markup=get_super_admin_kb(maintenance_on=maint, monetization_on=monet, is_temp_session=True),
            parse_mode="HTML"
        )
    else:
        _register_failed_login(user_id)
        await state.clear()
        await message.answer("❌ Noto‘g‘ri parol!")


@router.message(F.text == "🔒 Sessiyani yopish (Chiqish)")
async def close_temp_session(message: Message, state: FSMContext):
    await state.clear()
    if message.from_user.id in TEMP_SESSIONS:
        del TEMP_SESSIONS[message.from_user.id]
    await db.log_activity(message.from_user.id, message.from_user.full_name or "", "TEMP_SUPER_ADMIN_LOGOUT", "Sessiya yopildi", is_temp_admin=1)
    menu = await render_user_menu(message.from_user.id)
    await message.answer("🔒 Sessiyangiz yopildi.", reply_markup=menu)


@router.message(CommandStart())
@router.message(F.text == "🔙 Bosh menyu")
async def cmd_start(message: Message, state: FSMContext):
    if not await check_access(message): return
    await state.clear()
    menu = await render_user_menu(message.from_user.id)
    greeting = "👑 Hurmatli Super Admin, xush kelibsiz!" if is_super_admin(message.from_user.id) else "Assalomu alaykum! Kerakli bo‘limni tanlang:"
    await message.answer(greeting, reply_markup=menu)


@router.message(F.text == "👑 Super Admin Panel")
async def super_admin_main(message: Message, state: FSMContext):
    if not is_super_admin(message.from_user.id): return
    await state.clear()
    maint = (await db.get_setting("maintenance_mode", "0")) == "1"
    monet = (await db.get_setting("monetization_active", "0")) == "1"
    is_temp = is_temp_admin_user(message.from_user.id)
    await message.answer("👑 Super Admin boshqaruv paneli:", reply_markup=get_super_admin_kb(maintenance_on=maint, monetization_on=monet, is_temp_session=is_temp))


@router.message(F.text == "🛠 Admin Panel")
async def sub_admin_main(message: Message, state: FSMContext):
    if not await check_access(message): return
    if not await db.is_admin(message.from_user.id, ADMIN_ID): return
    await state.clear()
    await message.answer("🛠 Admin boshqaruv paneli:", reply_markup=sub_admin_kb)


@router.message(F.text.startswith("📊 Bot"))
async def admin_stats(message: Message, state: FSMContext):
    if not await check_access(message): return
    if not (is_super_admin(message.from_user.id) or await db.is_admin(message.from_user.id, ADMIN_ID)): return
    await state.clear()
    stats = await db.get_stats()
    monet = (await db.get_setting("monetization_active", "0")) == "1"
    text = (
        "📊 <b>Bot Statistikasi:</b>\n\n"
        f"👥 Ro‘yxatdagi haydovchilar: <b>{stats['drivers']} ta</b>\n"
        f"🛣 Faol yo‘nalishlar: <b>{stats['routes']} ta</b>\n"
        f"🙋‍♂️ Buyurtmalar arxivi: <b>{stats['orders']} ta</b>\n"
        f"📝 Barcha audit loglari: <b>{stats['logs']} ta</b>\n"
        f"🛡 Tayinlangan adminlar: <b>{stats['admins']} ta</b>\n"
        f"⛔️ Qora ro‘yxatdagilar: <b>{stats['banned']} ta</b>\n"
        f"💎 Monetizatsiya holati: <b>{'Faol \U0001F7E2' if monet else 'O\'chiq \U0001F534'}</b>"
    )
    await message.answer(text, parse_mode="HTML")


@router.message(F.text == "💳 To‘lov kartasini sozlash", StateFilter("*"))
async def change_card_start(message: Message, state: FSMContext):
    if not is_super_admin(message.from_user.id): return
    await state.clear()
    curr_card = await db.get_setting("p2p_card_number", "8600123456789012")
    await message.answer(
        f"💳 <b>Hozirgi to‘lov qabul qiluvchi karta:</b>\n<code>{curr_card}</code>\n\n"
        "Yangi 16 xonali karta raqamini kiriting (Masalan: <code>8600123456789012</code>):",
        parse_mode="HTML"
    )
    await state.set_state(ChangeCardState.new_card_number)


@router.message(ChangeCardState.new_card_number)
async def change_card_save(message: Message, state: FSMContext):
    clean_card = re.sub(r"\D", "", message.text.strip())
    if len(clean_card) != 16:
        await message.answer("Karta raqami 16 ta raqamdan iborat bo‘lishi kerak. Qayta kiriting:")
        return
    await db.set_setting("p2p_card_number", clean_card)
    await db.log_activity(message.from_user.id, message.from_user.full_name, "ADMIN_CHANGE_CARD", f"Yangi karta: {clean_card}", is_temp_admin=int(is_temp_admin_user(message.from_user.id)))
    await state.clear()
    await message.answer(f"✅ <b>To‘lov kartasi yangilandi:</b>\n<code>{clean_card}</code>\n\nEndi barcha Click to‘lovlari shu kartaga yo‘naltiriladi.", parse_mode="HTML")


@router.message(F.text == "💎 Monetizatsiyani boshlash")
async def monetization_start_init(message: Message):
    if not is_super_admin(message.from_user.id): return
    await message.answer(
        "💎 <b>MONETIZATSIYANI BOSHLASH (1-BOSQICH):</b>\n\n"
        "Rostdan ham haydovchilar uchun oylik obuna (30 000 so‘m/oy) tizimini yoqmoqchimisiz?",
        reply_markup=monetization_start_1_kb,
        parse_mode="HTML"
    )


@router.callback_query(F.data == "mon_cancel")
async def mon_cancel_cb(callback: CallbackQuery):
    await callback.message.edit_text("Amal bekor qilindi.")


@router.callback_query(F.data == "mon_start_1_ok")
async def mon_start_1_cb(callback: CallbackQuery):
    if not is_super_admin(callback.from_user.id): return
    await callback.message.edit_text(
        "💎 <b>MONETIZATSIYANI BOSHLASH (2-BOSQICH QAT’IY TASDIQ):</b>\n\n"
        "Tugma bosilishi bilan barcha ro‘yxatdagi haydovchilarga obuna shartlari haqida avtomatik xabar yuboriladi va tizim pullik rejimga o‘tadi. Rozimisiz?",
        reply_markup=monetization_start_2_kb,
        parse_mode="HTML"
    )


@router.callback_query(F.data == "mon_start_2_confirm")
async def mon_start_2_cb(callback: CallbackQuery, bot: Bot):
    if not is_super_admin(callback.from_user.id): return
    await db.set_setting("monetization_active", "1")
    await db.log_activity(callback.from_user.id, callback.from_user.full_name, "MONETIZATION_TOGGLE", "Monetizatsiya ishga tushirildi", is_temp_admin=int(is_temp_admin_user(callback.from_user.id)))

    await callback.message.edit_text("💎 <b>Monetizatsiya muvaffaqiyatli yoqildi! Haydovchilarga 7 kunlik bepul muddat berilmoqda...</b>", parse_mode="HTML")

    # Barcha mavjud haydovchilarga darhol to'lov talab qilinmaydi - 7 kunlik bepul muhlat beriladi
    driver_ids = await db.grant_grace_days_to_all_drivers(days=7)

    driver_msg = (
        "🌟 <b>Hurmatli haydovchilar!</b>\n\n"
        "Botimizning sifatini oshirish, xizmatni yanada tezkor, barqaror va uzluksiz ishlashini ta’minlash hamda yo‘lovchilar bazasini kengaytirish maqsadida tizimimizda oylik obuna rejimi ishga tushirildi.\n\n"
        "Sizga <b>7 kunlik bepul muhlat</b> berildi. Shu muddat davomida kabinetingizdagi <b>[ 🌟 Tarif va Obuna ]</b> tugmasi orqali obunangizni faollashtirib qo‘yishingizni so‘raymiz.\n\n"
        "<i>Bizni tanlaganingiz uchun rahmat! Jamoamiz Sizga barakali qatnovlar tilaydi.</i>\n\n"
        "🔗 @w_taxi_bot"
    )

    for did in driver_ids:
        try:
            await bot.send_message(chat_id=did, text=driver_msg, parse_mode="HTML")
        except Exception:
            pass

    maint = (await db.get_setting("maintenance_mode", "0")) == "1"
    is_temp = is_temp_admin_user(callback.from_user.id)
    await callback.message.answer("✅ Barcha haydovchilar ogohlantirildi va monetizatsiya ishga tushdi.", reply_markup=get_super_admin_kb(maintenance_on=maint, monetization_on=True, is_temp_session=is_temp))


@router.message(F.text == "🛑 Monetizatsiyani to‘xtatish")
async def monetization_stop_init(message: Message):
    if not is_super_admin(message.from_user.id): return
    await message.answer(
        "🛑 <b>MONETIZATSIYANI TO‘XTATISH (1-BOSQICH):</b>\n\n"
        "Rostdan ham obuna tizimini to‘xtatib, barcha haydovchilar uchun botni vaqtincha bepul rejimga o‘tkazmoqchimisiz?",
        reply_markup=monetization_stop_1_kb,
        parse_mode="HTML"
    )


@router.callback_query(F.data == "mon_stop_1_ok")
async def mon_stop_1_cb(callback: CallbackQuery):
    if not is_super_admin(callback.from_user.id): return
    await callback.message.edit_text(
        "🛑 <b>MONETIZATSIYANI TO‘XTATISH (2-BOSQICH QAT’IY TASDIQ):</b>\n\n"
        "Obuna rejimi butunlay o‘chiriladi va barcha haydovchilar bepul xizmatdan foydalana boshlaydi. Tasdiqlaysizmi?",
        reply_markup=monetization_stop_2_kb,
        parse_mode="HTML"
    )


@router.callback_query(F.data == "mon_stop_2_confirm")
async def mon_stop_2_cb(callback: CallbackQuery, bot: Bot):
    if not is_super_admin(callback.from_user.id): return
    await db.set_setting("monetization_active", "0")
    await db.log_activity(callback.from_user.id, callback.from_user.full_name, "MONETIZATION_TOGGLE", "Monetizatsiya to'xtatildi", is_temp_admin=int(is_temp_admin_user(callback.from_user.id)))

    await callback.message.edit_text("🛑 <b>Monetizatsiya to‘xtatildi. Bot yana to‘liq bepul rejimga o‘tkazildi.</b>", parse_mode="HTML")

    maint = (await db.get_setting("maintenance_mode", "0")) == "1"
    is_temp = is_temp_admin_user(callback.from_user.id)
    await callback.message.answer("✅ Amal bajarildi.", reply_markup=get_super_admin_kb(maintenance_on=maint, monetization_on=False, is_temp_session=is_temp))


@router.message(F.text == "🌟 Tarif va Obuna")
async def driver_subscription_menu(message: Message, state: FSMContext):
    if not await check_access(message): return
    await state.clear()

    driver = await db.get_driver(message.from_user.id)
    if not driver:
        await message.answer("Siz haydovchi sifatida ro‘yxatdan o‘tmagansiz.")
        return

    is_sub = await db.is_driver_subscribed(message.from_user.id)
    card_num = await db.get_setting("p2p_card_number", "8600123456789012")
    amount = 30000

    click_url = f"https://my.click.uz/clickp2p/?recipient={card_num}&amount={amount}"
    sub_status_text = "🟢 <b>Faol (Obuna muddati yetarli)</b>" if is_sub else "🔴 <b>Muddati tugagan yoki to‘lanmagan</b>"

    text = (
        f"🌟 <b>Haydovchi obuna va tarif markazi</b>\n\n"
        f"📶 Sizning holatingiz: {sub_status_text}\n"
        f"💳 <b>Oylik obuna narxi:</b> 30 000 so‘m / 30 kun\n\n"
        f"To‘lovni amalga oshirish uchun quyidagi tugmani bosing va o‘tkazma qilingach, <b>to‘lov cheki (skrinshot)ni shu yerga rasm ko‘rinishida yuboring</b>:"
    )

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💳 Click orqali to‘lash (30 000 so‘m)", url=click_url)],
            [InlineKeyboardButton(text="📸 Chekni yuborish", callback_data="drv_send_receipt")]
        ]
    )
    await message.answer(text, reply_markup=kb, parse_mode="HTML")


@router.callback_query(F.data == "drv_send_receipt")
async def driver_send_receipt_callback(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer("Iltimos, amalga oshirilgan to‘lov chekining skrinshotini (rasmini) yuboring:")
    await state.set_state(DriverPaymentState.waiting_receipt)
    await callback.answer()


@router.message(DriverPaymentState.waiting_receipt, F.photo)
async def driver_receipt_received(message: Message, state: FSMContext, bot: Bot):
    photo_id = message.photo[-1].file_id
    await state.clear()

    # Har bir chek uchun alohida payment_id yaratamiz - shu orqali ikki marta tasdiqlash mumkin bo'lmaydi
    payment_id = await db.save_driver_payment(message.from_user.id, photo_id)

    await message.answer("✅ <b>Chekingiz adminga yuborildi!</b>\nAdminlar tekshirib chiqqach, obunangiz darhol faollashtiriladi.", parse_mode="HTML")

    admin_recipients = await db.get_backup_recipients(ADMIN_ID)
    approve_kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Obunani tasdiqlash (+30 kun)", callback_data=f"app_sub_{payment_id}")],
            [InlineKeyboardButton(text="❌ Rad etish", callback_data=f"rej_sub_{payment_id}")]
        ]
    )
    caption = (
        f"🔔 <b>Yangi to‘lov cheki tushdi!</b>\n\n"
        f"👤 Haydovchi: {message.from_user.full_name}\n"
        f"🆔 ID: <code>{message.from_user.id}</code>\n"
        f"📞 Username: @{message.from_user.username or 'yoq'}"
    )

    for aid in admin_recipients:
        try:
            await bot.send_photo(chat_id=aid, photo=photo_id, caption=caption, reply_markup=approve_kb, parse_mode="HTML")
        except Exception:
            pass


@router.callback_query(F.data.startswith("app_sub_"))
async def admin_approve_subscription(callback: CallbackQuery, bot: Bot):
    if not (is_super_admin(callback.from_user.id) or await db.is_admin(callback.from_user.id, ADMIN_ID)):
        await callback.answer("Huquqingiz yo‘q!", show_alert=True)
        return

    payment_id = int(callback.data.replace("app_sub_", ""))
    target_id = await db.approve_driver_payment(payment_id)

    if target_id is None:
        # Allaqachon tasdiqlangan (boshqa admin bosgan) - qayta ishlamaymiz
        await callback.answer("⚠️ Bu to‘lov allaqachon tasdiqlangan!", show_alert=True)
        try:
            await callback.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass
        return

    await db.log_activity(callback.from_user.id, callback.from_user.full_name, "APPROVE_PAYMENT", f"Haydovchiga 30 kun obuna berildi: {target_id}")

    try:
        await callback.message.edit_caption(caption=callback.message.caption + "\n\n✅ <b>TASDIQLANDI (+30 kun berildi)</b>", parse_mode="HTML")
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

    try:
        await bot.send_message(
            chat_id=target_id,
            text="🎉 <b>Tabriklaymiz! To‘lovingiz tasdiqlandi.</b>\nObunangiz yana 30 kunga uzaytirildi va barcha imkoniyatlar ochildi! 🚀\n\n🔗 @w_taxi_bot",
            parse_mode="HTML"
        )
    except Exception:
        pass

    await callback.answer("Obuna muvaffaqiyatli tasdiqlandi!")


@router.callback_query(F.data.startswith("rej_sub_"))
async def admin_reject_subscription_start(callback: CallbackQuery, state: FSMContext):
    if not (is_super_admin(callback.from_user.id) or await db.is_admin(callback.from_user.id, ADMIN_ID)):
        await callback.answer("Huquqingiz yo‘q!", show_alert=True)
        return
    payment_id = int(callback.data.replace("rej_sub_", ""))
    await state.update_data(reject_target_type="driver_payment", reject_target_id=payment_id, reject_msg_id=callback.message.message_id, reject_chat_id=callback.message.chat.id)
    await callback.message.answer("Rad etish sababini yozing (foydalanuvchiga shu matn yuboriladi):")
    await state.set_state(AdminRejectState.enter_reason)
    await callback.answer()


@router.message(AdminRejectState.enter_reason)
async def admin_reject_reason_submit(message: Message, state: FSMContext, bot: Bot):
    """
    Ikkala rad etish oqimi (haydovchi obunasi va xizmat e'loni) uchun yagona joy.
    Bu orqali handlers.py va service_ad.py bir xil state'ni bir-biridan
    "o'g'irlab" qolish muammosi oldini oladi.
    """
    data = await state.get_data()
    reason = message.text.strip()
    target_type = data.get("reject_target_type")

    if target_type == "driver_payment":
        payment_id = data["reject_target_id"]
        user_id = await db.reject_driver_payment(payment_id, reason)
        if user_id is None:
            await message.answer("⚠️ Bu to‘lov allaqachon ko‘rib chiqilgan.")
        else:
            await db.log_activity(message.from_user.id, message.from_user.full_name, "REJECT_PAYMENT", f"Haydovchi to'lovi rad etildi: {user_id}")
            try:
                await bot.edit_message_reply_markup(chat_id=data["reject_chat_id"], message_id=data["reject_msg_id"], reply_markup=None)
            except Exception:
                pass
            try:
                await bot.send_message(
                    chat_id=user_id,
                    text=f"❌ <b>To‘lovingiz rad etildi.</b>\n\nSabab: {reason}\n\nIltimos, to‘g‘ri chek bilan qaytadan urinib ko‘ring (🌟 Tarif va Obuna bo‘limi orqali).",
                    parse_mode="HTML"
                )
            except Exception:
                pass
            await message.answer("✅ Foydalanuvchiga rad etish sababi yuborildi.")

    elif target_type == "service_ad":
        ad_id = data["reject_target_id"]
        ad = await db.reject_service_ad_once(ad_id, reason)
        if ad is None:
            await message.answer("⚠️ Bu e'lon allaqachon ko‘rib chiqilgan.")
        else:
            try:
                await bot.edit_message_reply_markup(chat_id=data["reject_chat_id"], message_id=data["reject_msg_id"], reply_markup=None)
            except Exception:
                pass
            try:
                await bot.send_message(
                    chat_id=ad['user_id'],
                    text=f"❌ <b>E'loningiz bekor qilindi.</b>\n\nSabab: {reason}\n\nIltimos, to‘g‘irlab qaytadan yuborishingiz mumkin.\n\n🔗 @w_taxi_bot",
                    parse_mode="HTML"
                )
            except Exception:
                pass
            await message.answer("✅ Foydalanuvchiga rad etish sababi yuborildi.")

    await state.clear()


@router.callback_query(F.data.startswith("complain_"))
async def complain_start(callback: CallbackQuery, state: FSMContext):
    driver_id = int(callback.data.replace("complain_", ""))
    await state.update_data(complain_driver_id=driver_id)
    await callback.message.answer("⚠️ Shikoyatingiz matnini yozing (bu haydovchi va vaziyat haqida qisqacha yozing):")
    await state.set_state(ComplaintState.enter_text)
    await callback.answer()


@router.message(ComplaintState.enter_text)
async def complain_text_submit(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    driver_id = data.get("complain_driver_id")
    text = message.text.strip()

    await db.save_complaint(message.from_user.id, driver_id, text)
    await db.log_activity(message.from_user.id, message.from_user.full_name, "COMPLAINT", f"Haydovchi {driver_id} haqida shikoyat")
    await state.clear()
    await message.answer("✅ Shikoyatingiz qabul qilindi. Adminlar tez orada ko‘rib chiqadi.")

    admin_recipients = await db.get_backup_recipients(ADMIN_ID)
    notify_text = (
        f"⚠️ <b>Yangi shikoyat!</b>\n\n"
        f"👤 Shikoyatchi: {message.from_user.full_name} (ID: <code>{message.from_user.id}</code>)\n"
        f"🚘 Haydovchi ID: <code>{driver_id}</code>\n"
        f"📝 Matn: {text}"
    )
    for aid in admin_recipients:
        try:
            await bot.send_message(chat_id=aid, text=notify_text, parse_mode="HTML")
        except Exception:
            pass


@router.message(F.text == "🔑 Parolni o‘zgartirish", StateFilter("*"))
async def change_password_start(message: Message, state: FSMContext):
    if not is_super_admin(message.from_user.id): return
    await state.clear()
    await message.answer("Yangi Super Admin parolini yozing (kamida 4 ta belgi):")
    await state.set_state(ChangePasswordState.new_password)


@router.message(ChangePasswordState.new_password)
async def change_password_save(message: Message, state: FSMContext):
    new_p = message.text.strip()
    if len(new_p) < 4:
        await message.answer("Parol kamida 4 ta belgidan iborat bo‘lishi kerak.")
        return

    await db.set_super_admin_password(new_p)
    await db.log_activity(message.from_user.id, message.from_user.full_name, "ADMIN_CHANGE_PASSWORD", "Parol o'zgartirildi (hash holida saqlandi)", is_temp_admin=int(is_temp_admin_user(message.from_user.id)))
    await state.clear()

    # Xavfsizlik uchun yangi parol chatga qaytarilmaydi
    try:
        await message.delete()
    except Exception:
        pass
    await message.answer("✅ Yangi parol muvaffaqiyatli o‘rnatildi va xavfsiz saqlandi. Uni eslab qoling — u endi hech qayerda ko‘rsatilmaydi.")


@router.message(F.text.startswith("📝 Adminlar faoliyati"))
async def admin_audit_view(message: Message):
    if not is_super_admin(message.from_user.id): return
    logs = await db.get_recent_admin_logs(20)
    if not logs:
        await message.answer("Hozircha audit loglari yo‘q.")
        return

    text = "📝 <b>Oxirgi Adminlar Harakati Jurnali:</b>\n\n"
    for l in logs:
        temp_badge = "🔴 <b>[BEGONA QURILMA]</b> " if l['is_temp_admin'] else "🛡 "
        text += (
            f"{temp_badge}<b>{l['user_name']}</b> (ID: <code>{l['telegram_id']}</code>)\n"
            f"⚡️ Amal: <code>{l['action_type']}</code>\n"
            f"📄 Tafsilot: {l['details']}\n"
            f"📅 Vaqt: {l['created_at']}\n"
            f"━━━━━━━━━━━━━━━━━━\n"
        )
    await message.answer(text, parse_mode="HTML")


@router.message(F.text == "📢 Ommaviy xabar yuborish")
async def broadcast_start(message: Message, state: FSMContext):
    if not is_super_admin(message.from_user.id): return
    await message.answer("Barcha foydalanuvchilarga yubormoqchi bo‘lgan xabaringizni yozing:")
    await state.set_state(BroadcastState.message_content)


@router.message(BroadcastState.message_content)
async def broadcast_send(message: Message, state: FSMContext, bot: Bot):
    user_ids = await db.get_all_user_ids()
    await state.clear()
    await message.answer(f"⏳ Xabar {len(user_ids)} ta foydalanuvchiga tarqatilmoqda...")

    success = 0
    for uid in user_ids:
        try:
            await bot.copy_message(chat_id=uid, from_chat_id=message.chat.id, message_id=message.message_id)
            success += 1
            await asyncio.sleep(0.04)
        except Exception:
            pass
    await message.answer(f"✅ Xabar {success} ta foydalanuvchiga yetkazildi!")


@router.message(F.text == "🔴 Favqulodda to‘xtatish")
async def kill_switch_init(message: Message):
    if not is_super_admin(message.from_user.id): return
    await message.answer("⚠️ <b>1-BOSQICH OGOHLANTIRISH!</b>\n\nBot faoliyatini to‘xtatmoqchimisiz?", reply_markup=kill_confirm_1_kb, parse_mode="HTML")


@router.callback_query(F.data == "kill_cancel")
@router.callback_query(F.data == "start_cancel")
async def kill_cancel_cb(callback: CallbackQuery):
    await callback.message.edit_text("Amal bekor qilindi.")


@router.callback_query(F.data == "kill_step_1_ok")
async def kill_step_1_callback(callback: CallbackQuery):
    if not is_super_admin(callback.from_user.id): return
    await callback.message.edit_text("⚠️ <b>2-BOSQICH QAT’IY TASDIQLASH:</b>\n\nBot barcha foydalanuvchilar uchun yopiladi. Rozimisiz?", reply_markup=kill_confirm_2_kb, parse_mode="HTML")


@router.callback_query(F.data == "kill_step_2_confirm")
async def kill_step_2_callback(callback: CallbackQuery, bot: Bot):
    if not is_super_admin(callback.from_user.id): return
    await db.set_setting("maintenance_mode", "1")
    await db.log_activity(callback.from_user.id, callback.from_user.full_name, "KILL_SWITCH", "Bot to'xtatildi", is_temp_admin=int(is_temp_admin_user(callback.from_user.id)))

    await callback.message.edit_text("🔴 <b>Bot to‘xtatildi!</b>", parse_mode="HTML")
    maint_msg = (
        "🛠 <b>Botda yangilanish va texnik xizmat olib borilayapti.</b>\n\n"
        "Bot faoliyatida uzulish va to‘xtatilishlar kuzatilishi mumkin. Yangilanish bu yangi imkoniyatlar.\n\n"
        "🔗 @w_taxi_bot"
    )
    for uid in await db.get_all_user_ids():
        try:
            await bot.send_message(chat_id=uid, text=maint_msg, parse_mode="HTML")
            await asyncio.sleep(0.04)
        except Exception:
            pass
    maint = True
    monet = (await db.get_setting("monetization_active", "0")) == "1"
    is_temp = is_temp_admin_user(callback.from_user.id)
    await callback.message.answer("✅ Amal bajarildi.", reply_markup=get_super_admin_kb(maintenance_on=maint, monetization_on=monet, is_temp_session=is_temp))


@router.message(F.text == "🍏 Botni ishga tushirish (Start)")
async def start_switch_init(message: Message):
    if not is_super_admin(message.from_user.id): return
    await message.answer("🍏 <b>1-BOSQICH:</b> Botni qayta ishga tushirasizmi?", reply_markup=start_confirm_1_kb, parse_mode="HTML")


@router.callback_query(F.data == "start_step_1_ok")
async def start_step_1_callback(callback: CallbackQuery):
    if not is_super_admin(callback.from_user.id): return
    await callback.message.edit_text("🍏 <b>2-BOSQICH QAT’IY TASDIQLASH:</b>\n\nBot ochilsinmi?", reply_markup=start_confirm_2_kb, parse_mode="HTML")


@router.callback_query(F.data == "start_step_2_confirm")
async def start_step_2_callback(callback: CallbackQuery, bot: Bot):
    if not is_super_admin(callback.from_user.id): return
    await db.set_setting("maintenance_mode", "0")
    await db.log_activity(callback.from_user.id, callback.from_user.full_name, "START_SWITCH", "Bot ishga tushirildi", is_temp_admin=int(is_temp_admin_user(callback.from_user.id)))

    await callback.message.edit_text("🍏 <b>Bot qayta ishga tushirildi!</b>", parse_mode="HTML")

    welcome_back_msg = (
        "🎉 <b>Botimiz yana o‘z faoliyatiga to‘liq qaytdi!</b>\n\n"
        "Botimizda foydalanuvchilar soni ko‘payganligi sababli ba'zi o‘zgarishlarni kiritdik. "
        "Sizlar bizning botimizni sabr bilan kutib sodiq qolganingiz uchun jamoamiz nomidan rahmat aytamiz.\n\n"
        "🔗 @w_taxi_bot"
    )

    for uid in await db.get_all_user_ids():
        try:
            await bot.send_message(chat_id=uid, text=welcome_back_msg, parse_mode="HTML")
            await asyncio.sleep(0.04)
        except Exception:
            pass

    maint = False
    monet = (await db.get_setting("monetization_active", "0")) == "1"
    is_temp = is_temp_admin_user(callback.from_user.id)
    await callback.message.answer("✅ Bot faol holatda.", reply_markup=get_super_admin_kb(maintenance_on=maint, monetization_on=monet, is_temp_session=is_temp))


@router.message(F.text.startswith("🚫 Qora ro‘yxat"))
async def ban_menu(message: Message):
    if not (is_super_admin(message.from_user.id) or await db.is_admin(message.from_user.id, ADMIN_ID)): return
    await message.answer("Qora ro‘yxat boshqaruvi:", reply_markup=ban_management_kb)


@router.callback_query(F.data == "ban_action_block")
async def ban_user_start(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer("Bloklamoqchi bo‘lgan Telegram ID ni kiriting:")
    await state.set_state(BanUserManage.enter_user_id)
    await callback.answer()


@router.message(BanUserManage.enter_user_id)
async def ban_user_id_picked(message: Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("Faqat raqamli ID kiriting:")
        return
    await state.update_data(ban_target_id=int(message.text))
    await message.answer("Muddatni tanlang:", reply_markup=ban_duration_kb)
    await state.set_state(BanUserManage.enter_duration)


@router.callback_query(BanUserManage.enter_duration, F.data.startswith("bandur_"))
async def ban_duration_picked(callback: CallbackQuery, state: FSMContext):
    hours = int(callback.data.replace("bandur_", ""))
    await state.update_data(ban_hours=hours)
    await callback.message.edit_text("Sababini yozing:")
    await state.set_state(BanUserManage.enter_reason)


@router.message(BanUserManage.enter_reason)
async def ban_reason_submit(message: Message, state: FSMContext):
    data = await state.get_data()
    uid = data["ban_target_id"]
    hours = data["ban_hours"]
    reason = message.text.strip()
    await db.ban_user(uid, reason, duration_hours=(hours if hours > 0 else None))
    await db.log_activity(message.from_user.id, message.from_user.full_name, "BAN_USER", f"Bloklandi: {uid}", is_temp_admin=int(is_temp_admin_user(message.from_user.id)))
    await state.clear()
    await message.answer(f"⛔️ ID: <code>{uid}</code> bloklandi.", parse_mode="HTML")


@router.callback_query(F.data == "ban_action_unblock")
async def unban_user_start(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer("Blokdan chiqarish uchun Telegram ID ni kiriting:")
    await state.set_state(BanUserManage.unban_user_id)
    await callback.answer()


@router.message(BanUserManage.unban_user_id)
async def unban_user_submit(message: Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("Faqat raqamli ID kiriting:")
        return
    uid = int(message.text)
    await db.unban_user(uid)
    await db.log_activity(message.from_user.id, message.from_user.full_name, "UNBAN_USER", f"Blokdan chiqarildi: {uid}", is_temp_admin=int(is_temp_admin_user(message.from_user.id)))
    await state.clear()
    await message.answer(f"✅ ID: <code>{uid}</code> blokdan chiqarildi.", parse_mode="HTML")


@router.message(F.text.startswith("➕ Yangi Admin"))
async def admin_add_start(message: Message, state: FSMContext):
    if not is_super_admin(message.from_user.id): return
    await state.clear()
    await message.answer("Yangi adminning Telegram ID raqamini kiriting:")
    await state.set_state(AdminManage.add_admin_id)


@router.message(AdminManage.add_admin_id)
async def admin_add_id_input(message: Message, state: FSMContext):
    if not message.text or not message.text.isdigit():
        await message.answer("Faqat raqamli ID kiriting:")
        return
    await state.update_data(new_admin_id=int(message.text))
    await message.answer("Admin uchun ism yozing:")
    await state.set_state(AdminManage.add_admin_name)


@router.message(AdminManage.add_admin_name)
async def admin_add_save(message: Message, state: FSMContext):
    data = await state.get_data()
    await db.add_admin(data['new_admin_id'], message.text.strip(), message.from_user.id)
    await db.log_activity(message.from_user.id, message.from_user.full_name, "ADD_ADMIN", f"Admin qo'shildi: {data['new_admin_id']}", is_temp_admin=int(is_temp_admin_user(message.from_user.id)))
    await state.clear()
    await message.answer(f"✅ Yangi admin qo'shildi.")


@router.message(F.text.startswith("📋 Adminlar"))
async def admin_list_show(message: Message, state: FSMContext):
    if not is_super_admin(message.from_user.id): return
    await state.clear()
    admins = await db.get_all_admins()
    if not admins:
        await message.answer("Adminlar yo‘q.")
        return
    text = "📋 <b>Adminlar:</b>\n\n"
    for a in admins:
        text += f"👤 {a['full_name']} (ID: <code>{a['telegram_id']}</code>)\n"
    await message.answer(text, parse_mode="HTML")


@router.message(F.text.startswith("➖ Adminni"))
async def admin_remove_start(message: Message, state: FSMContext):
    if not is_super_admin(message.from_user.id): return
    await state.clear()
    await message.answer("O‘chiriladigan admin ID sini kiriting:")
    await state.set_state(AdminManage.remove_admin_id)


@router.message(AdminManage.remove_admin_id)
async def admin_remove_process(message: Message, state: FSMContext):
    if not message.text or not message.text.isdigit():
        await message.answer("Faqat raqamli ID kiriting:")
        return
    tid = int(message.text.strip())
    await db.remove_admin(tid)
    await db.log_activity(message.from_user.id, message.from_user.full_name, "REMOVE_ADMIN", f"Admin o'chirildi: {tid}", is_temp_admin=int(is_temp_admin_user(message.from_user.id)))
    await state.clear()
    await message.answer(f"✅ Admin o‘chirildi.")


@router.message(F.text.startswith("💾 Baza"))
async def admin_manual_backup(message: Message, state: FSMContext):
    """
    PostgreSQL uchun to'g'ri zaxira: pg_dump orqali .sql fayl yaratiladi.
    (Avvalgi versiyada SQLite davridan qolgan db.DB_NAME ishlatilgan edi -
    bu PostgreSQL bilan ishlamas edi va xatolik berardi.)
    """
    if not (is_super_admin(message.from_user.id) or await db.is_admin(message.from_user.id, ADMIN_ID)): return
    await state.clear()

    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        await message.answer("⚠️ DATABASE_URL topilmadi, zaxira yaratib bo‘lmadi.")
        return

    await message.answer("⏳ Zaxira tayyorlanmoqda, biroz kuting...")

    parsed = urlparse(database_url)
    env = os.environ.copy()
    if parsed.password:
        env["PGPASSWORD"] = parsed.password

    with tempfile.NamedTemporaryFile(suffix=".sql", delete=False) as tmp:
        tmp_path = tmp.name

    cmd = [
        "pg_dump",
        "-h", parsed.hostname or "localhost",
        "-p", str(parsed.port or 5432),
        "-U", parsed.username or "postgres",
        "-d", (parsed.path or "/postgres").lstrip("/"),
        "-f", tmp_path,
        "--no-owner",
        "--no-privileges",
    ]

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd, env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        _, stderr = await proc.communicate()

        if proc.returncode != 0 or not os.path.exists(tmp_path) or os.path.getsize(tmp_path) == 0:
            logging.error(f"pg_dump xatosi: {stderr.decode(errors='ignore')}")
            await message.answer("❌ Zaxira yaratishda xatolik yuz berdi. pg_dump o‘rnatilganligini tekshiring.")
            return

        filename = f"backup_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.sql"
        await message.answer_document(document=FSInputFile(tmp_path, filename=filename))
    except FileNotFoundError:
        await message.answer("❌ pg_dump topilmadi. Server(container)da PostgreSQL client vositalari o‘rnatilganligiga ishonch hosil qiling.")
    except Exception as e:
        logging.error(f"Zaxira yaratishda xatolik: {e}")
        await message.answer("❌ Zaxira yaratishda kutilmagan xatolik yuz berdi.")
    finally:
        try:
            os.remove(tmp_path)
        except Exception:
            pass


@router.message(F.text.startswith("👥 Haydovchilar"))
async def admin_drivers_list(message: Message, state: FSMContext):
    if not (is_super_admin(message.from_user.id) or await db.is_admin(message.from_user.id, ADMIN_ID)): return
    await state.clear()
    drivers = await db.get_all_drivers()
    if not drivers:
        await message.answer("Haydovchilar yo‘q.")
        return
    text = "📋 <b>Haydovchilar:</b>\n\n"
    for d in drivers:
        sub_ok = "🟢 VIP Obuna" if await db.is_driver_subscribed(d['telegram_id']) else "⚪️ Bepul"
        text += f"👤 {d['full_name']} | <code>{d['telegram_id']}</code> | {sub_ok}\n"
    await message.answer(text, parse_mode="HTML")


@router.message(F.text == "🗺 Yo‘l bo‘yi xizmatlari")
async def roadside_services_menu(message: Message, state: FSMContext):
    if not await check_access(message): return
    await state.clear()
    await message.answer(
        "🗺 <b>Yo‘l bo‘yi xizmatlari markazi</b>\n\n"
        "O‘zingizga kerakli xizmat turini tanlang:",
        reply_markup=get_roadside_services_kb(),
        parse_mode="HTML"
    )


async def render_roadside_results(message: Message, user_id: int, services):
    if not services:
        await message.answer("😔 Afsuski, yaqin atrofdan bunday xizmat topilmadi.", reply_markup=await render_user_menu(user_id))
        return

    response_text = f"📍 <b>Sizga eng yaqin topilgan {len(services)} ta xizmat:</b>\n\n"

    for i, s in enumerate(services, 1):
        dist = round(s["distance"], 1)
        maps_url = f"https://maps.google.com/?q={s['latitude']},{s['longitude']}"

        response_text += (
            f"<b>{i}. {s['name']}</b>\n"
            f"📏 Masofa: <b>~{dist} km</b> | 📞 Tel: {s['phone'] or 'Yo‘q'}\n"
            f"📝 Izoh: {s['description'] or '-'}\n"
            f"🗺 <a href='{maps_url}'>Yo‘lni ko‘rsatish (Google Maps)</a>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
        )

    await message.answer(response_text, reply_markup=await render_user_menu(user_id), parse_mode="HTML", disable_web_page_preview=True)


# Endi "🚗 Avtosalon" ham shu ro'yxatga qo'shildi
@router.message(F.location, F.text.in_(["🍽 Ovqatlanish", "🛏 Hostel va Mehmonxona", "🔧 Avtoservis", "🚗 Avtosalon"]))
async def process_roadside_service_search(message: Message):
    try:
        await message.delete()
    except Exception:
        pass

    text_map = {
        "🍽 Ovqatlanish": "food",
        "🛏 Hostel va Mehmonxona": "hotel",
        "🔧 Avtoservis": "service",
        "🚗 Avtosalon": "autosalon"
    }
    stype = text_map.get(message.text)
    if not stype:
        return

    user_lat = message.location.latitude
    user_lon = message.location.longitude

    services = await db.get_nearest_services(user_lat, user_lon, stype, limit=10)
    await render_roadside_results(message, message.from_user.id, services)


@router.message(F.text == "⛽️ Zapravka")
async def roadside_gas_start(message: Message, state: FSMContext):
    if not await check_access(message): return
    await state.clear()
    await message.answer(
        "⛽️ <b>Qanday yoqilg'i turi kerak?</b>",
        reply_markup=get_fuel_types_kb([], "sfuel", multi=False),
        parse_mode="HTML"
    )


@router.callback_query(F.data == "sfuel_back")
async def roadside_gas_back(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    try:
        await callback.message.delete()
    except Exception:
        pass
    await callback.message.answer(
        "🗺 <b>Yo‘l bo‘yi xizmatlari markazi</b>\n\nO‘zingizga kerakli xizmat turini tanlang:",
        reply_markup=get_roadside_services_kb(),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data.startswith("sfuel_pick_"))
async def roadside_gas_fuel_picked(callback: CallbackQuery, state: FSMContext):
    fuel_key = callback.data.replace("sfuel_pick_", "")
    await state.update_data(roadside_fuel=fuel_key)
    await state.set_state(RoadsideSearchState.waiting_location)
    try:
        await callback.message.delete()
    except Exception:
        pass
    await callback.message.answer(
        "📍 Iltimos, joylashuvingizni yuboring:",
        reply_markup=get_location_request_kb()
    )
    await callback.answer()


@router.message(RoadsideSearchState.waiting_location, F.location)
async def process_gas_location_search(message: Message, state: FSMContext):
    try:
        await message.delete()
    except Exception:
        pass

    data = await state.get_data()
    fuel_key = data.get("roadside_fuel")
    await state.clear()

    user_lat = message.location.latitude
    user_lon = message.location.longitude

    services = await db.get_nearest_services(user_lat, user_lon, "gas", limit=10, fuel_type=fuel_key)
    await render_roadside_results(message, message.from_user.id, services)


@router.message(F.text == "🚗 Haydovchi")
async def driver_start(message: Message, state: FSMContext):
    if not await check_access(message): return
    await state.clear()
    driver = await db.get_driver(message.from_user.id)
    if driver:
        is_sub = await db.is_driver_subscribed(message.from_user.id)
        count = await db.get_driver_routes_count(message.from_user.id)
        status_text = "🟢 Mijoz kutmoqda (Bo‘sh)" if driver['status'] == 'waiting' else "🟡 Yo‘lda (Harakatda)"
        vip_text = "🌟 <b>VIP Obunachi</b>" if is_sub else "⚪️ <b>Standart (Bepul)</b>"

        await message.answer(
            f"👤 Haydovchi: <b>{driver['full_name']}</b>\n"
            f"🚘 Avtomobil: <b>{driver['car_model']}</b> ({driver['car_number']})\n"
            f"📶 Holat: <b>{status_text}</b>\n"
            f"💎 Tarif: {vip_text}\n"
            f"🛣 Faol yo‘nalishlar: <b>{count} ta</b>",
            reply_markup=get_driver_cabinet_kb(driver['status'], is_subscribed=is_sub),
            parse_mode="HTML"
        )
    else:
        await message.answer("Haydovchi sifatida ro‘yxatdan o‘tish.\nXizmat turini tanlang:", reply_markup=driver_type_kb)
        await state.set_state(DriverReg.service_type)


@router.callback_query(F.data.startswith("drvtype_"))
async def process_service_type(callback: CallbackQuery, state: FSMContext):
    stype = callback.data.split("_")[1]
    await state.update_data(service_type=stype)
    await callback.message.edit_text("Avtomobilingiz modelini tanlang:", reply_markup=get_cars_kb(stype))
    await state.set_state(DriverReg.car_model)


@router.callback_query(F.data.startswith("car_"))
async def process_car_choice(callback: CallbackQuery, state: FSMContext):
    car = callback.data.split("_", 1)[1]
    if car == "other":
        await callback.message.answer("Avtomobil modelini yozing:")
        return
    await state.update_data(car_model=car)
    await callback.message.delete()
    await callback.message.answer("Avtomobil davlat raqamini kiriting:")
    await state.set_state(DriverReg.car_number)


@router.message(DriverReg.car_model)
async def process_car_custom(message: Message, state: FSMContext):
    await state.update_data(car_model=message.text.strip())
    await message.answer("Avtomobil davlat raqamini kiriting:")
    await state.set_state(DriverReg.car_number)


@router.message(DriverReg.car_number)
async def process_car_number(message: Message, state: FSMContext):
    await state.update_data(car_number=message.text.strip().upper())
    await message.answer("Telefon raqamingizni yuboring:", reply_markup=phone_keyboard)
    await state.set_state(DriverReg.phone)


@router.message(DriverReg.phone, F.contact)
async def process_phone_contact(message: Message, state: FSMContext):
    phone = message.contact.phone_number
    phone = f"+{phone}" if not phone.startswith("+") else phone
    await state.update_data(phone=phone)
    await db.save_user_phone(message.from_user.id, message.from_user.full_name, phone)
    await message.answer("Rasmingizni yuboring:", reply_markup=ReplyKeyboardRemove())
    await state.set_state(DriverReg.photo)


@router.message(DriverReg.phone, F.text)
async def process_phone_text(message: Message, state: FSMContext):
    clean = clean_phone(message.text)
    if not clean:
        await message.answer("Telefon raqam noto‘g‘ri:")
        return
    await state.update_data(phone=clean)
    await db.save_user_phone(message.from_user.id, message.from_user.full_name, clean)
    await message.answer("Rasmingizni yuboring:", reply_markup=ReplyKeyboardRemove())
    await state.set_state(DriverReg.photo)


@router.message(DriverReg.photo, F.photo)
async def process_photo(message: Message, state: FSMContext):
    photo_id = message.photo[-1].file_id
    data = await state.get_data()
    data["telegram_id"] = message.from_user.id
    data["full_name"] = message.from_user.full_name
    data["photo_id"] = photo_id

    await db.save_driver(data)
    await db.extend_driver_subscription(message.from_user.id, days=30)
    await db.log_activity(message.from_user.id, message.from_user.full_name, "DRIVER_REGISTER", f"{data['car_model']}")
    await state.clear()
    await message.answer("✅ Ro‘yxatdan o‘tdingiz! Dastlabki 30 kun VIP obuna sovg‘a qilindi.", reply_markup=get_driver_cabinet_kb('waiting', is_subscribed=True))


@router.message(F.text == "🛣 Yangi marshrut sozlash")
async def driver_pick_scope(message: Message, state: FSMContext):
    if not await check_access(message): return
    await state.clear()

    monetization_on = (await db.get_setting("monetization_active", "0")) == "1"
    if monetization_on and not await db.is_driver_subscribed(message.from_user.id):
        current_count = await db.get_driver_routes_count(message.from_user.id)
        await message.answer(
            f"ℹ️ Siz hozir <b>bepul tarifda</b>siz — maksimal {db.FREE_DRIVER_ROUTE_LIMIT} ta marshrutga ruxsat bor "
            f"(hozir: {current_count} ta). Cheksiz marshrut uchun 🌟 Tarif va Obuna orqali VIP bo‘lishingiz mumkin.",
            parse_mode="HTML"
        )

    await message.answer("Qatnov turini tanlang:", reply_markup=get_route_scope_kb("drv_scope"))


@router.callback_query(F.data == "drv_scope_type_local")
async def drv_local_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(DriverLocalRoute.pick_region)
    await callback.message.edit_text("Qaysi viloyat ichida qatnaysiz?", reply_markup=get_regions_kb("drv_locreg"))


@router.callback_query(DriverLocalRoute.pick_region, F.data.startswith("drv_locreg_reg_"))
async def drv_local_region_picked(callback: CallbackQuery, state: FSMContext):
    region = callback.data.replace("drv_locreg_reg_", "")
    if region == "Toshkent shahri":
        await callback.answer("⚠️ Toshkent shahri ichida lokal qatnov mavjud emas!", show_alert=True)
        return
    await state.update_data(local_region=region)
    await state.set_state(DriverLocalRoute.pick_from_district)
    await callback.message.edit_text(f"[{region}] — Qaysi tumandan yo‘lga chiqasiz?", reply_markup=get_districts_kb(region, "drv_lfrom"))


@router.callback_query(DriverLocalRoute.pick_from_district, F.data.startswith("drv_lfrom_dist_"))
async def drv_local_from_picked(callback: CallbackQuery, state: FSMContext):
    dist = callback.data.replace("drv_lfrom_dist_", "")
    data = await state.get_data()
    region = data['local_region']
    await state.update_data(from_dist=dist)
    await state.set_state(DriverLocalRoute.pick_to_district)
    await callback.message.edit_text(f"[{region}] — Qaysi tumanga borasiz?", reply_markup=get_districts_kb(region, "drv_lto"))


@router.callback_query(DriverLocalRoute.pick_to_district, F.data.startswith("drv_lto_dist_"))
async def drv_local_to_picked(callback: CallbackQuery, state: FSMContext):
    to_dist = callback.data.replace("drv_lto_dist_", "")
    data = await state.get_data()
    region = data['local_region']
    from_dist = data.get('from_dist')

    if from_dist == to_dist:
        await callback.answer("⚠️ Chiqish tumani va borish tumani bir xil bo‘lishi mumkin emas!", show_alert=True)
        return

    allowed, limit = await db.can_add_more_routes(callback.from_user.id, 1)
    if not allowed:
        await callback.answer(
            f"⚠️ Bepul tarifda maksimal {limit} ta marshrut ruxsat etilgan. "
            f"Ko'proq marshrut qo'shish uchun 🌟 Tarif va Obuna orqali VIP bo'ling!",
            show_alert=True
        )
        return

    from_loc = f"{region}, {from_dist}"
    to_loc = f"{region}, {to_dist}"

    await db.add_driver_single_route(callback.from_user.id, from_loc, to_loc, route_category='local')
    await state.clear()
    await callback.message.delete()
    is_sub = await db.is_driver_subscribed(callback.from_user.id)
    await callback.message.answer(
        f"✅ Lokal yo‘nalish faollashtirildi!\n📍 {from_loc} ➡️ {to_loc}",
        reply_markup=get_driver_cabinet_kb('waiting', is_subscribed=is_sub)
    )


@router.callback_query(F.data == "drv_scope_type_intercity")
async def drv_inter_start(callback: CallbackQuery, state: FSMContext):
    await state.update_data(from_list=[], to_list=[], cur_region=None)
    await state.set_state(DriverMultiRoute.selecting_from)
    await callback.message.edit_text("📍 Odam oladigan viloyatlarni belgilang:", reply_markup=get_regions_kb("mfrom", []))


@router.callback_query(DriverMultiRoute.selecting_from, F.data.startswith("mfrom_reg_"))
async def mfrom_reg(callback: CallbackQuery, state: FSMContext):
    region = callback.data.replace("mfrom_reg_", "")
    if region == "Toshkent shahri":
        fl = ["Toshkent shahri"]
        await state.update_data(from_list=fl)
        await state.set_state(DriverMultiRoute.selecting_to)
        await callback.message.edit_text("🏁 Boradigan viloyatlarni tanlang:", reply_markup=get_regions_kb("mto", []))
        await callback.answer()
        return
    await state.update_data(cur_region=region)
    data = await state.get_data()
    await callback.message.edit_text(f"[{region}] — Tumanlarni bosing:", reply_markup=get_multi_districts_kb(region, data.get("from_list", []), "mfrom"))


@router.callback_query(DriverMultiRoute.selecting_from, F.data.startswith("mfrom_tog_"))
async def mfrom_toggle(callback: CallbackQuery, state: FSMContext):
    dist = callback.data.replace("mfrom_tog_", "")
    data = await state.get_data()
    reg = data.get("cur_region")
    loc = f"{reg}, {dist}"
    fl = data.get("from_list", [])
    if loc in fl: fl.remove(loc)
    else: fl.append(loc)
    await state.update_data(from_list=fl)
    await callback.message.edit_reply_markup(reply_markup=get_multi_districts_kb(reg, fl, "mfrom"))
    await callback.answer()


@router.callback_query(DriverMultiRoute.selecting_from, F.data == "mfrom_all")
async def mfrom_toggle_all(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    reg = data.get("cur_region")
    dists = REGIONS_DATA.get(reg, [])
    fl = data.get("from_list", [])
    all_in = all(f"{reg}, {d}" in fl for d in dists)
    for d in dists:
        l = f"{reg}, {d}"
        if all_in and l in fl: fl.remove(l)
        elif not all_in and l not in fl: fl.append(l)
    await state.update_data(from_list=fl)
    await callback.message.edit_reply_markup(reply_markup=get_multi_districts_kb(reg, fl, "mfrom"))
    await callback.answer()


@router.callback_query(DriverMultiRoute.selecting_from, F.data == "mfrom_back_reg")
async def mfrom_back(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    await callback.message.edit_text("📍 Chiqish viloyatini tanlang:", reply_markup=get_regions_kb("mfrom", data.get("from_list", [])))


@router.callback_query(DriverMultiRoute.selecting_from, F.data == "mfrom_done")
async def mfrom_done(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    if not data.get("from_list"):
        await callback.answer("Kamida 1 ta tuman yoki Toshkent shahrini tanlang!", show_alert=True)
        return
    await state.set_state(DriverMultiRoute.selecting_to)
    await callback.message.edit_text("🏁 Boradigan viloyatlarni tanlang:", reply_markup=get_regions_kb("mto", data.get("to_list", [])))


@router.callback_query(DriverMultiRoute.selecting_to, F.data.startswith("mto_reg_"))
async def mto_reg(callback: CallbackQuery, state: FSMContext):
    region = callback.data.replace("mto_reg_", "")
    if region == "Toshkent shahri":
        data = await state.get_data()
        fl = data.get("from_list", [])
        if "Toshkent shahri" in fl:
            await callback.answer("⚠️ Chiqish manzili va borish manzili bir xil bo‘lishi mumkin emas!", show_alert=True)
            return
        tl = ["Toshkent shahri"]
        allowed, limit = await db.can_add_more_routes(callback.from_user.id, len(fl) * len(tl))
        if not allowed:
            await callback.answer(
                f"⚠️ Bepul tarifda maksimal {limit} ta marshrut ruxsat etilgan. "
                f"Ko'proq marshrut qo'shish uchun 🌟 Tarif va Obuna orqali VIP bo'ling!",
                show_alert=True
            )
            return
        await db.add_driver_multi_routes(callback.from_user.id, fl, tl, route_category='intercity')
        await state.clear()
        await callback.message.delete()
        is_sub = await db.is_driver_subscribed(callback.from_user.id)
        await callback.message.answer(
            f"✅ Marshrutlar saqlandi! ({len(fl)*len(tl)} ta bog‘lanma)",
            reply_markup=get_driver_cabinet_kb('waiting', is_subscribed=is_sub)
        )
        return

    await state.update_data(cur_region=region)
    data = await state.get_data()
    await callback.message.edit_text(f"[{region}] — Boradigan tumanlarni belgilang:", reply_markup=get_multi_districts_kb(region, data.get("to_list", []), "mto"))


@router.callback_query(DriverMultiRoute.selecting_to, F.data.startswith("mto_tog_"))
async def mto_toggle(callback: CallbackQuery, state: FSMContext):
    dist = callback.data.replace("mto_tog_", "")
    data = await state.get_data()
    reg = data.get("cur_region")
    loc = f"{reg}, {dist}"
    tl = data.get("to_list", [])
    if loc in tl: tl.remove(loc)
    else: tl.append(loc)
    await state.update_data(to_list=tl)
    await callback.message.edit_reply_markup(reply_markup=get_multi_districts_kb(reg, tl, "mto"))
    await callback.answer()


@router.callback_query(DriverMultiRoute.selecting_to, F.data == "mto_all")
async def mto_toggle_all(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    reg = data.get("cur_region")
    dists = REGIONS_DATA.get(reg, [])
    tl = data.get("to_list", [])
    valid_dists = [f"{reg}, {d}" for d in dists]
    all_in = all(l in tl for l in valid_dists)
    for l in valid_dists:
        if all_in and l in tl: tl.remove(l)
        elif not all_in and l not in tl: tl.append(l)
    await state.update_data(to_list=tl)
    await callback.message.edit_reply_markup(reply_markup=get_multi_districts_kb(reg, tl, "mto"))
    await callback.answer()


@router.callback_query(DriverMultiRoute.selecting_to, F.data == "mto_back_reg")
async def mto_back(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    await callback.message.edit_text("🏁 Boradigan viloyatni tanlang:", reply_markup=get_regions_kb("mto", data.get("to_list", [])))


@router.callback_query(DriverMultiRoute.selecting_to, F.data == "mto_done")
async def mto_finish(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    fl, tl = data.get("from_list", []), data.get("to_list", [])
    if not tl:
        await callback.answer("Kamida 1 ta borish tumani yoki Toshkent shahrini tanlang!", show_alert=True)
        return

    valid_tl = [t for t in tl if t not in fl]
    if not valid_tl:
        await callback.answer("⚠️ Chiqish va borish manzillari bir xil bo‘lishi mumkin emas!", show_alert=True)
        return

    new_routes_count = len(fl) * len(valid_tl)
    allowed, limit = await db.can_add_more_routes(callback.from_user.id, new_routes_count)
    if not allowed:
        await callback.answer(
            f"⚠️ Bepul tarifda maksimal {limit} ta marshrut ruxsat etilgan. "
            f"Ko'proq marshrut qo'shish uchun 🌟 Tarif va Obuna orqali VIP bo'ling!",
            show_alert=True
        )
        return

    await db.add_driver_multi_routes(callback.from_user.id, fl, valid_tl, route_category='intercity')
    await state.clear()
    await callback.message.delete()
    is_sub = await db.is_driver_subscribed(callback.from_user.id)
    await callback.message.answer(
        f"✅ Marshrutlar saqlandi! ({len(fl)*len(valid_tl)} ta bog‘lanma)",
        reply_markup=get_driver_cabinet_kb('waiting', is_subscribed=is_sub)
    )


@router.message(F.text == "🚀 Yo‘lga chiqdim")
async def driver_set_on_way(message: Message, state: FSMContext):
    if not await check_access(message): return
    await state.clear()
    await db.set_driver_status(message.from_user.id, 'on_way')
    is_sub = await db.is_driver_subscribed(message.from_user.id)
    await message.answer("🚀 Qatnov boshlandi.", reply_markup=get_driver_cabinet_kb('on_way', is_subscribed=is_sub))


@router.message(F.text == "🟢 Mijoz kutmoqdaman")
async def driver_set_waiting(message: Message, state: FSMContext):
    if not await check_access(message): return
    await state.clear()
    await db.set_driver_status(message.from_user.id, 'waiting')
    is_sub = await db.is_driver_subscribed(message.from_user.id)
    await message.answer("🟢 Faol qidiruvdasiz.", reply_markup=get_driver_cabinet_kb('waiting', is_subscribed=is_sub))


@router.message(F.text == "📋 Yo‘lovchilar ro‘yxati")
async def driver_view_passengers(message: Message, state: FSMContext):
    if not await check_access(message): return
    await state.clear()
    orders = await db.get_passenger_orders_for_driver(message.from_user.id)
    is_sub = await db.is_driver_subscribed(message.from_user.id)
    if not orders:
        await message.answer("Hozirda buyurtmalar yo‘q.", reply_markup=get_driver_cabinet_kb('waiting', is_subscribed=is_sub))
        return
    text = "📋 <b>Buyurtmalar:</b>\n\n"
    for o in orders:
        text += f"👤 {o['full_name']} | 📍 {o['from_loc']} ➡️ {o['to_loc']} | 📞 {o['phone']}\n"
    await message.answer(text, reply_markup=get_driver_cabinet_kb('waiting', is_subscribed=is_sub), parse_mode="HTML")


@router.message(F.text == "🗑 Yo‘nalishlarni tozalash")
async def driver_clear_routes(message: Message, state: FSMContext):
    if not await check_access(message): return
    await state.clear()
    await db.clear_driver_routes(message.from_user.id)
    is_sub = await db.is_driver_subscribed(message.from_user.id)
    await message.answer("✅ Yo‘nalishlar tozalandi.", reply_markup=get_driver_cabinet_kb('waiting', is_subscribed=is_sub))


@router.message(F.text.in_(["🙋‍♂️ Yo‘lovchi", "📦 Pochta berish", "🚚 Yuk yuborish"]))
async def psg_start(message: Message, state: FSMContext):
    if not await check_access(message): return
    await state.clear()
    service_type = "cargo" if message.text in ["📦 Pochta berish", "🚚 Yuk yuborish"] else "passenger"
    await state.update_data(req_service=service_type)
    await message.answer("Safar ko‘lamini tanlang:", reply_markup=get_route_scope_kb("psg_scope"))


@router.callback_query(F.data == "psg_scope_type_local")
async def psg_local_start(callback: CallbackQuery, state: FSMContext):
    await state.update_data(is_local=True)
    await callback.message.edit_text("Qaysi viloyat ichida safar qilasiz?", reply_markup=get_regions_kb("psg_locreg"))
    await state.set_state(PassengerSearch.from_region)


@router.callback_query(PassengerSearch.from_region, F.data.startswith("psg_locreg_reg_"))
async def psg_local_reg_picked(callback: CallbackQuery, state: FSMContext):
    region = callback.data.replace("psg_locreg_reg_", "")
    if region == "Toshkent shahri":
        await callback.answer("⚠️ Toshkent shahri ichida lokal qatnov mavjud emas!", show_alert=True)
        return
    await state.update_data(from_region=region, to_region=region)
    await callback.message.edit_text(f"[{region}] — Chiqish tumaningiz:", reply_markup=get_districts_kb(region, "psg_from"))
    await state.set_state(PassengerSearch.from_district)


@router.callback_query(F.data == "psg_scope_type_intercity")
async def psg_inter_start(callback: CallbackQuery, state: FSMContext):
    await state.update_data(is_local=False)
    await callback.message.edit_text("Qaysi viloyatdan yo‘lga chiqasiz?", reply_markup=get_regions_kb("psg_from"))
    await state.set_state(PassengerSearch.from_region)


@router.callback_query(PassengerSearch.from_region, F.data.startswith("psg_from_reg_"))
async def psg_from_reg_picked(callback: CallbackQuery, state: FSMContext):
    region = callback.data.replace("psg_from_reg_", "")
    if region == "Toshkent shahri":
        await state.update_data(from_region="Toshkent shahri", from_district="")
        await callback.message.edit_text("Boradigan viloyatingizni tanlang:", reply_markup=get_regions_kb("psg_to"))
        await state.set_state(PassengerSearch.to_region)
        return
    await state.update_data(from_region=region)
    await callback.message.edit_text(f"[{region}] — Tumaningizni tanlang:", reply_markup=get_districts_kb(region, "psg_from"))
    await state.set_state(PassengerSearch.from_district)


@router.callback_query(PassengerSearch.from_district, F.data.startswith("psg_from_dist_"))
async def psg_from_dist_picked(callback: CallbackQuery, state: FSMContext):
    dist = callback.data.replace("psg_from_dist_", "")
    await state.update_data(from_district=dist)
    data = await state.get_data()
    if data.get("is_local"):
        region = data['from_region']
        await callback.message.edit_text(f"[{region}] — Qaysi tumanga borasiz?", reply_markup=get_districts_kb(region, "psg_to"))
        await state.set_state(PassengerSearch.to_district)
    else:
        await callback.message.edit_text("Boradigan viloyatingizni tanlang:", reply_markup=get_regions_kb("psg_to"))
        await state.set_state(PassengerSearch.to_region)


@router.callback_query(PassengerSearch.to_region, F.data.startswith("psg_to_reg_"))
async def psg_to_reg_picked(callback: CallbackQuery, state: FSMContext, bot: Bot):
    region = callback.data.replace("psg_to_reg_", "")
    if region == "Toshkent shahri":
        data = await state.get_data()
        if data.get("from_region") == "Toshkent shahri":
            await callback.answer("⚠️ Chiqish manzili va borish manzili bir xil bo‘lishi mumkin emas!", show_alert=True)
            return
        await state.update_data(to_region="Toshkent shahri", to_district="")
        await finalize_passenger_search(callback, state, bot)
        return
    await state.update_data(to_region=region)
    await callback.message.edit_text(f"[{region}] — Boradigan tumanni tanlang:", reply_markup=get_districts_kb(region, "psg_to"))
    await state.set_state(PassengerSearch.to_district)


@router.callback_query(PassengerSearch.to_district, F.data.startswith("psg_to_dist_"))
async def psg_to_dist_picked(callback: CallbackQuery, state: FSMContext, bot: Bot):
    dist = callback.data.replace("psg_to_dist_", "")
    await state.update_data(to_district=dist)
    await finalize_passenger_search(callback, state, bot)


async def finalize_passenger_search(callback: CallbackQuery, state: FSMContext, bot: Bot):
    data = await state.get_data()
    f_reg = data.get('from_region')
    f_dist = data.get('from_district', '')
    t_reg = data.get('to_region')
    t_dist = data.get('to_district', '')

    from_loc = f"{f_reg}, {f_dist}" if f_dist else f_reg
    to_loc = f"{t_reg}, {t_dist}" if t_dist else t_reg

    if from_loc == to_loc:
        await callback.answer("⚠️ Chiqish manzili va borish manzili bir xil bo‘lishi mumkin emas!", show_alert=True)
        return

    req_service = data.get("req_service", "passenger")
    await state.update_data(final_from=from_loc, final_to=to_loc)

    await callback.message.delete()
    drivers = await db.search_drivers(from_loc, to_loc)

    vip_drivers = []
    free_drivers = []
    for drv in drivers:
        if await db.is_driver_subscribed(drv['telegram_id']):
            vip_drivers.append(drv)
        else:
            free_drivers.append(drv)

    sorted_drivers = vip_drivers + free_drivers

    if sorted_drivers:
        await callback.message.answer(f"🔍 <b>{from_loc}</b> ➡️ <b>{to_loc}</b> bo‘yicha topilgan faol haydovchilar:", parse_mode="HTML")
        for drv in sorted_drivers:
            is_vip = await db.is_driver_subscribed(drv['telegram_id'])
            vip_badge = "🌟 <b>[VIP TAVSIYA]</b> " if is_vip else ""
            post_status = "Ha" if drv["accepts_post"] else "Yo‘q"
            caption = (
                f"{vip_badge}👤 <b>Haydovchi:</b> {drv['full_name']}\n"
                f"🚘 <b>Mashina:</b> {drv['car_model']} ({drv['car_number']})\n"
                f"💺 <b>Bo‘sh joy:</b> {drv['seats']} ta\n"
                f"📦 <b>Pochta oladi:</b> {post_status}\n"
                f"📞 <b>Aloqa:</b> {drv['phone']}"
            )
            await callback.message.answer_photo(photo=drv['photo_id'], caption=caption, reply_markup=get_driver_card_kb(drv['telegram_id']), parse_mode="HTML")
    else:
        recent_count = await db.count_recent_orders(callback.from_user.id, minutes=60)
        if recent_count >= MAX_ORDERS_PER_HOUR:
            await state.clear()
            await callback.message.answer(
                "⏳ <b>Iltimos, biroz kuting.</b>\n\nSiz so‘nggi 1 soat ichida yetarlicha buyurtma berdingiz. "
                "Birozdan so‘ng qayta urinib ko‘ring.",
                reply_markup=await render_user_menu(callback.from_user.id),
                parse_mode="HTML"
            )
            return

        saved_phone = await db.get_user_phone(callback.from_user.id)
        if saved_phone:
            order_id = await db.add_passenger_order(user_id=callback.from_user.id, full_name=callback.from_user.full_name, phone=saved_phone, from_loc=from_loc, to_loc=to_loc, seats=1, target_driver_id=0, service_type=req_service)

            driver_ids = await db.get_matching_driver_ids(from_loc, to_loc)
            monetization_on = (await db.get_setting("monetization_active", "0")) == "1"

            vip_receivers = []
            free_receivers = []

            for d_id in driver_ids:
                if monetization_on:
                    if await db.is_driver_subscribed(d_id):
                        vip_receivers.append(d_id)
                    else:
                        free_receivers.append(d_id)
                else:
                    vip_receivers.append(d_id)

            order_title = "📦 <b>Yangi Pochta/Yuk buyurtmasi!</b>" if req_service == "cargo" else "🔔 <b>Yangi yo‘lovchi buyurtmasi!</b>"
            drv_msg = f"{order_title}\n\n📍 <b>Yo‘nalish:</b> {from_loc} ➡️ {to_loc}\n👤 <b>Mijoz:</b> {callback.from_user.full_name}\n📞 <b>Telefon:</b> {saved_phone}\n\n🔗 @w_taxi_bot"

            for vid in vip_receivers:
                try:
                    await bot.send_message(chat_id=vid, text=drv_msg, parse_mode="HTML")
                    await asyncio.sleep(0.04)
                except Exception:
                    pass

            if monetization_on and free_receivers:
                asyncio.create_task(delayed_dispatch_to_free_drivers(bot, free_receivers, drv_msg, delay_seconds=300))

            await state.clear()
            await callback.message.answer(
                f"✅ <b>Buyurtmangiz qabul qilindi!</b>\n\n"
                f"📍 {from_loc} ➡️ {to_loc}\n"
                f"📞 Bog‘lanish raqami: <b>{saved_phone}</b>\n\n"
                "Haydovchilar tez orada siz bilan bog‘lanishadi.",
                reply_markup=get_close_order_kb(order_id),
                parse_mode="HTML"
            )
        else:
            await callback.message.answer(
                f"📍 <b>{from_loc}</b> ➡️ <b>{to_loc}</b> yo‘nalishida hozircha mashina topilmadi.\n\n"
                "Buyurtmangizni barcha haydovchilarga yetkazishimiz uchun pastdagi tugma orqali telefon raqamingizni yuboring:",
                reply_markup=phone_keyboard,
                parse_mode="HTML"
            )
            await state.set_state(PassengerOrderState.phone)


@router.callback_query(F.data.startswith("book_drv_"))
async def psg_book_direct_driver(callback: CallbackQuery, state: FSMContext, bot: Bot):
    target_drv = int(callback.data.replace("book_drv_", ""))
    saved_phone = await db.get_user_phone(callback.from_user.id)
    data = await state.get_data()
    from_loc = data.get('final_from', "Noma'lum")
    to_loc = data.get('final_to', "Noma'lum")
    req_service = data.get('req_service', 'passenger')

    if saved_phone:
        order_id = await db.add_passenger_order(user_id=callback.from_user.id, full_name=callback.from_user.full_name, phone=saved_phone, from_loc=from_loc, to_loc=to_loc, seats=1, target_driver_id=target_drv, service_type=req_service)
        try:
            drv_msg = f"🎯 <b>Sizga to‘g‘ridan-to‘g‘ri buyurtma!</b>\n\n📍 <b>Yo‘nalish:</b> {from_loc} ➡️ {to_loc}\n👤 <b>Mijoz:</b> {callback.from_user.full_name}\n📞 <b>Telefon:</b> {saved_phone}\n\n🔗 @w_taxi_bot"
            await bot.send_message(chat_id=target_drv, text=drv_msg, parse_mode="HTML")
        except Exception:
            pass
        await state.clear()
        await callback.message.answer(
            f"✅ <b>Buyurtmangiz haydovchiga yetkazildi!</b>\n\n"
            f"📍 {from_loc} ➡️ {to_loc}\n"
            f"📞 Bog‘lanish uchun: <b>{saved_phone}</b>\n"
            "Haydovchi tez orada siz bilan bog‘lanadi.",
            reply_markup=get_close_order_kb(order_id),
            parse_mode="HTML"
        )
    else:
        await state.update_data(target_driver_id=target_drv)
        await callback.message.answer("Haydovchi siz bilan bog‘lanishi uchun pastdagi tugma orqali telefon raqamingizni yuboring:", reply_markup=phone_keyboard)
        await state.set_state(PassengerOrderState.phone)


@router.message(PassengerOrderState.phone, F.contact)
async def psg_order_phone_submit(message: Message, state: FSMContext, bot: Bot):
    phone = message.contact.phone_number
    phone_clean = clean_phone(phone)
    if not phone_clean:
        await message.answer("Telefon raqamni o‘qishda xatolik. Iltimos, pastdagi tugmani qayta bosing:", reply_markup=phone_keyboard)
        return

    await db.save_user_phone(message.from_user.id, message.from_user.full_name, phone_clean)

    recent_count = await db.count_recent_orders(message.from_user.id, minutes=60)
    if recent_count >= MAX_ORDERS_PER_HOUR:
        await state.clear()
        await message.answer(
            "⏳ <b>Iltimos, biroz kuting.</b>\n\nSiz so‘nggi 1 soat ichida yetarlicha buyurtma berdingiz. "
            "Birozdan so‘ng qayta urinib ko‘ring.",
            reply_markup=await render_user_menu(message.from_user.id),
            parse_mode="HTML"
        )
        return

    data = await state.get_data()
    from_loc = data.get('final_from', "Noma'lum")
    to_loc = data.get('final_to', "Noma'lum")
    target_drv = data.get('target_driver_id', 0)
    req_service = data.get('req_service', 'passenger')

    order_id = await db.add_passenger_order(user_id=message.from_user.id, full_name=message.from_user.full_name, phone=phone_clean, from_loc=from_loc, to_loc=to_loc, seats=1, target_driver_id=target_drv, service_type=req_service)

    if target_drv != 0:
        try:
            drv_msg = f"🎯 <b>Sizga to‘g‘ridan-to‘g‘ri buyurtma!</b>\n\n📍 <b>Yo‘nalish:</b> {from_loc} ➡️ {to_loc}\n👤 <b>Mijoz:</b> {message.from_user.full_name}\n📞 <b>Telefon:</b> {phone_clean}\n\n🔗 @w_taxi_bot"
            await bot.send_message(chat_id=target_drv, text=drv_msg, parse_mode="HTML")
        except Exception:
            pass
    else:
        driver_ids = await db.get_matching_driver_ids(from_loc, to_loc)
        monetization_on = (await db.get_setting("monetization_active", "0")) == "1"
        vip_receivers = []
        free_receivers = []

        for d_id in driver_ids:
            if monetization_on:
                if await db.is_driver_subscribed(d_id):
                    vip_receivers.append(d_id)
                else:
                    free_receivers.append(d_id)
            else:
                vip_receivers.append(d_id)

        order_title = "📦 <b>Yangi Pochta/Yuk buyurtmasi!</b>" if req_service == "cargo" else "🔔 <b>Yangi yo‘lovchi buyurtmasi!</b>"
        drv_msg = f"{order_title}\n\n📍 <b>Yo‘nalish:</b> {from_loc} ➡️ {to_loc}\n👤 <b>Mijoz:</b> {message.from_user.full_name}\n📞 <b>Telefon:</b> {phone_clean}\n\n🔗 @w_taxi_bot"

        for vid in vip_receivers:
            try:
                await bot.send_message(chat_id=vid, text=drv_msg, parse_mode="HTML")
                await asyncio.sleep(0.04)
            except Exception:
                pass

        if monetization_on and free_receivers:
            asyncio.create_task(delayed_dispatch_to_free_drivers(bot, free_receivers, drv_msg, delay_seconds=300))

    await state.clear()
    await message.answer(
        f"✅ <b>Buyurtmangiz muvaffaqiyatli yetkazildi!</b>\n\n"
        f"📍 {from_loc} ➡️ {to_loc}\n"
        f"📞 Aloqa raqamingiz: <b>{phone_clean}</b>\n"
        "Haydovchilar tez orada ular bilan bog‘lanishadi.",
        reply_markup=get_close_order_kb(order_id),
        parse_mode="HTML"
    )


@router.callback_query(F.data.startswith("close_order_"))
async def close_order_callback(callback: CallbackQuery):
    order_id = int(callback.data.replace("close_order_", ""))
    requester_id = callback.from_user.id
    is_admin_user = is_super_admin(requester_id) or await db.is_admin(requester_id, ADMIN_ID)

    success = await db.close_passenger_order(order_id, requester_id=requester_id, is_admin=is_admin_user)

    if not success:
        await callback.answer("⚠️ Bu e'lonni yopish huquqingiz yo‘q yoki u allaqachon yopilgan.", show_alert=True)
        return

    await callback.message.edit_text("✅ <b>E'loningiz yopildi va haydovchilar ro‘yxatidan olib tashlandi.</b>", parse_mode="HTML")
    await callback.answer("E'lon muvaffaqiyatli bekor qilindi!")


@router.message(PassengerOrderState.phone, F.text)
async def psg_order_phone_text_rejected(message: Message):
    await message.answer(
        "⚠️ <b>Iltimos, raqamni matn ko‘rinishida yozmang.</b>\n\n"
        "Faqat pastdagi <b>📲 Telefon raqamni yuborish</b> tugmasini bosing:",
        reply_markup=phone_keyboard,
        parse_mode="HTML"
    )
