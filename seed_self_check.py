# -*- coding: utf-8 -*-
"""
seed_self_check.py — Добавляет 30 Self Check вопросов через дашборд (как админ).

Полный реальный HTTP-флоу через Django test Client (все middleware):
  1. POST /login/          (user=8, админ "Joha")
  2. POST /lock/           (пароль дашборда)
  3. GET  /dashboard/      (проверка, что панель работает)
  4. POST /dashboard/ai-translate/  (перевод uz/ru/en через DeepSeek)
  5. POST /dashboard/self-check/create/ × 30 (с картинками и "(T)"-маркером)

Запуск: python seed_self_check.py
"""
import io
import json
import os
import sys
import time

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "src.settings")

import django

django.setup()

from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.urls import reverse
from PIL import Image, ImageDraw

from core.models import SelfAnswer, SelfQuestion

ADMIN_ID = "8"
ADMIN_PASS = "1"
AI_CHUNK = 30  # элементов на один вызов ai_translate

# ── Генерация PNG-картинок ────────────────────────────────────────────────

def make_png(color_a, color_b, shape, size=(400, 300)):
    """Градиент + геометрическая фигура (shield/lock/key/alert/globe/envelope/bug/check)."""
    img = Image.new("RGB", size)
    draw = ImageDraw.Draw(img)
    w, h = size
    # Вертикальный градиент
    for y in range(h):
        t = y / h
        r = int(color_a[0] * (1 - t) + color_b[0] * t)
        g = int(color_a[1] * (1 - t) + color_b[1] * t)
        b = int(color_a[2] * (1 - t) + color_b[2] * t)
        draw.line([(0, y), (w, y)], fill=(r, g, b))
    cx, cy = w // 2, h // 2
    white = (255, 255, 255)
    if shape == "shield":
        draw.polygon([(cx, 40), (cx + 90, 90), (cx + 90, cy + 60),
                      (cx, h - 30), (cx - 90, cy + 60), (cx - 90, 90)], outline=white, width=6)
    elif shape == "lock":
        draw.rectangle([cx - 40, cy - 60, cx + 40, cy + 60], outline=white, width=6)
        draw.arc([cx - 30, cy - 130, cx + 30, cy - 50], start=180, end=360, fill=white, width=6)
        draw.ellipse([cx - 8, cy - 12, cx + 8, cy + 4], fill=white)
    elif shape == "key":
        draw.ellipse([cx - 90, cy - 30, cx - 30, cy + 30], outline=white, width=6)
        draw.line([(cx - 60, cy), (cx + 60, cy)], fill=white, width=8)
        draw.line([(cx + 30, cy), (cx + 30, cy + 40)], fill=white, width=8)
        draw.line([(cx + 60, cy), (cx + 60, cy + 30)], fill=white, width=8)
    elif shape == "alert":
        draw.polygon([(cx, 30), (cx + 100, h - 40), (cx - 100, h - 40)], outline=white, width=6)
        draw.rectangle([cx - 6, cy - 50, cx + 6, cy - 10], fill=white)
        draw.ellipse([cx - 8, cy - 2, cx + 8, cy + 14], fill=white)
    elif shape == "globe":
        draw.ellipse([cx - 80, cy - 80, cx + 80, cy + 80], outline=white, width=6)
        draw.ellipse([cx - 30, cy - 80, cx + 30, cy + 80], outline=white, width=4)
        draw.line([(cx - 80, cy), (cx + 80, cy)], fill=white, width=4)
    elif shape == "envelope":
        draw.rectangle([40, 70, w - 40, h - 70], outline=white, width=6)
        draw.line([(40, 70), (cx, cy), (w - 40, 70)], fill=white, width=6)
    elif shape == "bug":
        draw.ellipse([cx - 50, cy - 60, cx + 50, cy + 60], outline=white, width=6)
        draw.line([(cx, cy - 60), (cx, cy + 60)], fill=white, width=4)
        for dx in (-18, 18):
            draw.line([(cx + dx, cy - 30), (cx + dx * 2, cy - 60)], fill=white, width=5)
    else:  # check
        draw.ellipse([cx - 70, cy - 70, cx + 70, cy + 70], outline=white, width=6)
        draw.line([(cx - 35, cy), (cx - 5, cy + 30), (cx + 40, cy - 25)], fill=white, width=8)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf.read()


def up(name, png):
    return SimpleUploadedFile(name, png, content_type="image/png")


