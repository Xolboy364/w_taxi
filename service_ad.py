from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, ReplyKeyboardRemove, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext

from config import ADMIN_ID
from keyboards import phone_keyboard, get_service_types_kb, get_fuel_types_kb, FUEL_TYPES
from states import ServiceAdStates
import database as db

router = Router()

# Xizmat turlari va narxlari
SERVICE_TYPES = {
    "gas": {"name": "⛽️ Zapravka", "price": 50000},
    "food": {"name": "🍽 Ovqatlanish", "price": 50000},
    "hotel": {"name": "🛏 Mehmonxona", "price": 70000},
    "service": {"name": "🔧 Avtoservis", "price": 50000},
    "autosalon": {"name": "🚗 Avtosalon", "price": 100000}
}

async def check_access_svc(message_or_callback) -> bool:
    user_id = message_or_callback.from_user.id
    banned, reason = await db.is_user_banned(user_id)
    if banned:
        text = f"⛔️ <b>Sizning profilingiz bloklangan!</b>\nSabab: {reason}"
        if isinstance(message_or_callback, Message):
            await message_or_callback.answer(text, parse_mode="HTML")
        else:
            await message_or_callback.message.answer(text, parse_mode="HTML")
        return False
    return True

@router.message(F.text == "📢 E'lon joylashtirish")
async def service_ad_start(message: Message, state: FSMContext):
    if not await check_access_svc(message): return
    await state.clear()
    await message.answer(
        "📢 <b>Yo'l bo'yi xizmati e'loni</b>\n\n"
        "Xizmat turini tanlang:",
        reply_markup=get_service_types_kb(),
        parse_mode="HTML"
    )
    await state.set_state(ServiceAdStates.choose_type)

@router.callback_query(ServiceAdStates.choose_type, F.data.startswith("svc_type_"))
async def service_ad_type(callback: CallbackQuery, state: FSMContext):
    svc_type = callback.data.replace("svc_type_", "")
    if svc_type == "back":
        await callback.message.delete()
        from handlers import render_user_menu
        menu = await render_user_menu(callback.from_user.id)
        await callback.message.answer("🔙 Bosh menyu", reply_markup=menu)
        await callback.answer()
        return

    await state.update_data(service_type=svc_type)

    if svc_type == "gas":
        await state.update_data(fuel_types=[])
        fuel_msg = "⛽️ Qanday yoqilgi turlari mavjud? Kerakli turlarni belgilang, song Davom etish tugmasini bosing:"
        await callback.message.edit_text(fuel_msg, reply_markup=get_fuel_types_kb([], "adfuel"))
        await state.set_state(ServiceAdStates.choose_fuel_types)
        await callback.answer()
        return

    await callback.message.answer("📌 Xizmat nomini kiriting:")
    await state.set_state(ServiceAdStates.enter_name)
    await callback.answer()

@router.callback_query(ServiceAdStates.choose_fuel_types, F.data.startswith("adfuel_tog_"))
async def ad_fuel_toggle(callback: CallbackQuery, state: FSMContext):
    key = callback.data.replace("adfuel_tog_", "")
    data = await state.get_data()
    sel = data.get("fuel_types", [])
    if key in sel:
        sel.remove(key)
    else:
        sel.append(key)
    await state.update_data(fuel_types=sel)
    await callback.message.edit_reply_markup(reply_markup=get_fuel_types_kb(sel, "adfuel"))
    await callback.answer()

