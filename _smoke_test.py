# -*- coding: utf-8 -*-
"""Смоук-тест всех маршрутов проекта через Django test Client."""
import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "src.settings")
import django

django.setup()

from django.test import Client

from core.models import User
from core.auth_jwt.services import AuthRedisService

fails = []
ok = []


def check(label, resp, expected=None, allow_redirect=True):
    """Фиксируем статус; 500+ или несовпадение с expected — провал."""
    status = resp.status_code
    if expected is not None and status != expected:
        fails.append((label, status, f"expected {expected}"))
        print(f"[FAIL] {label}: {status} (expected {expected})")
        return
    if status >= 500:
        fails.append((label, status, "server error"))
        print(f"[FAIL] {label}: {status}")
        return
    ok.append((label, status))


# ═══ 1. Публичные страницы ═══════════════════════════════════════════════════
pub = Client(raise_request_exception=False)
for url in ["/", "/uz/", "/ru/", "/en/", "/self/", "/uz/self/", "/ru/self/", "/self/check/", "/uz/self/check/", "/login/", "/uz/login/"]:
    check(f"GET {url}", pub.get(url))

# /JustAdmin/ без логина → редирект на админ-логин (302)
check("GET /JustAdmin/", pub.get("/JustAdmin/"), expected=302)

# ═══ 2. Ошибочные входы в логин ══════════════════════════════════════════════
c2 = Client(raise_request_exception=False)
check("POST /login/ user=999 (нет юзера)", c2.post("/login/", {"user": "999"}), expected=200)
c3 = Client(raise_request_exception=False)
check("POST /login/ user=abc (не число)", c3.post("/login/", {"user": "abc"}), expected=200)
c4 = Client(raise_request_exception=False)
check("POST /login/ без поля user", c4.post("/login/", {}), expected=200)
c5 = Client(raise_request_exception=False)
check("POST /login/ user=-1", c5.post("/login/", {"user": "-1"}), expected=200)
c6 = Client(raise_request_exception=False)
check("GET /login/ (аноним)", c6.get("/login/"), expected=200)

# ═══ 3. Админский дашборд ════════════════════════════════════════════════════
admin_c = Client(raise_request_exception=False)
r = admin_c.post("/login/", {"user": "8"})
check("POST /login/ user=8 (админ)", r, expected=302)
print("    access_token выдан:", "access_token" in admin_c.cookies)

# Имитируем успешный /lock/ (то же, что делает view после проверки пароля)
AuthRedisService.authorize_dashboard(8)

check("GET /lock/ (форма пароля)", admin_c.get("/lock/"), expected=200)

dash = [
    "/dashboard/", "/dashboard/subject/", "/dashboard/potok/",
    "/dashboard/user/", "/dashboard/result/",
    "/dashboard/list/subject/", "/dashboard/list/potok/",
    "/dashboard/list/result/", "/dashboard/list/user/",
    "/dashboard/list/quiz/", "/dashboard/list/variant/",
    "/dashboard/list/question/", "/dashboard/list/selfquestion/",
    "/dashboard/list/selfquestion/",
    "/dashboard/list/selfresult/", "/dashboard/list/new/",
    "/dashboard/list/selfctg/",
    "/dashboard/self-check/create/", "/dashboard/self-check/1/edit/",
    "/form/user/",
    "/action/view/selfctg/1/", "/action/edit/selfctg/1/",
    "/action/view/potok/6/", "/action/edit/potok/6/",
    "/action/view/subject/1/", "/action/edit/subject/1/",
    "/action/view/user/8/", "/action/edit/user/8/",
    "/action/view/quiz/1/", "/action/edit/quiz/1/",
]
for url in dash:
    check(f"GET {url}", admin_c.get(url))

# drill-down уровни
check("GET /dashboard/subject/1/", admin_c.get("/dashboard/subject/1/"))
check("GET /dashboard/subject/1/1/", admin_c.get("/dashboard/subject/1/1/"))
check("GET /dashboard/subject/1/1/8/", admin_c.get("/dashboard/subject/1/1/8/"))

    # несуществующие объекты (не должны давать 500)