# ── Вопросы: 30 шт, тема "базовые навыки кибербезопасности" ────────────────
# a.img задаёт цветовую пару для картинки ответа; q.img — для картинки вопроса.
C = {
    "blue":   ((30, 58, 138), (59, 130, 246)),
    "teal":   ((6, 78, 59), (16, 185, 129)),
    "red":    ((127, 29, 29), (239, 68, 68)),
    "purple": ((88, 28, 135), (168, 85, 247)),
    "gold":   ((146, 64, 14), (234, 179, 8)),
    "slate":  ((15, 23, 42), (71, 85, 105)),
    "green":  ((20, 83, 45), (34, 197, 94)),
    "cyan":   ((8, 51, 68), (34, 211, 238)),
}

QUESTIONS = [
    {"q": "Kiberxavfsizlik nima?", "img": ("shield", C["blue"]),
     "a": [("Axborot tizimlari va tarmoqlarni raqamli tahdidlardan himoya qilish amaliyoti", True, ("check", C["green"])),
           ("Faqat antivirus dasturini o'rnatish", False, None),
           ("Kompyuter o'yinlarini xavfsiz o'ynash", False, None),
           ("Internetdan foydalanishni butunlay taqiqlash", False, None)]},

    {"q": "Quyidagi parollardan qaysi biri eng ishonchli?", "img": None,
     "a": [("123456", False, None),
           ("qwerty", False, None),
           ("Katta va kichik harflar, raqamlar va belgilar aralashgan uzun parol", True, ("lock", C["gold"])),
           ("Tug'ilgan sana", False, None)]},

    {"q": "Fishing (phishing) nima?", "img": ("envelope", C["red"]),
     "a": [("Soxta xatlar yoki saytlar orqali maxfiy ma'lumotlarni o'g'irlash usuli", True, None),
           ("Baliq ovlash sport turi", False, None),
           ("Antivirus dasturi turi", False, None),
           ("Fayllarni shifrlash usuli", False, None)]},

    {"q": "Ikki bosqichli autentifikatsiya (2FA) nima?", "img": None,
     "a": [("Paroldan tashqari qo'shimcha tasdiqlash qadami (SMS kod yoki ilova)", True, ("check", C["teal"])),
           ("Parolni ikki marta kiritish", False, None),
           ("Ikkita akkaunt ochish", False, None),
           ("Wi-Fi parolini har kuni almashtirish", False, None)]},

    {"q": "Zararli dastur (malware) nima?", "img": ("bug", C["red"]),
     "a": [("Ma'lumotlarni o'g'irlash yoki zarar yetkazish uchun yaratilgan dastur", True, None),
           ("Sekin ishlaydigan dastur", False, None),
           ("Eski dastur versiyasi", False, None),
           ("Bepul tarqatiladigan dastur", False, None)]},

    {"q": "Shubhali elektron xat kelganda nima qilish kerak?", "img": None,
     "a": [("Havolalarni darhol bosib tekshirish", False, None),
           ("Havolalarni ochmaslik va xavfsizlik xizmatiga xabar berish", True, ("alert", C["gold"])),
           ("Xatga javob yozish", False, None),
           ("Xatni barcha tanishlarga yuborish", False, None)]},

    {"q": "Antivirus dasturi qanday vazifani bajaradi?", "img": None,
     "a": [("Zararli dasturlarni aniqlaydi, bloklaydi va o'chiradi", True, None),
           ("Internet tezligini oshiradi", False, None),
           ("Kompyuterni jismoniy sovutadi", False, None),
           ("Fayllarni avtomatik siqadi", False, None)]},

    {"q": "Ommaviy Wi-Fi tarmog'idan foydalanishda qanday xavf bor?", "img": ("globe", C["cyan"]),
     "a": [("Trafikni ushlab qolish va ma'lumotlarni o'g'irlash", True, None),
           ("Internet tezligi past bo'lishi", False, None),
           ("Reklamalar ko'p chiqishi", False, None),
           ("Hech qanday xavf yo'q", False, None)]},

    {"q": "Ransomware (to'lov talab qiluvchi dastur) nima?", "img": ("lock", C["purple"]),
     "a": [("Fayllaringizni shifrlab, qaytarish evaziga to'lov talab qiladigan dastur", True, ("lock", C["red"])),
           ("Bepul antivirus dasturi", False, None),
           ("Kompyuterni tezlashtiruvchi dastur", False, None),
           ("Onlayn o'yin dasturi", False, None)]},

    {"q": "Kuchli parol yaratish qoidalaridan biri qaysi?", "img": None,
     "a": [("Har bir xizmat uchun alohida va murakkab parol ishlatish", True, None),
           ("Barcha akkauntlar uchun bir xil parol", False, None),
           ("Qisqa va eslab qolish oson parol", False, None),
           ("Ism-sharifdan parol yasash", False, None)]},

    {"q": "Ijtimoiy injeneriya nima?", "img": None,
     "a": [("Insonlarni aldash orqali maxfiy ma'lumotlarni olish usuli", True, None),
           ("Dasturlash tili", False, None),
           ("Tarmoq protokoli", False, None),
           ("Shifrlash algoritmi", False, None)]},

    {"q": "VPN nima uchun ishlatiladi?", "img": ("globe", C["blue"]),
     "a": [("Internet-trafikni shifrlash va maxfiylikni ta'minlash", True, None),
           ("Kompyuterni sovutish", False, None),
           ("O'yinlarni tezlashtirish", False, None),
           ("Fayllarni o'chirish", False, None)]},

    {"q": "Cookie (kuki) fayllari nima?", "img": None,
     "a": [("Saytlar brauzeringizda saqlaydigan kichik ma'lumot fayllari", True, None),
           ("Shirinlik turi", False, None),
           ("Kompyuter virusi turi", False, None),
           ("Monitor sozlamasi", False, None)]},

    {"q": "HTTPS protokoli HTTP dan nima bilan farq qiladi?", "img": None,
     "a": [("Ma'lumotlar shifrlangan holda uzatiladi", True, ("shield", C["green"])),
           ("Sahifalar tezroq ochiladi", False, None),
           ("Reklamalar ko'rsatilmaydi", False, None),
           ("Faqat telefonlar uchun mo'ljallangan", False, None)]},

    {"q": "Ma'lumotlarning zaxira nusxasini (backup) yaratish nima uchun kerak?", "img": None,
     "a": [("Ma'lumot yo'qolgan yoki zararlangan holatda tiklash uchun", True, None),
           ("Kompyuterni tezlashtirish uchun", False, None),
           ("Internet tezligini oshirish uchun", False, None),
           ("Ekran yorqinligini sozlash uchun", False, None)]},

    {"q": "Spam xabarlar nima?", "img": None,
     "a": [("Ommaviy yuboriladigan keraksiz yoki reklama xabarlari", True, None),
           ("Muhim davlat xabarlari", False, None),
           ("Shifrlangan maxfiy xatlar", False, None),
           ("Tizim yangilanishlari", False, None)]},

    {"q": "Telefon ekran qulfi (PIN yoki parol) nima uchun kerak?", "img": ("lock", C["teal"]),
     "a": [("Qurilmaga ruxsatsiz kirishni oldini olish uchun", True, None),
           ("Ekranni chiroyli ko'rsatish uchun", False, None),
           ("Batareyani tejash uchun", False, None),
           ("Xotirani ko'paytirish uchun", False, None)]},

    {"q": "Ilovalarni qayerdan yuklab olish xavfsizroq?", "img": None,
     "a": [("Rasmiy do'konlardan (App Store, Google Play)", True, ("check", C["blue"])),
           ("Noma'lum saytlardan", False, None),
           ("Ijtimoiy tarmoqlardagi havolalardan", False, None),
           ("Torrent saytlardan", False, None)]},

    {"q": "DDoS hujum nima?", "img": None,
     "a": [("Serverni juda ko'p so'rovlar bilan to'ldirib ishdan chiqarish", True, None),
           ("Antivirus bazasini yangilash", False, None),
           ("Parolni tiklash jarayoni", False, None),
           ("Fayllarni nusxalash", False, None)]},

    {"q": "Shifrlash (encryption) nima?", "img": ("key", C["gold"]),
     "a": [("Ma'lumotni faqat kalit egalari o'qiy oladigan shaklga aylantirish", True, ("key", C["purple"])),
           ("Faylni butunlay o'chirish", False, None),
           ("Faylni boshqa papkaga nusxalash", False, None),
           ("Internet tezligini oshirish", False, None)]},

    {"q": "Bank xodimi qo'ng'iroq qilib SMS-kodni so'rasa nima qilasiz?", "img": None,
     "a": [("Kodni hech qachon aytmaysiz va qo'ng'iroqni tugatasiz", True, ("alert", C["red"])),
           ("Kodni darhol aytasiz", False, None),
           ("Kodni SMS orqali yuborasiz", False, None),
           ("Kodning yarmini aytasiz", False, None)]},

    {"q": "Firewall (xavfsizlik devori) nima?", "img": None,
     "a": [("Tarmoq trafigini nazorat qiluvchi himoya tizimi", True, None),
           ("Dasturlash tili", False, None),
           ("Kompyuter o'yini turi", False, None),
           ("Brauzer kengaytmasi", False, None)]},

    {"q": "Noma'lum fleshka topib olsangiz nima qilasiz?", "img": None,
     "a": [("Kompyuterga ulamaysiz va xavfsizlik xizmatiga topshirasiz", True, None),
           ("Darhol kompyuterga ulaysiz", False, None),
           ("Ichidagi fayllarni ochasiz", False, None),
           ("Do'stingizga berasiz", False, None)]},

    {"q": "Parollarni qanchalik tez-tez yangilash tavsiya etiladi?", "img": None,
     "a": [("Muntazam ravishda, ayniqsa shubhali holatdan keyin darhol", True, None),
           ("Hech qachon yangilash shart emas", False, None),
           ("Har 10 yilda bir marta", False, None),
           ("Faqat tug'ilgan kunda", False, None)]},

    {"q": "Brauzerda \"Kompyuteringiz virus bilan zararlangan\" degan oynachalar chiqsa nima qilasiz?", "img": ("alert", C["red"]),
     "a": [("Bu ko'pincha soxta ogohlantirish — hech narsani bosmasdan oynani yopasiz", True, None),
           ("Darhol ko'rsatilgan tugmani bosasiz", False, None),
           ("Telefon raqamingizni kiritasiz", False, None),
           ("To'lov qilasiz", False, None)]},

    {"q": "Ijtimoiy tarmoqlarda shaxsiy ma'lumotlarni qancha joylash xavfsiz?", "img": None,
     "a": [("Iloji boricha kam — manzil, telefon va hujjat raqamlarini joylamang", True, ("shield", C["blue"])),
           ("Barcha ma'lumotlarni joylasangiz bo'ladi", False, None),
           ("Faqat uy manzilini", False, None),
           ("Faqat telefon raqamini", False, None)]},

    {"q": "Kiberbullying (internetda ta'qib qilish) nima?", "img": None,
     "a": [("Internet orqali kimnidir haqoratlash yoki ta'qib qilish", True, None),
           ("Onlayn o'yin turi", False, None),
           ("Dastur yangilash jarayoni", False, None),
           ("Ijtimoiy tarmoq funksiyasi", False, None)]},

    {"q": "Ochiq manbali dastur (open source) nima?", "img": None,
     "a": [("Manba kodi ochiq va istalgan kishi tekshira oladigan dastur", True, None),
           ("Bepul internet xizmati", False, None),
           ("Yopiq tarmoq turi", False, None),
           ("Antivirus dasturi turi", False, None)]},

    {"q": "2FA da SMS-kod o'rniga yana nimadan foydalanish mumkin?", "img": None,
     "a": [("Autentifikator ilova yoki apparat kalit (YubiKey)", True, None),
           ("Ikkinchi telefon raqamini yozish", False, None),
           ("Elektron pochta parolini aytish", False, None),
           ("Brauzer tarixini tozalash", False, None)]},

    {"q": "Kiberxavfsizlik madaniyatining asosiy qoidasi qaysi?", "img": ("shield", C["slate"]),
     "a": [("Har bir foydalanuvchi xavfsizlikka mas'ul — shubhali narsani ochishdan oldin o'ylang", True, None),
           ("Xavfsizlik faqat IT bo'limining ishi", False, None),
           ("Parolsiz ishlash mumkin", False, None),
           ("Har qanday havolani bosish mumkin", False, None)]},
]