@router.callback_query(ServiceAdStates.choose_fuel_types, F.data == "adfuel_done")
async def ad_fuel_done(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    if not data.get("fuel_types"):
        await callback.answer("Kamida 1 ta yoqilgi turini tanlang!", show_alert=True)
        return
    await callback.message.delete()
    await callback.message.answer("📌 Xizmat nomini kiriting:")
    await state.set_state(ServiceAdStates.enter_name)
    await callback.answer()

@router.message(ServiceAdStates.enter_name)
async def service_ad_name(message: Message, state: FSMContext):
    if len(message.text.strip()) < 3:
        await message.answer("Nomi kamida 3 ta belgidan iborat bo'lishi kerak:")
        return
    await state.update_data(name=message.text.strip())
    await message.answer("📍 Xizmat joylashgan manzilni (lokatsiya) yuboring:")
    await state.set_state(ServiceAdStates.enter_location)

@router.message(ServiceAdStates.enter_location, F.location)
async def service_ad_location(message: Message, state: FSMContext):
    await state.update_data(
        latitude=message.location.latitude,
        longitude=message.location.longitude,
        telegram_id=message.from_user.id
    )
    await message.answer("📞 Telefon raqamingizni yuboring:", reply_markup=phone_keyboard)
    await state.set_state(ServiceAdStates.enter_phone)

@router.message(ServiceAdStates.enter_location, F.text)
async def service_ad_location_text(message: Message):
    await message.answer("Iltimos, lokatsiya yuboring! 📍")

@router.message(ServiceAdStates.enter_phone, F.contact)
async def service_ad_phone(message: Message, state: FSMContext):
    phone = message.contact.phone_number
    await state.update_data(phone=phone)
    await message.answer("📝 Qisqa tavsif yozing:", reply_markup=ReplyKeyboardRemove())
    await state.set_state(ServiceAdStates.enter_description)

@router.message(ServiceAdStates.enter_phone, F.text)
async def service_ad_phone_text(message: Message):
    await message.answer("Iltimos, pastdagi tugma orqali telefon raqamingizni yuboring:", reply_markup=phone_keyboard)

@router.message(ServiceAdStates.enter_description)
async def service_ad_description(message: Message, state: FSMContext):
    if len(message.text.strip()) < 5:
        await message.answer("Tavsif kamida 5 ta belgidan iborat bo'lishi kerak:")
        return
    await state.update_data(description=message.text.strip())
    await message.answer("🖼 Rasm yuboring (ixtiyoriy, yoki 'O'tkazib yuborish' deb yozing):")
    await state.set_state(ServiceAdStates.enter_photo)

@router.message(ServiceAdStates.enter_photo, F.photo)
async def service_ad_photo(message: Message, state: FSMContext):
    photo_id = message.photo[-1].file_id
    await state.update_data(photo_id=photo_id)
    await show_payment_summary(message, state)

@router.message(ServiceAdStates.enter_photo, F.text.lower().in_(["o'tkazib yuborish", "otkazib yuborish"]))
async def service_ad_skip_photo(message: Message, state: FSMContext):
    await state.update_data(photo_id=None)
    await show_payment_summary(message, state)

@router.message(ServiceAdStates.enter_photo, F.text)
async def service_ad_photo_invalid(message: Message):
    await message.answer("Iltimos, rasm yuboring yoki 'O'tkazib yuborish' deb yozing:")

async def show_payment_summary(message: Message, state: FSMContext):
    data = await state.get_data()
    svc_info = SERVICE_TYPES.get(data.get("service_type"), SERVICE_TYPES["gas"])
    amount = svc_info["price"]
    await state.update_data(amount=amount)
    
    card_num = await db.get_setting("p2p_card_number", "8600123456789012")
    click_url = f"https://my.click.uz/clickp2p/?recipient={card_num}&amount={amount}"
    
    fuel_line = ""
    if data.get("fuel_types"):
        fuel_names = ", ".join(FUEL_TYPES.get(k, k) for k in data["fuel_types"])
        fuel_line = f"⛽️ Yoqilg'i turlari: {fuel_names}\n"

    text = (
        f"📢 <b>E'lon ma'lumotlari:</b>\n\n"
        f"🏷 Tur: {svc_info['name']}\n"
        f"{fuel_line}"
        f"📌 Nomi: {data['name']}\n"
        f"📍 Manzil: {data['latitude']}, {data['longitude']}\n"
        f"📞 Telefon: {data['phone']}\n"
        f"📝 Tavsif: {data['description'][:50]}...\n\n"
        f"💰 To'lov: <b>{amount:,} so'm</b>\n"
        f"📅 Davomiyligi: <b>30 kun</b>\n\n"
        f"To'lovni amalga oshirish uchun Click tugmasini bosing:\n"
        f"To'lov qilgach, <b>chek skrinshotini</b> yuboring."
    )
    
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💳 Click orqali to'lash", url=click_url)],
            [InlineKeyboardButton(text="📸 Chekni yuborish", callback_data="svc_pay_receipt")],
            [InlineKeyboardButton(text="🔙 Bekor qilish", callback_data="svc_cancel")]
        ]
    )
    
    await message.answer(text, reply_markup=kb, parse_mode="HTML")
    await state.set_state(ServiceAdStates.waiting_payment)

