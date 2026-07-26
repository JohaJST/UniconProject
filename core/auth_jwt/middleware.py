"""
core/auth_jwt/middleware.py
──────────────────────────────
JWTAuthenticationMiddleware — заменяет стандартную session-аутентификацию
Django на аутентификацию по JWT access_token из cookie.

Регистрируется в settings.MIDDLEWARE сразу после CsrfViewMiddleware
(см. Промпт 1) — должен отработать до AuthenticationMiddleware и до
DashboardSecurityMiddleware (который дописывается в следующем шаге).
"""
from urllib.parse import urlencode

from django.conf import settings
from django.shortcuts import redirect
from django.urls import reverse

from core.models import User
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
            # Токена нет вовсе (например, первый визит) — на логин,
            # заодно подчищаем куки на случай "половинчатого" состояния.
            return self._clear_cookies_and_redirect_login()

        # ── 3. Декодируем токен и обрабатываем ошибки ────────────────────
        try:
            payload = decode_token(access_token, token_type="access")
        except TokenExpired:
            # Access протух, но это штатная ситуация — отправляем на рефреш,
            # передавая исходный путь, чтобы вернуть пользователя обратно.
            refresh_url = reverse("token_refresh")
            query = urlencode({"next": request.path})
            return redirect(f"{refresh_url}?{query}")
        except TokenInvalid:
            # Подпись невалидна / формат неверный / не тот тип токена —
            # доверия токену нет, разлогиниваем полностью.
            return self._clear_cookies_and_redirect_login()

        # ── 4. Проверки состояния в Redis ─────────────────────────────────
        if AuthRedisService.is_token_revoked(payload["jti"]):
            return self._clear_cookies_and_redirect_login()

        if not AuthRedisService.validate_session(payload["sub"], payload["device_id"]):
            return self._clear_cookies_and_redirect_login()

        # ── 5. Успех — проставляем пользователя и пропускаем дальше ──────
        # ХОТФИКС: обёрнуто в try/except User.DoesNotExist — токен формально
        # ещё жив (exp не истёк, jti не отозван), но пользователя уже могли
        # удалить из БД. В этом случае доверять токену нельзя — разлогиниваем.
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