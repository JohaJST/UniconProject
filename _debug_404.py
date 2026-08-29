# -*- coding: utf-8 -*-
"""
Репродукция 404 для АВТОРИЗОВАННЫХ пользователей на всех языках.
Проходим: вход, публичные ссылки (с префиксами и без), логаут,
смену языка, защищённые страницы. Фиксируем каждый 404 в цепочке.
"""
import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "src.settings")
import django

django.setup()

from django.test import Client

from core.models import User

users_by_lang = {}
for u in User.objects.filter(is_active=True).exclude(role=1):
    users_by_lang.setdefault(u.lang or "uz", u.id)
print("пользователи по языкам:", users_by_lang)

PUBLIC_URLS = [
    "/", "/login/", "/self/", "/self/check/",
    "/uz/", "/ru/", "/en/",
    "/uz/login/", "/ru/login/", "/en/login/",
    "/uz/self/", "/ru/self/", "/en/self/",
    "/uz/self/check/", "/ru/self/check/", "/en/self/check/",
]

problems = []

for lang, uid in sorted(users_by_lang.items()):
    c = Client(raise_request_exception=False)
    r = c.post("/login/", {"user": str(uid)})
    print(f"\n=== пользователь lang={lang!r} (id={uid}) — вход: {r.status_code} -> {r.headers.get('Location')}")

    for url in PUBLIC_URLS:
        r = c.get(url, follow=True)
        chain = " -> ".join(
            f"{hop_status}@{hop_url}" for hop_url, hop_status in getattr(r, "redirect_chain", [])
        )
        marker = ""
        if r.status_code == 404:
            marker = "  <<<< 404!"
            problems.append((lang, url, chain))
        elif r.status_code >= 500:
            marker = f"  <<<< {r.status_code}!"
            problems.append((lang, url, chain))
        print(f"  {url:24s} -> {r.status_code}{marker}  [{chain}]")

    # статика и медиа НЕ должны уводиться на языковые префиксы
    for url in ["/static/base.css", "/media/nonexist.png", "/i18n/"]:
        r = c.get(url, follow=False)
        loc = r.headers.get("Location") or ""
        bad = "/en/static" in loc or "/uz/static" in loc or "/ru/static" in loc or "/en/media" in loc
        if bad:
            problems.append((lang, url, f"bad redirect -> {loc}"))
        print(f"  {url:24s} -> {r.status_code}  [Location: {loc or '-'}]")

    # защищённые страницы
    for url in ["/test/", "/user/", "/v2/test/"]:
        r = c.get(url, follow=True)
        chain = " -> ".join(f"{s}@{u}" for u, s in getattr(r, "redirect_chain", []))
        if r.status_code == 404 or r.status_code >= 500:
            problems.append((lang, url, chain))
        print(f"  {url:24s} -> {r.status_code}  [{chain}]")

    # смена языка на каждый из трёх, со страницы с префиксом и без
    for target_lang in ["uz", "ru", "en"]:
        for next_url in ["/", "/uz/self/check/"]:
            c2 = Client(raise_request_exception=False)
            c2.post("/login/", {"user": str(uid)})
            r = c2.post(
                "/account/language/",
                {"lang": target_lang, "next": next_url},
                follow=True,
            )
            chain = " -> ".join(f"{s}@{u}" for u, s in getattr(r, "redirect_chain", []))
            if r.status_code == 404 or r.status_code >= 500:
                problems.append((f"{lang}->{target_lang}", next_url, chain))
            print(f"  switch->{target_lang} next={next_url:18s} -> {r.status_code}  [{chain}]")

    # логаут: куда уводит redirect('about')
    r = c.get("/logout/", follow=True)
    chain = " -> ".join(f"{s}@{u}" for u, s in getattr(r, "redirect_chain", []))
    if r.status_code == 404 or r.status_code >= 500:
        problems.append((lang, "/logout/", chain))
    print(f"  /logout/ -> {r.status_code}  [{chain}]")

print()
print("=" * 70)
if problems:
    print("НАЙДЕНЫ ПРОБЛЕМЫ:")
    for p in problems:
        print("  ", p)
else:
    print("404 НЕ НАЙДЕНЫ в этих сценариях")
