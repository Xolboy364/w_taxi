from aiogram.types import (
    ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

REGIONS_DATA = {
    "Toshkent shahri": ["Yunusobod", "Chilonzor", "Mirzo Ulug‘bek", "Mirobod", "Shayxontohur", "Yakkasaroy", "Sergeli", "Yangi Hayot", "Olmazor", "Uchtepa", "Bektemir", "Yashnobod"],
    "Qoraqalpog‘iston Resp.": ["Nukus sh.", "Taxiatosh sh.", "Amudaryo", "Beruniy", "Bo‘zatov", "Chimboy", "Ellikqal’a", "Kegeyli", "Mo‘ynoq", "Nukus tumani", "Qanliko‘l", "Qo‘ng‘irot", "Qorao‘zak", "Shumanay", "Taxtako‘pir", "To‘rtko‘l", "Xo‘jayli"],
    "Surxondaryo viloyati": ["Termiz sh.", "Angor", "Bandixon", "Boysun", "Denov", "Jarqo‘rg‘on", "Muzrabot", "Oltinsoy", "Qiziriq", "Qumqo‘rg‘on", "Sariosiyo", "Sherobod", "Sho‘rchi", "Termiz tumani", "Uzun"],
    "Qashqadaryo viloyati": ["Qarshi sh.", "Shahrisabz sh.", "Chiroqchi", "Dehqonobod", "G‘uzor", "Kasbi", "Kitob", "Koson", "Ko‘kdala", "Mirishkor", "Muborak", "Nishon", "Qamashi", "Qarshi tumani", "Shahrisabz tumani", "Yakkabog‘"],
    "Samarqand viloyati": ["Samarqand sh.", "Kattaqo‘rg‘on sh.", "Bulung‘ur", "Ishtixon", "Jomboy", "Kattaqo‘rg‘on tumani", "Narpay", "Nurobod", "Oqdaryo", "Paxtachi", "Payariq", "Pastdarg‘om", "Qo‘shrabot", "Samarqand tumani", "Toyloq", "Urgut"],
    "Farg‘ona viloyati": ["Farg‘ona sh.", "Qo‘qon sh.", "Marg‘ilon sh.", "Quvasoy sh.", "Bag‘dod", "Beshariq", "Buvayda", "Dang‘ara", "Farg‘ona tumani", "Furqat", "Oltiariq", "Quva", "Qo‘shtepa", "Rishton", "So‘x", "Toshloq", "Uchko‘prik", "O‘zbekiston tum.", "Yozyovon"],
    "Andijon viloyati": ["Andijon sh.", "Xonobod sh.", "Andijon tumani", "Asaka", "Baliqchi", "Bo‘ston", "Buloqboshi", "Izboskan", "Jalaquduq", "Xo‘jaobod", "Marhamat", "Oltinko‘l", "Paxtaobod", "Qo‘rg‘ontepa", "Shahrixon", "Ulug‘nor"],
    "Namangan viloyati": ["Namangan sh.", "Chortoq", "Chust", "Kosonsoy", "Mingbuloq", "Namangan tumani", "Norin", "Pop", "To‘raqo‘rg‘on", "Uchqo‘rg‘on", "Uychi", "Yangiqo‘rg‘on", "Davlatobod"],
    "Buxoro viloyati": ["Buxoro sh.", "Kogon sh.", "Olot", "Buxoro tumani", "G‘ijduvon", "Jondor", "Kogon tumani", "Qorako‘l", "Qorovulbozor", "Peshku", "Romitan", "Shofirkon", "Vobkent"],
    "Navoiy viloyati": ["Navoiy sh.", "Zarafshon sh.", "Kanimex", "Karmana", "Qiziltepa", "Navbahor", "Nurota", "Tomdi", "Uchquduq", "Xatirchi"],
    "Jizzax viloyati": ["Jizzax sh.", "Arnasoy", "Baxmal", "Do‘stlik", "Forish", "G‘allaorol", "Sh.Rashidov", "Mirzacho‘l", "Paxtakor", "Yangiobod", "Zafarobod", "Zarbdor"],
    "Sirdaryo viloyati": ["Guliston sh.", "Shirin sh.", "Yangiyer sh.", "Boyovut", "Guliston tumani", "Mirzaobod", "Oqoltin", "Sardoba", "Sayxunobod", "Sirdaryo tumani", "Xovos"],
    "Xorazm viloyati": ["Urganch sh.", "Xiva sh.", "Bog‘ot", "Gurlan", "Hazorasp", "Qo‘shko‘pir", "Shovot", "Tuproqqal’a", "Urganch tumani", "Xiva tumani", "Xonqa", "Yangiariq", "Yangibozor"],
    "Toshkent viloyati": ["Nurafshon sh.", "Olmaliq sh.", "Angren sh.", "Chirchiq sh.", "Bekobod sh.", "Yangiyo‘l sh.", "Bo‘stonliq", "Chinoz", "Qibray", "Parkent", "Piskent", "Quyi Chirchiq", "O‘rta Chirchiq", "Yuqori Chirchiq", "Zangiota", "Toshkent tumani", "Bo‘ka", "Bekobod tumani"]
}

def get_main_menu(is_super: bool = False, is_sub: bool = False) -> ReplyKeyboardMarkup:
    keyboard = [
        [KeyboardButton(text="🚗 Haydovchi"), KeyboardButton(text="🙋‍♂️ Yo‘lovchi")],
        [KeyboardButton(text="📦 Pochta berish"), KeyboardButton(text="🚚 Yuk yuborish")],
        [KeyboardButton(text="🗺 Yo‘l bo‘yi xizmatlari")]
    ]
    if is_super:
        keyboard.append([KeyboardButton(text="👑 Super Admin Panel")])
    elif is_sub:
        keyboard.append([KeyboardButton(text="🛠 Admin Panel")])
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

def get_roadside_services_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="⛽️ Zapravka", request_location=True), KeyboardButton(text="🍽 Ovqatlanish", request_location=True)],
            [KeyboardButton(text="🛏 Hostel va Mehmonxona", request_location=True), KeyboardButton(text="🔧 Avtoservis", request_location=True)],
            [KeyboardButton(text="🔙 Bosh menyu")]
        ],
        resize_keyboard=True
    )

