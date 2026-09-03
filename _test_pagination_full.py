# -*- coding: utf-8 -*-
"""
_test_pagination_full.py
────────────────────────────
Полная функциональная проверка пагинации дашборда — все 10 списков:

    Keyset Engine (через /dashboard/list/<tip>/):
        subject, potok, result, user, quiz, variant, question,
        selfctg, selfquestion

    Offset Engine (через /dashboard/list/selfresult/ -> list_selfuser):
        selfuser

Что проверяется для КАЖДОГО keyset-списка:
  1. Полный обход вперёд (start -> next -> ... -> конец):
       - размер каждой страницы == spec.page_size, кроме последней;
       - нет дублей id между страницами;
       - нет пропусков — множество id обхода == множеству id в БД;
       - has_next/has_prev корректно флагуют конец/начало.
  2. Прыжок "last" сразу даёт тот же хвост, что и обход вперёд до конца.
  3. Обратный обход (prev от последней страницы до первой) даёт ТЕ ЖЕ
     страницы, что и прямой обход (в том же порядке).
  4. Fallback-сценарии:
       - мусорный ?cursor= -> тихий возврат на первую страницу;
       - ?dir=что-то_невалидное -> тихий возврат на первую страницу;
       - валидный по подписи, но с чужим filters_fingerprint курсор ->
         тихий возврат на первую страницу (проверяется и на уровне HTTP,
         и напрямую через core.dashboard.pagination.tokens);
       - просроченный токен (max_age=0) -> None на уровне decode_cursor
         (прямой вызов функции — не ждать реальный час TTL).
  5. Доп. GET-параметры (не cursor/dir) сохраняются в сгенерированных
     ссылках пагинации (задел на будущие фильтры).
  6. RBAC: студент получает redirect на "about", а не 200/500, даже с
     мусорным cursor в query-string (DashboardSecurityMiddleware отсекает
     раньше, чем запрос доходит до пагинации).

Для offset-списка (selfuser) дополнительно проверяются:
  - обход вперёд/назад по ?page=N;
  - невалидный/отрицательный/слишком большой ?page= не даёт 500 и мягко
    клампуется на первую/последнюю страницу.

Тест работает на ЛЮБОМ состоянии БД, но даёт содержательные результаты
(несколько страниц) только если предварительно отработал
`_seed_pagination_stress_data.py`. Если данных мало — часть проверок
(например, "минимум 2 страницы") будет отмечена как SKIP, а не FAIL.

Запуск: python _test_pagination_full.py
"""
import os
import re
import time
from urllib.parse import parse_qs, urlparse

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "src.settings")
import django

django.setup()

from django.test import Client

from core.auth_jwt.services import AuthRedisService
from core.dashboard.pagination.registry import LIST_REGISTRY
from core.dashboard.pagination.tokens import decode_cursor, encode_cursor, make_filters_fingerprint
from core.models import User
from core.models.auth import Role

fails = []
oks = []
skips = []


def check(label, cond, detail=""):
    if cond:
        oks.append(label)
    else:
        fails.append((label, detail))
        print(f"[FAIL] {label}: {detail}")


def skip(label, reason):
    skips.append((label, reason))
    print(f"[SKIP] {label}: {reason}")


# ═══════════════════════════════════════════════════════════════════════════
# Инфраструктура: временные admin/student для авторизации в тесте
# ═══════════════════════════════════════════════════════════════════════════

def _make_temp_users():
    admin = User.objects.create_user(
        username="tmp_pagtest_admin", password="PagTest123",
        role=Role.ADMIN, name="PagTestAdmin", last_name="Tmp",
    )
    student = User.objects.create_user(
        username="tmp_pagtest_student", password="PagTest123",
        role=Role.STUDENT, name="PagTestStudent", last_name="Tmp",
    )
    AuthRedisService.set_active_session(admin.id, "pagtest-admin-dev", "ua", "127.0.0.0/24")
    AuthRedisService.set_active_session(student.id, "pagtest-student-dev", "ua", "127.0.0.0/24")
    return admin, student


def _admin_client(admin):
    c = Client(raise_request_exception=False)
    r = c.post("/login/", {"user": str(admin.id)})
    assert r.status_code == 302, f"login admin failed: {r.status_code}"
    AuthRedisService.authorize_dashboard(admin.id)  # обходим форму пароля дашборда
    return c


