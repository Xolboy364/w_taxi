import json
from itertools import combinations

REGIONS_DATA = {
    "Nukus": [
        "Amudaryo", "Beruniy", "Bo‘zatov", "Chimboy", "Ellikqal’a",
        "Kegeyli", "Mo‘ynoq", "Nukus tumani", "Qanliko‘l", "Qo‘ng‘irot",
        "Qorao‘zak", "Shumanay", "Taxtako‘pir", "To‘rtko‘l", "Xo‘jayli"
    ],
    "Andijon": [
        "Andijon tumani", "Asaka", "Baliqchi", "Bo‘ston", "Buloqboshi",
        "Izboskan", "Jalaquduq", "Xo‘jaobod", "Marhamat", "Oltinko‘l",
        "Paxtaobod", "Qo‘rg‘ontepa", "Shahrixon", "Ulug‘nor"
    ],
    "Buxoro": [
        "Olot", "Buxoro tumani", "G‘ijduvon", "Jondor", "Kogon",
        "Qorako‘l", "Qorovulbozor", "Peshku", "Romitan", "Shofirkon", "Vobkent"
    ],
    "Farg‘ona": [
        "Bag‘dod", "Beshariq", "Buvayda", "Dang‘ara", "Farg‘ona tumani",
        "Furqat", "Oltiariq", "Quva", "Qo‘shtepa", "Rishton",
        "So‘x", "Toshloq", "Uchko‘prik", "Uzbekistan", "Yozyovon"
    ],
    "Jizzax": [
        "Arnasoy", "Baxmal", "Do‘stlik", "Forish", "Jizzax tumani",
        "Mirzacho‘l", "Paxtakor", "Yangiobod", "Zafarobod", "Zarbdor"
    ],
    "Qarshi": [
        "Chiroqchi", "Dehqonobod", "G‘uzor", "Kasbi", "Kitob",
        "Koson", "Mirishkor", "Muborak", "Nishon", "Qamashi",
        "Qarshi tumani", "Shahrisabz", "Yakkabog‘"
    ],
    "Navoiy": [
        "Kanimex", "Karman", "Navoiy tumani", "Nurota",
        "Qiziltepa", "Tomdi", "Uchquduq", "Xatirchi"
    ],
    "Namangan": [
        "Chortoq", "Chust", "Kosonsoy", "Mingbuloq", "Namangan tumani",
        "Norin", "Pop", "To‘raqo‘rg‘on", "Uchqo‘rg‘on", "Uychi", "Yangiqo‘rg‘on"
    ],
    "Samarqand": [
        "Bulung‘ur", "Ishtixon", "Jomboy", "Kattaqo‘rg‘on", "Narpay",
        "Nurobod", "Oqdaryo", "Paxtachi", "Payariq", "Pastdarg‘om",
        "Qo‘shrabot", "Samarqand tumani", "Toyloq", "Urgut"
    ],
    "Termiz": [
        "Angor", "Bandixon", "Boysun", "Denov", "Jarqo‘rg‘on",
        "Muzrabot", "Oltinsoy", "Qiziriq", "Qumqo‘rg‘on", "Sariosiyo",
        "Sherobod", "Sho‘rchi", "Termiz tumani", "Uzun"
    ],
    "Guliston": [
        "Boyovut", "Guliston tumani", "Mirzaobod", "Oqoltin",
        "Sayxunobod", "Sirdaryo", "Xovos"
    ],
    "Nurafshon": [
        "Angren", "Bekobod", "Bo‘ka", "Bo‘stonliq", "Chinoz",
        "Keles", "Qibray", "O‘rta Chirchiq", "Parkent", "Piskent",
        "Quyi Chirchiq", "Toshkent tumani", "Yangiyo‘l", "Yuqori Chirchiq", "Zangiota"
    ],
    "Urganch": [
        "Bog‘ot", "Gurlan", "Hazorasp", "Qo‘shko‘pir", "Shovot",
        "Tuproqqal’a", "Urganch tumani", "Xiva", "Xonqa", "Yangiariq", "Yangibozor"
    ]
}

def generate_routes(type_filter=None):
    routes = []
    centers = list(REGIONS_DATA.keys())

    if type_filter in (None, 1):
        for c1, c2 in combinations(centers, 2):
            routes.append({"from": c1, "to": c2, "type": 1})

    if type_filter in (None, 2):
        for center, districts in REGIONS_DATA.items():
            for dist in districts:
                routes.append({"from": dist, "to": center, "type": 2})

    if type_filter in (None, 3):
        for center, districts in REGIONS_DATA.items():
            for d1, d2 in combinations(districts, 2):
                routes.append({"from": d1, "to": d2, "type": 3})

    if type_filter in (None, 4):
        for center, districts in REGIONS_DATA.items():
            for dist in districts:
                routes.append({"from": dist, "to": "Toshkent", "type": 4})

    return routes

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Yo'nalishlar ma'lumotlarini generatsiya qilish")
    parser.add_argument("--type", type=int, choices=[1, 2, 3, 4], help="Faqat ma'lum bitta turni olish")
    parser.add_argument("--output", type=str, default="routes.json", help="Chiqish JSON fayli nomi")
    args = parser.parse_args()

    data = generate_routes(type_filter=args.type)

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"[+] Jami yo'nalishlar soni: {len(data)}")
    print(f"[+] Saqlandi: {args.output}")