def get_driver_cabinet_kb(status: str = 'waiting', is_subscribed: bool = True) -> ReplyKeyboardMarkup:
    status_btn = KeyboardButton(text="🚀 Yo‘lga chiqdim") if status == 'waiting' else KeyboardButton(text="🟢 Mijoz kutmoqdaman")

    keyboard = [
        [KeyboardButton(text="🛣 Yangi marshrut sozlash")],
        [status_btn],
        [KeyboardButton(text="📋 Yo‘lovchilar ro‘yxati")],
        [KeyboardButton(text="🌟 Tarif va Obuna")] if not is_subscribed else [],
        [KeyboardButton(text="🗑 Yo‘nalishlarni tozalash"), KeyboardButton(text="🔙 Bosh menyu")]
    ]
    keyboard = [row for row in keyboard if row]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

def get_super_admin_kb(maintenance_on: bool = False, monetization_on: bool = False, is_temp_session: bool = False) -> ReplyKeyboardMarkup:
    kill_switch_btn = KeyboardButton(text="🍏 Botni ishga tushirish (Start)") if maintenance_on else KeyboardButton(text="🔴 Favqulodda to‘xtatish")
    monetization_btn = KeyboardButton(text="🛑 Monetizatsiyani to‘xtatish") if monetization_on else KeyboardButton(text="💎 Monetizatsiyani boshlash")

    keyboard = [
        [KeyboardButton(text="📊 Bot Statistikasi"), KeyboardButton(text="👥 Haydovchilar ro‘yxati")],
        [KeyboardButton(text="➕ Yangi Admin tayinlash"), KeyboardButton(text="➖ Adminni o‘chirish")],
        [KeyboardButton(text="📋 Adminlar ro‘yxati"), KeyboardButton(text="📝 Adminlar faoliyati (Audit)")],
        [KeyboardButton(text="📢 Ommaviy xabar yuborish"), KeyboardButton(text="🚫 Qora ro‘yxat (Ban)")],
        [KeyboardButton(text="💳 To‘lov kartasini sozlash"), KeyboardButton(text="🔑 Parolni o‘zgartirish")],
        [KeyboardButton(text="💾 Baza zaxirasini yuklash (.db)")],
        [monetization_btn, kill_switch_btn]
    ]
    if is_temp_session:
        keyboard.append([KeyboardButton(text="🔒 Sessiyani yopish (Chiqish)")])
    else:
        keyboard.append([KeyboardButton(text="🔙 Bosh menyu")])
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

sub_admin_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📊 Bot Statistikasi"), KeyboardButton(text="👥 Haydovchilar ro‘yxati")],
        [KeyboardButton(text="🚫 Qora ro‘yxat (Ban)"), KeyboardButton(text="💾 Baza zaxirasini yuklash (.db)")],
        [KeyboardButton(text="🔙 Bosh menyu")]
    ],
    resize_keyboard=True
)