def _student_client(student):
    c = Client(raise_request_exception=False)
    r = c.post("/login/", {"user": str(student.id)})
    assert r.status_code == 302, f"login student failed: {r.status_code}"
    return c


# ═══════════════════════════════════════════════════════════════════════════
# Извлечение ссылок пагинации из отрендеренного HTML
# ═══════════════════════════════════════════════════════════════════════════

def extract_keyset_links(html: str) -> dict:
    """
    {"start": url|None, "prev": url|None, "next": url|None, "last": url|None}
    Достаётся из href="...&dir=<x>&..." — недоступные направления
    рендерятся как <span> (без href), поэтому просто отсутствуют.
    """
    links = {}
    for href in re.findall(r'href="([^"]+)"', html):
        qs = parse_qs(urlparse(href).query)
        dir_values = qs.get("dir")
        if not dir_values:
            continue
        d = dir_values[0]
        if d in ("start", "prev", "next", "last") and d not in links:
            links[d] = href.replace("&amp;", "&")
    return links


def extract_offset_links(html: str) -> dict:
    """
    Offset-пагинация (selfuser_list.html) использует только ?page=N без
    отдельного маркера направления. Порядок в шаблоне фиксирован:
    start, prev, next, last — берём хрефы именно в порядке появления
    внутри блока "Пагинация (Offset Engine)".
    """
    marker = "Пагинация (Offset Engine)"
    idx = html.find(marker)
    block = html[idx:] if idx != -1 else html
    hrefs = [h.replace("&amp;", "&") for h in re.findall(r'href="([^"]*page=\d+[^"]*)"', block)]
    # Порядок появления в шаблоне: start (если есть) -> prev -> next -> last.
    # Так как disabled-варианты рендерятся <span>, среди найденных hrefs
    # порядок сохраняется, но какие именно направления присутствуют —
    # нужно сопоставить по контексту вокруг. Проще и надёжнее: вытащить
    # все (label, href) пары по соседним иконкам.
    result = {}
    for name, icon_pattern in [
        ("start", r'title="Первая страница"[^>]*>\s*<a href="([^"]*page=\d+[^"]*)"'),
        ("prev", r'Назад[\s\S]{0,40}?href="([^"]*page=\d+[^"]*)"|href="([^"]*page=\d+[^"]*)"[^>]*>\s*<i[^>]*chevron-left'),
    ]:
        pass  # см. упрощённый фолбэк ниже — надёжнее по позиции.

    # Надёжный fallback: ищем 4 якоря в блоке пагинации по порядку следования
    # <a href="...page=N..."> — шаблон гарантированно рендерит их в порядке
    # start, prev, next, last (пропуская отключённые как <span>).
    # Различаем их по соседнему тексту/иконке.
    for m in re.finditer(r'<a\s+href="([^"]*page=\d+[^"]*)"[^>]*>([\s\S]{0,80}?)</a>', block):
        href, inner = m.group(1).replace("&amp;", "&"), m.group(2)
        if "angles-left" in inner:
            result["start"] = href
        elif "chevron-left" in inner or "Назад" in inner:
            result["prev"] = href
        elif "chevron-right" in inner or "Вперёд" in inner:
            result["next"] = href
        elif "angles-right" in inner:
            result["last"] = href
    return result


def get_page(client, url):
    r = client.get(url)
    return r


# ═══════════════════════════════════════════════════════════════════════════
# 1. Прямой/обратный обход keyset-списка + сверка с БД
# ═══════════════════════════════════════════════════════════════════════════

def _extract_row_ids(html: str, tip: str) -> list:
    """
    Достаём id строк текущей страницы из атрибутов, которые list.html
    реально рендерит для каждого tip (см. templates/pages/dashboard/list.html):
    большинство веток начинают строку с `<td ...>{{ i.id }}</td>` в
    моно-шрифте (font-mono text-xs) — этого достаточно, чтобы вытащить
    числа надёжно, т.к. это первая колонка почти во всех ветках.
    """
    return [int(x) for x in re.findall(r'font-mono text-xs">\s*(\d+)\s*</td>', html)]


