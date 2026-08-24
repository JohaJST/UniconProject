# -*- coding: utf-8 -*-
"""
Финальные углублённые проверки безопасности и edge-case'ов.

Покрывает то, чего нет в юнит-тестах и базовом смоук-тесте:
  1. CSRF: POST без токена -> 403, с токеном -> 302.
  2. Тихое обновление: просроченный access + валидный refresh -> 200.
  3. Logout: старый access-токен отвергается (revocation по jti).
  4. Open redirect: /token/refresh/?next=https://evil.com -> редирект на home.
  5. Brute-force на /lock/: 7 неверных паролей -> блокировка.
  6. /lock/: верный пароль -> доступ к дашборду.
  7. edit_potok: мусорная дата и end <= start -> форма с ошибкой (не 500).
  8. XSS: <script> в вопросе рендерится экранированным.
  9. Admin-экспорт (import_export): QuestionResource не падает на удалённых полях.
 10. Финальная сверка чистоты БД (без мусора от тестов).
"""
import hashlib
import json
import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "src.settings")
import django

django.setup()

import jwt
from django.conf import settings
from django.core.cache import cache
from django.test import Client

from core.auth_jwt.services import AuthRedisService
from core.models import Potok, Question, Result, Subject, Test, User, Variant
from core.models.self import SelfAnswer, SelfQuestion

fails, oks = [], []


def check(label, cond, detail=""):
    if cond:
        oks.append(label)
    else:
        fails.append((label, detail))
        print(f"[FAIL] {label}: {detail}")


# ═══ 1. CSRF enforcement ═════════════════════════════════════════════════════
csrf_c = Client(enforce_csrf_checks=True, raise_request_exception=False)
r = csrf_c.post("/login/", {"user": "8"})
check("CSRF: POST без токена -> 403", r.status_code == 403, f"got {r.status_code}")

csrf_c.get("/login/")  # форма кладёт csrftoken в cookie
token = csrf_c.cookies.get("csrftoken")
r = csrf_c.post("/login/", {"user": "8", "csrfmiddlewaretoken": token.value})
check("CSRF: POST с токеном -> 302", r.status_code == 302, f"got {r.status_code}")

# ═══ 2. Тихое обновление access по refresh ══════════════════════════════════
uid, device_id, family_id = 8, "finalcheckdevice", "finalcheckfamily"
AuthRedisService.set_active_session(uid, device_id, "uahash", "127.0.0.0/24")

now = __import__("datetime").datetime.utcnow()
import datetime as _dt

expired_access = jwt.encode({
    "sub": str(uid), "device_id": device_id, "jti": "oldaccessjti",
    "type": "access", "iat": now - _dt.timedelta(hours=1),
    "exp": now - _dt.timedelta(seconds=30),
}, settings.SECRET_KEY, algorithm="HS256")

refresh_token = jwt.encode({
    "sub": str(uid), "device_id": device_id, "family_id": family_id,
    "jti": "refreshjti1", "type": "refresh",
    "iat": now - _dt.timedelta(hours=1),
    "exp": now + _dt.timedelta(hours=1),
}, settings.SECRET_KEY, algorithm="HS256")

AuthRedisService.rotate_refresh_family(
    family_id, hashlib.sha256(refresh_token.encode("utf-8")).hexdigest()
)

refresh_c = Client(raise_request_exception=False)
refresh_c.cookies["access_token"] = expired_access
refresh_c.cookies["refresh_token"] = refresh_token
# /lock/ — защищённый путь без требований к профилю (position/company_name)
r = refresh_c.get("/lock/")
check("Refresh: просроченный access + валидный refresh -> 200",
      r.status_code == 200, f"got {r.status_code} {r.headers.get('Location')}")
check("Refresh: access-токен ротирован (кука обновлена)",
      refresh_c.cookies.get("access_token").value != expired_access)

# ═══ 3. Logout отзывает access-токен (jti) ══════════════════════════════════
lo_c = Client(raise_request_exception=False)
lo_c.post("/login/", {"user": "8"})
old_access = lo_c.cookies.get("access_token").value
lo_c.get("/logout/")

old_c = Client(raise_request_exception=False)
old_c.cookies["access_token"] = old_access
r = old_c.get("/test/")
check("Logout: старый access-токен отвергнут -> редирект на login",
      r.status_code == 302 and r.headers.get("Location", "").endswith("/login/"),
      f"got {r.status_code} {r.headers.get('Location')}")

# ═══ 4. Open redirect на /token/refresh/ ═════════════════════════════════════
or_c = Client(raise_request_exception=False)
or_c.cookies["access_token"] = expired_access
or_c.cookies["refresh_token"] = refresh_token
# после п.2 refresh уже ротировался, но нас интересует только Location
r = or_c.get("/token/refresh/?next=https://evil.com")
loc = (r.headers.get("Location") or "") if r.status_code in (301, 302) else ""
check("Open redirect: next=https://evil.com не прошёл",
      "evil.com" not in loc, f"Location={loc}")

