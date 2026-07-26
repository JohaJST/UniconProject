"""
core/auth_jwt/middleware.py
──────────────────────────────
JWTAuthenticationMiddleware — заменяет стандартную session-аутентификацию
Django на аутентификацию по JWT access_token из cookie.

DashboardSecurityMiddleware — RBAC + sliding-window таймаут дашборда.
Стоит в конце цепочки (после JWTAuthenticationMiddleware), т.к. ему нужен
уже гарантированно проставленный request.user.
"""
from urllib.parse import urlencode

from django.conf import settings
from django.shortcuts import redirect
from django.urls import reverse

from core.models import User
from core.models.auth import Role
from core.auth_jwt.exceptions import TokenExpired, TokenInvalid
from core.auth_jwt.services import AuthRedisService
from core.auth_jwt.tokens import decode_token

# Публичные пути, не требующие аутентификации. Логин обязателен в списке —
# иначе получим бесконечный редирект login -> login -> ...
_IGNORED_EXACT_PATHS = {"/login/", "/about/", "/self/", "/self/check/"}
_IGNORED_PREFIXES = ("/JustAdmin/",)


class JWTAuthenticationMiddleware:
    """Стандартный Django middleware (init/call-стиль)."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # ── 1. Публичные пути — пропускаем без каких-либо проверок ──────
        if request.path.startswith(_IGNORED_PREFIXES) or request.path in _IGNORED_EXACT_PATHS:
            return self.get_response(request)

        # ── 2. Читаем access_token из cookie ─────────────────────────────
        access_token = request.COOKIES.get(settings.JWT_ACCESS_COOKIE_NAME)
        if not access_token:
            return self._clear_cookies_and_redirect_login()

        # ── 3. Декодируем токен и обрабатываем ошибки ────────────────────
        try:
            payload = decode_token(access_token, token_type="access")
        except TokenExpired:
            refresh_url = reverse("token_refresh")
            query = urlencode({"next": request.path})
            return redirect(f"{refresh_url}?{query}")
        except TokenInvalid:
            return self._clear_cookies_and_redirect_login()

        # ── 4. Проверки состояния в Redis ─────────────────────────────────
        if AuthRedisService.is_token_revoked(payload["jti"]):
            return self._clear_cookies_and_redirect_login()

        if not AuthRedisService.validate_session(payload["sub"], payload["device_id"]):
            return self._clear_cookies_and_redirect_login()

        # ── 5. Успех — проставляем пользователя и пропускаем дальше ──────
        try:
            request.user = User.objects.get(id=payload["sub"])
        except User.DoesNotExist:
            return self._clear_cookies_and_redirect_login()

        return self.get_response(request)

    @staticmethod
    def _clear_cookies_and_redirect_login():
        """Редирект на login с удалением access_token и refresh_token кук."""
        response = redirect("login")
        response.delete_cookie(settings.JWT_ACCESS_COOKIE_NAME)
        response.delete_cookie(settings.JWT_REFRESH_COOKIE_NAME)
        return response


class DashboardSecurityMiddleware:
    """
    Защита панели администратора (дашборд + связанные CRUD-пути:
    /dashboard/, /action/, /form/).

    На вход сюда попадает уже аутентифицированный request.user —
    гарантия даёт JWTAuthenticationMiddleware, отработавшая раньше.

    Обязанности (по порядку):
      1. RBAC — студентам в дашборд входа нет вообще. Проверяется ДО
         Redis, чтобы не тратить обращение к кэшу на заведомый отказ.
      2. Sliding-window таймаут — доступ подтверждается паролем дашборда
         (core/dashboard/home.py: lock) и живёт 600s в Redis-ключе
         user:{user_id}:dashboard_auth.
      3. Если ключ жив — продлеваем окно на ещё 600s (sliding window).

    /lock/ намеренно НЕ входит в _PROTECTED_PREFIXES: иначе получили бы
    бесконечный редирект lock -> lock -> ...
    """

    _PROTECTED_PREFIXES = ("/dashboard/", "/action/", "/form/")

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not request.path.startswith(self._PROTECTED_PREFIXES):
            return self.get_response(request)

        user = request.user

        # ── RBAC: студентам (Role.STUDENT == 4) в дашборд хода нет ───────
        if user.role == Role.STUDENT:
            return redirect("home")

        # ── Sliding-window проверка ───────────────────────────────────────
        if not AuthRedisService.is_dashboard_authorized(user.id):
            return redirect("lock")

        # Пользователь активен — продлеваем окно ещё на 600s.
        AuthRedisService.authorize_dashboard(user.id)

        return self.get_response(request)