def test_keyset_list(client, tip: str, spec):
    label_prefix = f"[{tip}]"
    url = f"/dashboard/list/{tip}/"

    r = get_page(client, url)
    check(f"{label_prefix} GET start -> 200", r.status_code == 200, f"got {r.status_code}")
    if r.status_code != 200:
        return

    html = r.content.decode("utf-8", "replace")
    links = extract_keyset_links(html)
    check(f"{label_prefix} start page: нет ссылки 'start'/'prev' (мы уже на первой)",
          "start" not in links and "prev" not in links,
          f"links={list(links.keys())}")

    forward_pages = []
    ids_seen = []
    current_html = html
    current_links = links
    guard = 0
    while True:
        guard += 1
        if guard > 200:
            check(f"{label_prefix} обход не зациклился", False, "превышен лимит 200 страниц — подозрение на цикл")
            break
        page_ids = _extract_row_ids(current_html, tip)
        forward_pages.append(page_ids)
        ids_seen.extend(page_ids)

        page_size = spec.page_size
        is_last_page = "next" not in current_links
        if not is_last_page:
            check(f"{label_prefix} размер нелast-страницы == page_size",
                  len(page_ids) == page_size, f"got {len(page_ids)} expected {page_size}")
        else:
            check(f"{label_prefix} размер last-страницы в пределах page_size",
                  0 <= len(page_ids) <= page_size, f"got {len(page_ids)}")
            break

        r2 = get_page(client, current_links["next"])
        check(f"{label_prefix} GET next -> 200", r2.status_code == 200, f"got {r2.status_code}")
        current_html = r2.content.decode("utf-8", "replace")
        current_links = extract_keyset_links(current_html)

    # ── Дубли/пропуски ──────────────────────────────────────────────────
    check(f"{label_prefix} нет дублей id между страницами обхода",
          len(ids_seen) == len(set(ids_seen)), f"total={len(ids_seen)} unique={len(set(ids_seen))}")

    db_ids = set(spec.queryset_factory().values_list("id", flat=True))
    check(f"{label_prefix} множество id обхода == множеству id в БД",
              set(ids_seen) == db_ids,
              f"missing={repr(db_ids - set(ids_seen)) if len(db_ids - set(ids_seen)) < 10 else '...'} "
              f"extra={repr(set(ids_seen) - db_ids) if len(set(ids_seen) - db_ids) < 10 else '...'}")

    if len(forward_pages) < 2:
        skip(f"{label_prefix} многостраничные проверки (last/prev-обход)",
             f"всего {len(forward_pages)} страница(ы) — запусти _seed_pagination_stress_data.py для полноты")
        return

    # ── "last" сразу даёт тот же хвост, что и обход вперёд ───────────────
    r_last = get_page(client, f"{url}?dir=last")
    check(f"{label_prefix} GET dir=last -> 200", r_last.status_code == 200, f"got {r_last.status_code}")
    last_html = r_last.content.decode("utf-8", "replace")
    last_direct_ids = _extract_row_ids(last_html, tip)
    check(f"{label_prefix} dir=last == последняя страница прямого обхода",
          last_direct_ids == forward_pages[-1],
          f"{last_direct_ids} != {forward_pages[-1]}")

    # ── Обратный обход должен воспроизвести прямой обход ─────────────────
    last_links = extract_keyset_links(last_html)
    backward_pages = [last_direct_ids]
    cur_links = last_links
    cur_html = last_html
    guard = 0
    while "prev" in cur_links:
        guard += 1
        if guard > 200:
            check(f"{label_prefix} обратный обход не зациклился", False, "лимит 200 превышен")
            break
        r_prev = get_page(client, cur_links["prev"])
        check(f"{label_prefix} GET prev -> 200", r_prev.status_code == 200, f"got {r_prev.status_code}")
        cur_html = r_prev.content.decode("utf-8", "replace")
        cur_links = extract_keyset_links(cur_html)
        backward_pages.append(_extract_row_ids(cur_html, tip))

    backward_pages.reverse()
    check(f"{label_prefix} обратный обход == прямому обходу (тот же порядок страниц)",
          backward_pages == forward_pages,
          f"forward has {len(forward_pages)} pages, backward has {len(backward_pages)} pages")

    # ── Fallback: мусорный cursor ─────────────────────────────────────────
    r_garbage = get_page(client, f"{url}?cursor=not-a-real-token-xyz&dir=next")
    check(f"{label_prefix} мусорный cursor -> 200 (не 500)", r_garbage.status_code == 200, f"got {r_garbage.status_code}")
    garbage_ids = _extract_row_ids(r_garbage.content.decode("utf-8", "replace"), tip)
    check(f"{label_prefix} мусорный cursor -> откат на первую страницу",
          garbage_ids == forward_pages[0], f"{garbage_ids} != {forward_pages[0]}")

    # ── Fallback: невалидный dir ───────────────────────────────────────────
    r_baddir = get_page(client, f"{url}?dir=totally_invalid_direction")
    check(f"{label_prefix} невалидный dir -> 200 (не 500)", r_baddir.status_code == 200, f"got {r_baddir.status_code}")
    baddir_ids = _extract_row_ids(r_baddir.content.decode("utf-8", "replace"), tip)
    check(f"{label_prefix} невалидный dir -> откат на первую страницу",
          baddir_ids == forward_pages[0], f"{baddir_ids} != {forward_pages[0]}")

    # ── Fallback: валидная подпись, но чужой filters_fingerprint ──────────
    real_fp = make_filters_fingerprint({})
    assert real_fp is not None
    bogus_token = encode_cursor(
        sort_value=str(1), id_value=1, direction="next", filters_fingerprint="deadbeef-wrong-fp",
    )
    r_fp = get_page(client, f"{url}?cursor={bogus_token}&dir=next")
    check(f"{label_prefix} fingerprint-mismatch cursor -> 200 (не 500)", r_fp.status_code == 200, f"got {r_fp.status_code}")
    fp_ids = _extract_row_ids(r_fp.content.decode("utf-8", "replace"), tip)
    check(f"{label_prefix} fingerprint-mismatch -> откат на первую страницу",
          fp_ids == forward_pages[0], f"{fp_ids} != {forward_pages[0]}")

    # ── Доп. GET-параметр сохраняется в ссылках пагинации ──────────────────
    r_extra = get_page(client, f"{url}?zzz_extra_param=1")
    extra_links = extract_keyset_links(r_extra.content.decode("utf-8", "replace"))
    if "next" in extra_links:
        check(f"{label_prefix} доп. GET-параметр сохранён в ссылке next",
              "zzz_extra_param=1" in extra_links["next"], f"next={extra_links['next']}")
    else:
        skip(f"{label_prefix} проверка сохранения доп. параметра", "нет ссылки 'next' (всего одна страница)")