check("GET /action/view/potok/999/", admin_c.get("/action/view/potok/999/"))
check("GET /action/edit/user/999/", admin_c.get("/action/edit/user/999/"))
check("GET /action/view/selfctg/999/", admin_c.get("/action/view/selfctg/999/"))
check("GET /dashboard/self-check/999/edit/", admin_c.get("/dashboard/self-check/999/edit/"))

# ═══ 4. Студент ══════════════════════════════════════════════════════════════
stud_c = Client(raise_request_exception=False)
r = stud_c.post("/login/", {"user": "2"})
check("POST /login/ user=2 (студент)", r, expected=302)
print("    redirect to:", r.headers.get("Location"))

# Студент с пустыми position/company_name должен уходить на /required/ — это
# штатное поведение (required()), а не баг.
r = stud_c.get("/test/")
print("    GET /test/ ->", r.status_code, r.headers.get("Location"))
if r.status_code == 302 and (r.headers.get("Location") or "").endswith("/required/"):
    ok.append(("GET /test/ (студент) -> /required/", r.status_code))
else:
    check("GET /test/ (студент)", r, expected=200)
check("GET /test/1/", stud_c.get("/test/1/"))
check("GET /test/1/result/", stud_c.get("/test/1/result/"))
check("GET /user/", stud_c.get("/user/"))
check("GET /required/", stud_c.get("/required/"))
check("GET /subject/1/", stud_c.get("/subject/1/"))
# RBAC: студенту в дашборд нельзя
check("GET /dashboard/ (студент)", stud_c.get("/dashboard/"), expected=302)
check("GET /form/user/ (студент)", stud_c.get("/form/user/"), expected=302)
check("GET /action/view/potok/1/ (студент)", stud_c.get("/action/view/potok/1/"), expected=302)

# ═══ 5. Выход ════════════════════════════════════════════════════════════════
check("GET /logout/", stud_c.get("/logout/"), expected=302)
check("GET /logout/ повторно", stud_c.get("/logout/"), expected=302)

# ═══ 6. Полный студенческий flow на временном юзере с профилем ══════════════
from core.models import Potok, User

tmp_stud = User.objects.create_user(
    username="tmp_smoke_student",
    password="x",
    role=4,
    name="Smoke",
    last_name="Tmp",
    position="QA Engineer",
    company_name="Unicon",
    potok_id=6,
)

tmp_c = Client(raise_request_exception=False)
r = tmp_c.post("/login/", {"user": str(tmp_stud.id)})
check("POST /login/ tmp_student", r, expected=302)
check("GET /test/ (профиль заполнен)", tmp_c.get("/test/"), expected=200)
# тест 3 принадлежит потоку 6 — "свой" поток; тест 14 — потоку 9
check("GET /test/3/ (свой поток)", tmp_c.get("/test/3/"), expected=200)
check("POST /test/answer/", tmp_c.post("/test/answer/", {"test_id": "3"}), expected=200)
check("GET /test/14/ (чужой поток)", tmp_c.get("/test/14/"), expected=302)
# POST в чужой тест — должен получить 403, а не создать Result
r = tmp_c.post("/test/14/", data='{"answers": []}', content_type="application/json")
print("    POST /test/14/ ->", r.status_code)
check("POST /test/14/ (чужой поток)", r, expected=403)

# уборка за смоук-тестом
tmp_stud.delete()
print("    temp student removed")

# ═══ 7. Ошибки дашборд-форм (POST, не должно быть 500) ═════════════════════
bad_c = Client(raise_request_exception=False)
bad_c.post("/login/", {"user": "8"})
AuthRedisService.authorize_dashboard(8)

check("POST /form/user/ без данных", bad_c.post("/form/user/", {}), expected=200)
check("POST /form/user/ role=abc", bad_c.post("/form/user/", {"role": "abc"}), expected=200)
check("POST /login/ user=8 повторно (уже вошёл)", bad_c.post("/login/", {"user": "8"}), expected=302)

print()
print("=" * 60)
print(f"OK: {len(ok)} проверок, FAIL: {len(fails)}")
for label, status, why in fails:
    print(f"  FAIL {label}: {status} {why}")
print("SMOKE TEST PASSED" if not fails else "SMOKE TEST HAS FAILURES")