assert len(QUESTIONS) == 30, f"expected 30 questions, got {len(QUESTIONS)}"


def main():
    client = Client()

    # ── 1. Логин как админ ──────────────────────────────────────────────
    r = client.get(reverse("login"))
    assert r.status_code == 200, f"GET /login/ -> {r.status_code}"
    r = client.post(reverse("login"), {"user": ADMIN_ID})
    assert r.status_code == 302, f"POST /login/ -> {r.status_code}"
    assert r.url == reverse("lock"), f"expected redirect to lock, got {r.url}"
    print("[1/6] Login OK -> redirect to /lock/")

    # ── 2. Пароль дашборда (lock) ────────────────────────────────────────
    r = client.get(reverse("lock"))
    assert r.status_code == 200, f"GET /lock/ -> {r.status_code}"
    r = client.post(reverse("lock"), {"pass": ADMIN_PASS})
    assert r.status_code == 302, f"POST /lock/ -> {r.status_code}"
    assert r.url == reverse("dashboard"), f"expected redirect to dashboard, got {r.url}"
    print("[2/6] Lock OK -> dashboard authorized")

    # ── 3. Дашборд работает ──────────────────────────────────────────────
    r = client.get(reverse("dashboard"))
    assert r.status_code == 200, f"GET /dashboard/ -> {r.status_code}"
    print("[3/6] Dashboard OK (200)")

    # ── 4. AI-перевод всех текстов ───────────────────────────────────────
    items = []
    for i, q in enumerate(QUESTIONS):
        items.append({"id": f"q{i}", "text": q["q"]})
        for j, a in enumerate(q["a"]):
            items.append({"id": f"q{i}a{j}", "text": a[0]})
    print(f"[4/6] Translating {len(items)} items via ai_translate...")

    translations = {}
    for start in range(0, len(items), AI_CHUNK):
        chunk = items[start:start + AI_CHUNK]
        cache.delete(f"ai_translate_throttle:{ADMIN_ID}")  # снимаем троттлинг
        r = client.post(
            reverse("ai_translate"),
            data=json.dumps({"items": chunk}),
            content_type="application/json",
        )
        if r.status_code != 200:
            print(f"  ai_translate failed: {r.status_code} {r.content[:200]}")
            sys.exit(1)
        payload = r.json()
        if not payload.get("ok"):
            print(f"  ai_translate error: {payload}")
            sys.exit(1)
        for t in payload["translations"]:
            translations[t["id"]] = t
        missing = payload.get("missing", [])
        print(f"  chunk {start // AI_CHUNK + 1}: {len(chunk)} items, missing={len(missing)}")
        time.sleep(1)

    # ── 5. Создание 30 вопросов через дашборд ────────────────────────────
    created = 0
    for i, q in enumerate(QUESTIONS):
        data = {}
        tr = translations.get(f"q{i}", {})
        data["question_text"] = q["q"]
        data["question_text_uz"] = tr.get("uz") or q["q"]
        data["question_text_ru"] = tr.get("ru") or ""
        data["question_text_en"] = tr.get("en") or ""
        if q["img"]:
            shape, colors = q["img"]
            data["question_image"] = up("q.png", make_png(colors[0], colors[1], shape))

        for j, a in enumerate(q["a"]):
            text, correct, aimg = a
            atr = translations.get(f"q{i}a{j}", {})
            prefix = "(T) " if correct else ""
            data[f"answer_text_{j}"] = prefix + text
            data[f"answer_text_{j}_uz"] = prefix + (atr.get("uz") or text)
            data[f"answer_text_{j}_ru"] = prefix + (atr.get("ru") or text)
            data[f"answer_text_{j}_en"] = prefix + (atr.get("en") or text)
            if correct:
                data[f"answer_correct_{j}"] = "1"
            if aimg:
                shape, colors = aimg
                data[f"answer_image_{j}"] = up("a.png", make_png(colors[0], colors[1], shape))

        r = client.post(reverse("self_check_create"), data)
        if r.status_code != 302:
            print(f"  question {i + 1} FAILED: {r.status_code}")
            continue
        created += 1

    print(f"[5/6] Created {created}/30 questions via dashboard")

    # ── 6. Проверка результата в БД ──────────────────────────────────────
    total_q = SelfQuestion.objects.count()
    total_a = SelfAnswer.objects.count()
    with_img_q = SelfQuestion.objects.filter(img__isnull=False).count()
    with_img_a = SelfAnswer.objects.filter(img__isnull=False).count()
    with_t = SelfAnswer.objects.filter(text_uz__startswith="(T)").count()
    review = SelfQuestion.objects.filter(needs_review=True).count()
    print(f"[6/6] DB check: questions={total_q}, answers={total_a}, "
          f"q_images={with_img_q}, a_images={with_img_a}, "
          f"answers_with_(T)={with_t}, needs_review={review}")
    assert created == 30, "not all questions created"
    print("DONE")


if __name__ == "__main__":
    main()