# ═══ 5-6. /lock/: brute-force и корректный пароль (временный админ) ═════════
tmp_admin = User.objects.create_user(
    username="tmp_final_admin", password="FinalPass123", role=2, name="T", last_name="F"
)
AuthRedisService.set_active_session(tmp_admin.id, "lockdevice", "uahash", "127.0.0.0/24")

lock_c = Client(raise_request_exception=False)
lock_c.post("/login/", {"user": str(tmp_admin.id)})

for i in range(7):
    r = lock_c.post("/lock/", {"pass": "wrongpass"})
    if r.status_code >= 500:
        check(f"/lock/: попытка {i + 1} не дала 500", False, f"got {r.status_code}")
        break
else:
    check("/lock/: 7 неверных попыток без 500", True)

r = lock_c.post("/lock/", {"pass": "wrongpass"})
content = r.content.decode("utf-8", "replace")
check("/lock/: после 7 попыток — сообщение о блокировке",
      "Слишком много попыток" in content, f"status {r.status_code}")

# разблокируем и проверяем корректный пароль
cache.delete(AuthRedisService._user_blocked_key(tmp_admin.id))
cache.delete(AuthRedisService._user_attempts_key(tmp_admin.id))
r = lock_c.post("/lock/", {"pass": "FinalPass123"})
check("/lock/: верный пароль -> dashboard",
      r.status_code == 302 and r.headers.get("Location", "").endswith("/dashboard/"),
      f"got {r.status_code} {r.headers.get('Location')}")

# уборка временного админа
AuthRedisService.kick_user(tmp_admin.id)
tmp_admin.delete()

# ═══ 7. edit_potok: кривые даты не дают 500 ═════════════════════════════════
adm_c = Client(raise_request_exception=False)
adm_c.post("/login/", {"user": "8"})
AuthRedisService.authorize_dashboard(8)

r = adm_c.post("/action/edit/potok/1/", {"potok_start": "garbage", "potok_end": "also-garbage"})
check("edit_potok: мусорная дата -> форма с ошибкой (не 500)",
      r.status_code == 200 and "Неверный формат дат" in r.content.decode("utf-8", "replace"),
      f"got {r.status_code}")

r = adm_c.post("/action/edit/potok/1/", {"potok_start": "2026-09-01T09:00", "potok_end": "2026-08-01T09:00"})
check("edit_potok: end <= start -> форма с ошибкой (не 500)",
      r.status_code == 200 and "позже" in r.content.decode("utf-8", "replace"),
      f"got {r.status_code}")

# ═══ 8. XSS: скрипт в вопросе рендерится экранированным ═════════════════════
xss_q = SelfQuestion.objects.create(
    text_uz="<script>alert('xss')</script>", text_ru="x", text_en="x"
)
r = adm_c.get("/dashboard/list/selfquestion/")
html = r.content.decode("utf-8", "replace")
check("XSS: <script> экранирован в списке",
      "<script>alert('xss')</script>" not in html and "&lt;script&gt;" in html)
xss_q.delete()

# ═══ 9. Admin-экспорт не падает на удалённых полях ══════════════════════════
try:
    from core.resource import QuestionResource, TestResource, UserResource

    QuestionResource().export(Question.objects.all())
    TestResource().export(Test.objects.all())
    ds = UserResource().export(User.objects.all())
    check("Admin-экспорт: ресурсы работают без падений", True)
    check("Admin-экспорт: password отсутствует в колонках", "password" not in ds.headers)
except Exception as exc:
    check("Admin-экспорт: ресурсы работают без падений", False, str(exc))

# ═══ 10. Финальная чистота БД ═══════════════════════════════════════════════
expected = {
    "users": 10, "potoks": 4, "subjects": 4, "tests": 5,
    "questions": 17, "variants": 54, "results": 8,
    "selfquestions": 37, "selfanswers": 140,
}
actual = {
    "users": User.objects.count(), "potoks": Potok.objects.count(),
    "subjects": Subject.objects.count(), "tests": Test.objects.count(),
    "questions": Question.objects.count(), "variants": Variant.objects.count(),
    "results": Result.objects.count(),
    "selfquestions": SelfQuestion.objects.count(),
    "selfanswers": SelfAnswer.objects.count(),
}
for k, v in expected.items():
    check(f"БД чистая: {k} == {v}", actual[k] == v, f"got {actual[k]}")

print()
print("=" * 64)
print(f"OK: {len(oks)} проверок, FAIL: {len(fails)}")
for label, detail in fails:
    print(f"  FAIL {label}: {detail}")
print("FINAL CHECKS PASSED" if not fails else "FINAL CHECKS HAVE FAILURES")
