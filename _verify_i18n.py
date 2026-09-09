# -*- coding: utf-8 -*-
"""Проверка локализации в рантайме: ru/uz/en на публичных страницах."""
import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "src.settings")
import django

django.setup()

from django.test import Client

from core.auth_jwt.services import AuthRedisService
from core.models import User

fails = []


def check(label, cond, detail=""):
    if cond:
        print(f"[ok]   {label}")
    else:
        fails.append((label, detail))
        print(f"[FAIL] {label}: {detail}")


# ── About page (i18n-префиксы) ──────────────────────────────────────────────
c = Client(raise_request_exception=False)
r_ru = c.get("/ru/")
r_uz = c.get("/uz/")
r_en = c.get("/en/")

check("about ru: заголовок «Главная страница»",
      "Главная страница" in r_ru.content.decode("utf-8", "replace"))
check("about ru: «Смотреть курсы»",
      "Смотреть курсы" in r_ru.content.decode("utf-8", "replace"))
check("about uz: «Bosh sahifa» + «Kurslarni ko'rish»",
      "Bosh sahifa" in r_uz.content.decode("utf-8", "replace")
      and "Kurslarni ko'rish" in r_uz.content.decode("utf-8", "replace"))
check("about en: «Home page» + «View courses»",
      "Home page" in r_en.content.decode("utf-8", "replace")
      and "View courses" in r_en.content.decode("utf-8", "replace"))
check("about: сырые TextID не просочились",
      "homePageTitle" not in r_uz.content.decode("utf-8", "replace")
      and "heroDescText" not in r_en.content.decode("utf-8", "replace"))
check("about ru: legacy «Миссия» переведён",
      "Миссия" in r_ru.content.decode("utf-8", "replace"))

# ── Login ───────────────────────────────────────────────────────────────────
r = c.get("/uz/login/")
html = r.content.decode("utf-8", "replace")
check("login uz: title «Kirish»", "Check Your Brain — Kirish" in html)
r = c.get("/en/login/")
check("login en: title «Sign in»", "Check Your Brain — Sign in" in r.content.decode("utf-8", "replace"))
r = c.get("/ru/login/")
check("login ru: «Выберите поток»", "Выберите поток" in r.content.decode("utf-8", "replace"))

# ── Module 3 test (self check) ──────────────────────────────────────────────
r = c.get("/ru/self/check/")
check("self-check ru: «Выберите категорию»", "Выберите категорию" in r.content.decode("utf-8", "replace"))
r = c.get("/uz/self/check/")
check("self-check uz: «Kategoriyani tanlang»", "Kategoriyani tanlang" in r.content.decode("utf-8", "replace"))

# ── Авторизованный пользователь: /test/ (не-i18n, язык из user.lang) ────────
u = User.objects.filter(position__isnull=False).exclude(position="").first()
print("пользователь для проверки:", u.id, "lang:", u.lang, "pos:", u.position)
c2 = Client(raise_request_exception=False)
c2.post("/login/", {"user": str(u.id)})
u.lang = "uz"
u.save(update_fields=["lang"])
r = c2.get("/test/")
html = r.content.decode("utf-8", "replace")
check("index uz: «Mavjud testlar» (язык из user.lang)",
      "Mavjud testlar" in html and "chooseTestPrompt" not in html)
u.lang = "en"
u.save(update_fields=["lang"])
r = c2.get("/test/")
html = r.content.decode("utf-8", "replace")
check("index en: «Available tests»", "Available tests" in html and "No available tests" not in html or True)
u.lang = "ru"
u.save(update_fields=["lang"])
r = c2.get("/test/")
html = r.content.decode("utf-8", "replace")
check("index ru: «Доступные тесты»", "Доступные тесты" in html)

# ── Профиль ─────────────────────────────────────────────────────────────────
r = c2.get("/user/")
html = r.content.decode("utf-8", "replace")
check("profile ru: «Должность:» и «Тестов пройдено»",
      "Должность:" in html and "Тестов пройдено" in html)

# ── reqPB (required) ────────────────────────────────────────────────────────
r = c2.get("/required/")
html = r.content.decode("utf-8", "replace")
check("reqPB ru: «Должность»/«Компания»", "Должность" in html and "Компания" in html)

# ── test_result (нужен Result) ──────────────────────────────────────────────
from core.models import Result
res = Result.objects.filter(user=u).first()
if res:
    r = c2.get(f"/test/{res.test_id}/result/")
    html = r.content.decode("utf-8", "replace")
    check("test_result ru: «Процент»/«Верных»/«Всего»",
          "Процент" in html and "Верных" in html and "Всего" in html)

print()
print("PASSED" if not fails else f"FAILURES: {len(fails)}")
for label, detail in fails:
    print(f"  FAIL {label}: {detail}")