@router.callback_query(F.data == "svc_pay_receipt")
async def service_payment_receipt(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer("📸 Iltimos, to'lov chekining skrinshotini yuboring:")
    await state.set_state(ServiceAdStates.receipt_photo)
    await callback.answer()

@router.message(ServiceAdStates.receipt_photo, F.photo)
async def service_receipt_received(message: Message, state: FSMContext, bot: Bot):
    photo_id = message.photo[-1].file_id
    data = await state.get_data()
    
    ad_id = await db.save_service_ad(data)
    await db.save_service_payment(ad_id, message.from_user.id, data['amount'], photo_id)
    
    await message.answer(
        "✅ <b>Chek qabul qilindi!</b>\n"
        "Admin tekshirib chiqqach, e'loningiz faollashtiriladi.\n\n"
        "⏳ Kuting, bu 24 soatgacha vaqt olishi mumkin.",
        parse_mode="HTML"
    )
    
    admin_recipients = await db.get_backup_recipients(ADMIN_ID)
    approve_kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ E'lonni tasdiqlash", callback_data=f"svc_approve_{ad_id}")],
            [InlineKeyboardButton(text="❌ Bekor qilish", callback_data=f"svc_reject_{ad_id}")]
        ]
    )
    
    svc_info = SERVICE_TYPES.get(data['service_type'])
    caption = (
        f"🔔 <b>Yangi to'lovli e'lon!</b>\n\n"
        f"🏷 Tur: {svc_info['name']}\n"
        f"📌 Nomi: {data['name']}\n"
        f"📍 Manzil: {data['latitude']}, {data['longitude']}\n"
        f"👤 Foydalanuvchi: {message.from_user.full_name}\n"
        f"🆔 ID: <code>{message.from_user.id}</code>\n"
        f"💰 Summa: {data['amount']:,} so'm"
    )
    
    for aid in admin_recipients:
        try:
            await bot.send_photo(
                chat_id=aid, 
                photo=photo_id, 
                caption=caption, 
                reply_markup=approve_kb, 
                parse_mode="HTML"
            )
        except Exception:
            pass
    
    await state.clear()

@router.callback_query(F.data == "svc_cancel")
async def service_cancel(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("❌ E'lon joylashtirish bekor qilindi.")
    await callback.answer()

@router.callback_query(F.data.startswith("svc_approve_"))
async def service_approve(callback: CallbackQuery, bot: Bot):
    if not (await db.is_admin(callback.from_user.id, ADMIN_ID) or callback.from_user.id == ADMIN_ID):
        await callback.answer("Huquqingiz yo'q!", show_alert=True)
        return
    
    ad_id = int(callback.data.replace("svc_approve_", ""))
    ad = await db.activate_service_ad(ad_id, days=30)
    
    await callback.message.edit_caption(
        caption=callback.message.caption + "\n\n✅ <b>TASDIQLANDI - 30 kun faol!</b>",
        parse_mode="HTML"
    )
    
    if ad:
        try:
            await bot.send_message(
                chat_id=ad['user_id'],
                text="🎉 <b>Tabriklaymiz! E'loningiz tasdiqlandi!</b>\n\n"
                     f"📌 <b>{ad['name']}</b>\n"
                     "📅 30 kun davomida faol bo'ladi.\n\n"
                     "🔗 @w_taxi_bot\n\n"
                     "<i>E'loningiz endi barcha foydalanuvchilarga ko'rsatiladi!</i>",
                parse_mode="HTML"
            )
        except Exception:
            pass
    
    await callback.answer("E'lon tasdiqlandi!")

@router.callback_query(F.data.startswith("svc_reject_"))
async def service_reject(callback: CallbackQuery, bot: Bot):
    if not (await db.is_admin(callback.from_user.id, ADMIN_ID) or callback.from_user.id == ADMIN_ID):
        await callback.answer("Huquqingiz yo'q!", show_alert=True)
        return
    
    ad_id = int(callback.data.replace("svc_reject_", ""))
    ad = await db.reject_service_ad(ad_id)
    
    await callback.message.edit_caption(
        caption=callback.message.caption + "\n\n❌ <b>BEKOR QILINDI</b>",
        parse_mode="HTML"
    )
    
    if ad:
        try:
            await bot.send_message(
                chat_id=ad['user_id'],
                text="❌ <b>E'loningiz bekor qilindi.</b>\n\n"
                     "Sababi: To'lov tasdiqlanmadi yoki ma'lumotlar noto'g'ri.\n"
                     "Admin bilan bog'lanishingiz mumkin.\n\n"
                     "🔗 @w_taxi_bot",
                parse_mode="HTML"
            )
        except Exception:
            pass
    
    await callback.answer("E'lon bekor qilindi!")