monetization_start_1_kb = InlineKeyboardMarkup(
    inline_keyboard=[
        [InlineKeyboardButton(text="💎 Ha, monetizatsiya boshlansin", callback_data="mon_start_1_ok")],
        [InlineKeyboardButton(text="🔙 Bekor qilish", callback_data="mon_cancel")]
    ]
)

monetization_start_2_kb = InlineKeyboardMarkup(
    inline_keyboard=[
        [InlineKeyboardButton(text="🚀 QAT’IY TASDIQLAYMAN (BOSHLASH)", callback_data="mon_start_2_confirm")],
        [InlineKeyboardButton(text="🔙 Bekor qilish", callback_data="mon_cancel")]
    ]
)

monetization_stop_1_kb = InlineKeyboardMarkup(
    inline_keyboard=[
        [InlineKeyboardButton(text="🛑 Ha, to‘xtatilsin", callback_data="mon_stop_1_ok")],
        [InlineKeyboardButton(text="🔙 Bekor qilish", callback_data="mon_cancel")]
    ]
)

monetization_stop_2_kb = InlineKeyboardMarkup(
    inline_keyboard=[
        [InlineKeyboardButton(text="⚠️ QAT’IY TASDIQLAYMAN (TO‘XTATISH)", callback_data="mon_stop_2_confirm")],
        [InlineKeyboardButton(text="🔙 Bekor qilish", callback_data="mon_cancel")]
    ]
)

ban_management_kb = InlineKeyboardMarkup(
    inline_keyboard=[
        [InlineKeyboardButton(text="🚫 Foydalanuvchini bloklash", callback_data="ban_action_block")],
        [InlineKeyboardButton(text="✅ Blokdan chiqarish (Unban)", callback_data="ban_action_unblock")]
    ]
)

ban_duration_kb = InlineKeyboardMarkup(
    inline_keyboard=[
        [InlineKeyboardButton(text="⏳ 1 kunga", callback_data="bandur_24"), InlineKeyboardButton(text="⏳ 3 kunga", callback_data="bandur_72")],
        [InlineKeyboardButton(text="⏳ 1 haftaga", callback_data="bandur_168"), InlineKeyboardButton(text="⛔️ Umrbod (Doimiy)", callback_data="bandur_0")]
    ]
)

kill_confirm_1_kb = InlineKeyboardMarkup(
    inline_keyboard=[
        [InlineKeyboardButton(text="⚠️ Ha, to‘xtatishga o‘tilsin", callback_data="kill_step_1_ok")],
        [InlineKeyboardButton(text="🔙 Bekor qilish", callback_data="kill_cancel")]
    ]
)

kill_confirm_2_kb = InlineKeyboardMarkup(
    inline_keyboard=[
        [InlineKeyboardButton(text="🔴 QAT’IY TASDIQLAYMAN (TO‘XTATISH)", callback_data="kill_step_2_confirm")],
        [InlineKeyboardButton(text="🔙 Bekor qilish", callback_data="kill_cancel")]
    ]
)

start_confirm_1_kb = InlineKeyboardMarkup(
    inline_keyboard=[
        [InlineKeyboardButton(text="🍏 Ha, ishga tushirilsin", callback_data="start_step_1_ok")],
        [InlineKeyboardButton(text="🔙 Bekor qilish", callback_data="start_cancel")]
    ]
)

start_confirm_2_kb = InlineKeyboardMarkup(
    inline_keyboard=[
        [InlineKeyboardButton(text="✅ QAT’IY TASDIQLAYMAN (ISHGA TUSHIRISH)", callback_data="start_step_2_confirm")],
        [InlineKeyboardButton(text="🔙 Bekor qilish", callback_data="start_cancel")]
    ]
)

def get_route_scope_kb(prefix: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🌐 Viloyatlararo / Toshkentga", callback_data=f"{prefix}_type_intercity")],
            [InlineKeyboardButton(text="🏘 O‘z viloyatim ichida (Lokal)", callback_data=f"{prefix}_type_local")]
        ]
    )

phone_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📱 Kontaktni ulashish", request_contact=True)],
        [KeyboardButton(text="🔙 Bosh menyu")]
    ],
    resize_keyboard=True
)

driver_type_kb = InlineKeyboardMarkup(
    inline_keyboard=[
        [InlineKeyboardButton(text="👥 Odam tashish", callback_data="drvtype_passenger")],
        [InlineKeyboardButton(text="🚚/📦 Yuk va Pochta", callback_data="drvtype_cargo")]
    ]
)

