# -*- coding: utf-8 -*-
"""
Проверка: смена языка у АВТОРИЗОВАННОГО пользователя должна менять
языковой префикс страницы about/self (раньше страница перезагружалась
на старом языке — баг translate_url под неверным активным языком).
"""
import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "src.settings")
import django

django.setup()

from django.test import Client

from core.models import User

fails = []


def check(label, cond, detail=""):
    if not cond:
        fails.append((label, detail))
        print(f"[FAIL] {label}: {detail}")
    else:
        print(f"[ok]   {label}")


def switch_case(user_id, from_url, target_lang, expected_location):
    """Логиним юзера, встаём на from_url, переключаем язык, проверяем Location."""
    c = Client(raise_request_exception=False)
    c.post("/login/", {"user": str(user_id)})
    c.get(from_url)  # "находимся" на странице

    r = c.post(
        "/account/language/",
        {"lang": target_lang, "next": from_url},
    )
    loc = r.headers.get("Location") or ""
    check(
        f"switch: {from_url} -> {target_lang}  (Location={loc!r})",
        r.status_code == 302 and loc == expected_location,
        f"status={r.status_code} expected {expected_location!r}",
    )

    # убеждаемся, что финальная страница 200 и URL имеет нужный префикс
    u = User.objects.get(id=user_id)
    check(f"  DB lang={target_lang!r}", u.lang == target_lang, f"got {u.lang!r}")

    r2 = c.get(loc, follow=True)
    final_url = getattr(r2, "redirect_chain", [])
    final_url = final_url[-1][0] if final_url else (loc if r2.status_code in (301, 302) else from_url)
    # hmm: после follow финальный URL = последний hop или исходный loc
    check(f"  итог {final_url} -> {r2.status_code}", r2.status_code == 200, f"status={r2.status_code}")
    return c


# Юзер с lang='uz' в БД (id=12) — переключаем во все стороны с /uz/...
for target, exp in [("ru", "/ru/"), ("en", "/en/")]:
    switch_case(12, "/uz/", target, exp)

# Юзер с lang='uz' переключается с /ru/ и /en/ (явный выбор страницы)
switch_case(12, "/ru/", "uz", "/uz/")
switch_case(12, "/en/", "uz", "/uz/")

# self-страницы
switch_case(12, "/uz/self/", "ru", "/ru/self/")
switch_case(12, "/uz/self/check/", "ru", "/ru/self/check/")

# не-i18n страница: префикса не будет
switch_case(12, "/test/", "ru", "/test/")

# краевой случай: user.lang='uz', но сидит на /en/ -> 'ru' должен дать /ru/
switch_case(12, "/en/", "ru", "/ru/")

# юзер с lang='ru' переключается на uz с /ru/
u2 = User.objects.filter(lang="ru", is_active=True).first()
switch_case(u2.id, "/ru/", "uz", "/uz/")

# префиксless '/' (стейловый сценарий): Location будет '/' (translate_url не
# находит префикс), дальше middleware отскочит на /<lang>/
c = Client(raise_request_exception=False)
c.post("/login/", {"user": "12"})
r = c.post("/account/language/", {"lang": "en", "next": "/"})
loc = r.headers.get("Location") or ""
check(f"switch: / -> en (Location={loc!r})", r.status_code == 302 and loc == "/", f"status={r.status_code}")
r2 = c.get(loc, follow=True)
final = getattr(r2, "redirect_chain", [])
final_url = final[-1][0] if final else loc
check(f"  итог / -> en: {final_url} -> {r2.status_code}", final_url == "/en/" and r2.status_code == 200,
      f"final={final_url} status={r2.status_code}")

print()
print("PASSED" if not fails else f"FAILURES: {len(fails)}")
for label, detail in fails:
    print(f"  FAIL {label}: {detail}")