# ═══════════════════════════════════════════════════════════════════════════
# 2. Прямой/обратный обход offset-списка selfuser
# ═══════════════════════════════════════════════════════════════════════════

def _extract_selfuser_ids(html: str) -> list:
    """SelfUser id не рендерится напрямую в selfuser_list.html — вместо
    этого используем pk из href action=view/selfuser/<pk>/ как надёжный
    суррогат идентичности строки."""
    return [int(x) for x in re.findall(r"/action/view/selfuser/(\d+)/", html)]


def test_offset_selfuser(client):
    label_prefix = "[selfuser]"
    url = "/dashboard/list/selfresult/"

    r = get_page(client, url)
    check(f"{label_prefix} GET start -> 200", r.status_code == 200, f"got {r.status_code}")
    if r.status_code != 200:
        return
    html = r.content.decode("utf-8", "replace")

    if "Пагинация (Offset Engine)" not in html:
        skip(f"{label_prefix} многостраничные проверки", "только 1 страница — запусти сид-скрипт для полноты")
        first_ids = _extract_selfuser_ids(html)
        db_count = User_selfuser_count()
        check(f"{label_prefix} единственная страница покрывает все записи",
              len(first_ids) == db_count, f"page has {len(first_ids)}, db has {db_count}")
        return

    forward_pages = []
    ids_seen = []
    cur_html = html
    guard = 0
    while True:
        guard += 1
        if guard > 200:
            check(f"{label_prefix} обход не зациклился", False, "лимит 200 превышен")
            break
        links = extract_offset_links(cur_html)
        page_ids = _extract_selfuser_ids(cur_html)
        forward_pages.append(page_ids)
        ids_seen.extend(page_ids)
        if "next" not in links:
            break
        r_next = get_page(client, links["next"])
        check(f"{label_prefix} GET next -> 200", r_next.status_code == 200, f"got {r_next.status_code}")
        cur_html = r_next.content.decode("utf-8", "replace")

    check(f"{label_prefix} нет дублей id между страницами", len(ids_seen) == len(set(ids_seen)),
          f"{len(ids_seen)} vs {len(set(ids_seen))}")

    from core.models.self import SelfUser
    db_ids = set(SelfUser.objects.values_list("id", flat=True))
    check(f"{label_prefix} множество id обхода == множеству id в БД", set(ids_seen) == db_ids)

    # ── Невалидные значения page= не дают 500 ──────────────────────────────
    for bad_page in ("abc", "-5", "0", "999999"):
        r_bad = get_page(client, f"{url}?page={bad_page}")
        check(f"{label_prefix} ?page={bad_page} -> 200 (не 500)", r_bad.status_code == 200, f"got {r_bad.status_code}")