def get_cars_kb(service_type: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    cars = ["Cobalt", "Gentra", "Nexia 3", "Damas", "Tracker", "Captiva"] if service_type == "passenger" else ["Labo", "Porter", "Isuzu", "Gazel", "Fura"]
    for car in cars:
        builder.button(text=car, callback_data=f"car_{car}")
    builder.button(text="✍️ Boshqa (qo‘lda yozish)", callback_data="car_other")
    builder.adjust(2)
    return builder.as_markup()

def get_regions_kb(action_prefix: str, selected_list: list = None) -> InlineKeyboardMarkup:
    if selected_list is None:
        selected_list = []
    builder = InlineKeyboardBuilder()
    for reg in REGIONS_DATA.keys():
        if reg == "Toshkent shahri":
            is_sel = "Toshkent shahri" in selected_list
            icon = "✅ " if is_sel else ""
            builder.button(text=f"{icon}{reg}", callback_data=f"{action_prefix}_reg_{reg}")
        else:
            is_sel = any(item.startswith(f"{reg},") for item in selected_list)
            icon = "✅ " if is_sel else ""
            builder.button(text=f"{icon}{reg}", callback_data=f"{action_prefix}_reg_{reg}")
    builder.adjust(2)

    if selected_list and action_prefix in ["mfrom", "mto"]:
        controls = InlineKeyboardBuilder()
        next_btn_text = f"➡️ Borish joylariga o‘tish ({len(selected_list)} ta)" if action_prefix == "mfrom" else f"💾 Saqlash ({len(selected_list)} ta)"
        controls.button(text=next_btn_text, callback_data=f"{action_prefix}_done")
        controls.adjust(1)
        builder.attach(controls)

    return builder.as_markup()

def get_districts_kb(region: str, action_prefix: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for dist in REGIONS_DATA.get(region, []):
        builder.button(text=dist, callback_data=f"{action_prefix}_dist_{dist}")
    builder.button(text="🔙 Boshqa viloyat", callback_data=f"{action_prefix}_back_reg")
    builder.adjust(2)
    return builder.as_markup()

def get_multi_districts_kb(region: str, selected_list: list, prefix: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if region == "Toshkent shahri":
        return builder.as_markup()
    districts = REGIONS_DATA.get(region, [])

    for dist in districts:
        loc_name = f"{region}, {dist}"
        is_sel = loc_name in selected_list
        icon = "✅" if is_sel else "◻️"
        builder.button(text=f"{icon} {dist}", callback_data=f"{prefix}_tog_{dist}")
    builder.adjust(2)

    controls = InlineKeyboardBuilder()
    all_in = all(f"{region}, {d}" in selected_list for d in districts) if districts else False
    toggle_txt = "❌ Bekor qilish" if all_in else "✨ Barchasini tanlash"
    controls.button(text=toggle_txt, callback_data=f"{prefix}_all")

    next_btn_text = f"➡️ Borish joylariga o‘tish ({len(selected_list)} ta)" if prefix == "mfrom" else f"💾 Saqlash ({len(selected_list)} ta)"
    controls.button(text=next_btn_text, callback_data=f"{prefix}_done")
    controls.button(text="🔙 Boshqa viloyat qo‘shish", callback_data=f"{prefix}_back_reg")
    controls.adjust(1)

    builder.attach(controls)
    return builder.as_markup()

def get_driver_card_kb(driver_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🚖 Shu haydovchiga buyurtma berish", callback_data=f"book_drv_{driver_id}")]
        ]
    )

def get_close_order_kb(order_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="❌ E'lonni bekor qilish (Mashina topdim)", callback_data=f"close_order_{order_id}")]
        ]
    )

# ---- Xizmat turlari klaviaturasi (avtomatik patch, service_ad.py uchun) ----

SERVICE_TYPES = {
    "gas": {"name": "⛽️ Zapravka", "price": 50000},
    "food": {"name": "🍽 Ovqatlanish", "price": 50000},
    "hotel": {"name": "🛏 Mehmonxona", "price": 70000},
    "service": {"name": "🔧 Avtoservis", "price": 50000},
    "autosalon": {"name": "🚗 Avtosalon", "price": 100000},
    "medical": {"name": "🏥 Tibbiyot", "price": 60000}
}

def get_service_types_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup(inline_keyboard=[])
    for key, val in SERVICE_TYPES.items():
        kb.inline_keyboard.append([
            InlineKeyboardButton(text=val["name"], callback_data=f"svc_type_{key}")
        ])
    kb.inline_keyboard.append([
        InlineKeyboardButton(text="🔙 Bosh menyu", callback_data="svc_type_back")
    ])
    return kb
