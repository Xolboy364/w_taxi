import ast
import os
import sys

ok = True

def check(label, condition):
    global ok
    if condition:
        print(f"✅ {label}")
    else:
        print(f"❌ {label}")
        ok = False

# ---------- 1. webapp_api.py sintaksisi ----------
try:
    src = open("webapp_api.py", encoding="utf-8").read()
    ast.parse(src)
    check("webapp_api.py sintaksisi to'g'ri", True)
except SyntaxError as e:
    check(f"webapp_api.py sintaksisi buzilgan: {e}", False)
    src = ""

# ---------- 2. webapp_api.py dagi muhim funksiyalar ----------
required_defs = [
    "validate_webapp_init_data", "validate_login_widget", "make_session_token",
    "verify_session_token", "require_auth", "require_admin",
    "drivers_search", "create_order", "driver_register", "driver_me",
    "driver_set_status", "driver_add_routes", "driver_clear_routes",
    "submit_ad", "admin_ads_pending", "admin_ads_approve", "admin_ads_reject",
    "admin_set_monetization", "admin_broadcast", "register_webapp_routes",
]
for name in required_defs:
    check(f"webapp_api.py: '{name}' mavjud", f"def {name}(" in src)

# ---------- 3. Haqiqiy database.py funksiyalarini chaqirayotgani (mos kelish tekshiruvi) ----------
real_db_calls = [
    "db.search_active_trip_drivers", "db.get_matching_driver_ids_from_trips",
    "db.can_add_more_routes", "db.count_recent_orders", "db.has_pending_service_ad",
    "db.save_service_payment", "db.activate_service_ad_once", "db.reject_service_ad_once",
    "db.grant_grace_days_to_all_drivers", "db.cancel_active_trip_for_driver",
]
for call in real_db_calls:
    check(f"webapp_api.py: '{call}' chaqirilgan", call in src)

# ---------- 4. database.py ga tegilmaganini tasdiqlash ----------
db_src = open("database.py", encoding="utf-8").read() if os.path.exists("database.py") else ""
check("database.py da 'get_pending_service_ads' YO'Q (biz qo'shmadik, to'g'ri)", "async def get_pending_service_ads" not in db_src)
check("database.py da asl 'activate_service_ad_once' bor (o'zgarmagan)", "async def activate_service_ad_once" in db_src)

# ---------- 5. index.html ----------
html_path = "webapp/dist/index.html"
if os.path.exists(html_path):
    html = open(html_path, encoding="utf-8").read()
    check("index.html: <div id=\"root\"> mavjud", 'id="root"' in html)
    check("index.html: bundle.js to'g'ri yo'lda ulangan", '/app/static/bundle.js' in html)
    check("index.html: Telegram WebApp SDK ulangan", 'telegram-web-app.js' in html)
else:
    check("webapp/dist/index.html topilmadi", False)

# ---------- 6. bundle.js ----------
bundle_path = "webapp/dist/bundle.js"
if os.path.exists(bundle_path):
    size = os.path.getsize(bundle_path)
    check(f"bundle.js mavjud ({size:,} bayt)", size > 100_000)
    with open(bundle_path, "rb") as f:
        content = f.read()
    text = content.decode("utf-8", errors="replace")
    check("bundle.js: 'createRoot' bor (React to'g'ri build bo'lgan)", "createRoot" in text)
    check("bundle.js: hal qilinmagan require() yo'q", "require(" not in text)
    check("bundle.js UTF-8 sifatida to'g'ri o'qiladi (buzilmagan)", "\ufffd" not in text[:2000] and "\ufffd" not in text[-2000:])
else:
    check("webapp/dist/bundle.js topilmadi — avval uni joylashtiring", False)

# ---------- 7. main.py ulanishlari ----------
main_src = open("main.py", encoding="utf-8").read() if os.path.exists("main.py") else ""
check("main.py: webapp_api import qilingan", "from webapp_api import register_webapp_routes" in main_src)
check("main.py: register_webapp_routes chaqirilgan", "register_webapp_routes(app, bot)" in main_src)

# ---------- 8. keyboards.py / config.py ulanishlari ----------
kb_src = open("keyboards.py", encoding="utf-8").read() if os.path.exists("keyboards.py") else ""
check("keyboards.py: WebAppInfo import qilingan", "WebAppInfo" in kb_src)
check("keyboards.py: webapp_url parametri get_main_menu da bor", "webapp_url" in kb_src)

cfg_src = open("config.py", encoding="utf-8").read() if os.path.exists("config.py") else ""
check("config.py: WEBAPP_URL mavjud", "WEBAPP_URL" in cfg_src)

hnd_src = open("handlers.py", encoding="utf-8").read() if os.path.exists("handlers.py") else ""
check("handlers.py: render_user_menu webapp_url uzatadi", "webapp_url=WEBAPP_URL" in hnd_src)

# ---------- 9. To'liq import qilish tekshiruvi (module sifatida yuklanadimi) ----------
try:
    sys.path.insert(0, ".")
    import importlib
    if "webapp_api" in sys.modules:
        importlib.reload(sys.modules["webapp_api"])
    else:
        importlib.import_module("webapp_api")
    check("webapp_api.py Python modul sifatida muvaffaqiyatli yuklandi (import xatosi yo'q)", True)
except Exception as e:
    check(f"webapp_api.py import qilishda xato: {type(e).__name__}: {e}", False)

print()
if ok:
    print("🎯 BARCHA TEKSHIRUVLAR MUVAFFAQIYATLI O'TDI.")
else:
    print("⚠️ Ba'zi tekshiruvlar muvaffaqiyatsiz — yuqoridagi ❌ belgilarini ko'rib chiqing.")