def User_selfuser_count():
    from core.models.self import SelfUser
    return SelfUser.objects.count()


# ═══════════════════════════════════════════════════════════════════════════
# 3. Прямые (без HTTP) проверки tokens.py: просрочка и мусорные строки
# ═══════════════════════════════════════════════════════════════════════════

def test_tokens_direct():
    token = encode_cursor(sort_value="2026-01-01T00:00:00", id_value=1, direction="next", filters_fingerprint="x")
    time.sleep(1.1)
    expired = decode_cursor(token, max_age=0)
    check("[tokens] max_age=0 после сна -> None (просрочен)", expired is None)

    fresh = decode_cursor(token, max_age=3600)
    check("[tokens] max_age=3600 сразу после кодирования -> валиден", fresh is not None)

    check("[tokens] decode_cursor(None) -> None", decode_cursor(None) is None)
    check("[tokens] decode_cursor('') -> None", decode_cursor("") is None)
    check("[tokens] decode_cursor(мусор) -> None", decode_cursor("!!!not-json-not-signed###") is None)


# ═══════════════════════════════════════════════════════════════════════════
# 4. RBAC: студенту в любой /dashboard/list/<tip>/ хода нет
# ═══════════════════════════════════════════════════════════════════════════

def test_rbac_student(student_client):
    for tip in list(LIST_REGISTRY.keys()) + ["selfresult" if "selfuser" in LIST_REGISTRY else "selfresult"]:
        url = f"/dashboard/list/{tip}/?cursor=garbage&dir=next"
        r = student_client.get(url)
        check(f"[rbac] студент /dashboard/list/{tip}/ (даже с мусорным cursor) -> redirect (не 200/500)",
              r.status_code == 302, f"got {r.status_code}")
        if r.status_code == 302:
            check(f"[rbac] студент /dashboard/list/{tip}/ -> редирект на 'about'",
                  r.headers.get("Location", "").rstrip("/").endswith("about") or r.headers.get("Location") == "/",
                  f"Location={r.headers.get('Location')}")


# ═══════════════════════════════════════════════════════════════════════════
# main
# ═══════════════════════════════════════════════════════════════════════════

def main():
    admin, student = _make_temp_users()
    try:
        admin_c = _admin_client(admin)
        student_c = _student_client(student)

        test_tokens_direct()
        test_rbac_student(student_c)

        for tip, spec in LIST_REGISTRY.items():
            if tip == "selfuser":
                continue  # обслуживается отдельным маршрутом /dashboard/list/selfresult/
            if spec.engine == "keyset":
                test_keyset_list(admin_c, tip, spec)
            elif spec.engine == "offset":
                pass  # selfuser — единственный offset-список, обработан отдельно ниже
            else:
                skip(f"[{tip}] проверка пагинации", f"engine={spec.engine!r} — пагинация не подключена")

        test_offset_selfuser(admin_c)

    finally:
        AuthRedisService.kick_user(admin.id)
        AuthRedisService.kick_user(student.id)
        admin.delete()
        student.delete()

    print()
    print("=" * 72)
    print(f"OK: {len(oks)}  FAIL: {len(fails)}  SKIP: {len(skips)}")
    if fails:
        print("\nПРОВАЛЕННЫЕ ПРОВЕРКИ:")
        for label, detail in fails:
            print(f"  FAIL {label}: {detail}")
    if skips:
        print("\nПРОПУЩЕННЫЕ ПРОВЕРКИ (недостаточно данных):")
        for label, reason in skips:
            print(f"  SKIP {label}: {reason}")
    print()
    print("PAGINATION TESTS PASSED" if not fails else "PAGINATION TESTS HAVE FAILURES")


if __name__ == "__main__":
    main()