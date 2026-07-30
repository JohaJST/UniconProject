"""
core/auth_jwt/middleware.py
──────────────────────────────
JWTAuthenticationMiddleware — заменяет стандартную session-аутентификацию
Django на аутентификацию по JWT access_token из cookie.

DashboardSecurityMiddleware — RBAC + sliding-window таймаут дашборда.
Стоит в конце цепочки (после JWTAuthenticationMiddleware), т.к. ему нужен
уже гарантированно проставленный request.user.
"""

import re

from urllib.parse import urlencode

from django.conf import settings
from django.shortcuts import redirect
from django.urls import reverse

from core.models import User
from core.models.auth import Role
from core.auth_jwt.exceptions import TokenExpired, TokenInvalid, RefreshRace
from core.auth_jwt.services import AuthRedisService
from core.auth_jwt.tokens import decode_token
from core.auth_jwt.refresh_logic import attempt_token_refresh

_IGNORED_EXACT_PATHS = {"/login/", "/", "/about/", "/self/", "/self/check/"}
_IGNORED_PREFIXES = ("/JustAdmin/", "/i18n/")

_LANGUAGE_PREFIX_RE = re.compile(r"^/(uz|ru|en)(/.*)?$")

def _sync_language_cookie(request, response, user):
    """
    Непрерывная ресинхронизация cookie django_language с User.lang.

    Нужна на случай, если lang поменяли в обход change_account_language
    (например, через /JustAdmin/) уже во время активной сессии: следующий
    же запрос к защищённому пути должен подтянуть актуальное значение.
    Кука перезаписывается ТОЛЬКО если значения разошлись — чтобы не
    пересоздавать её на каждой тихой ротации access/refresh токенов.
    """
    desired = user.lang or "uz"
    current = request.COOKIES.get(settings.LANGUAGE_COOKIE_NAME)
    if current == desired:
        return

    response.set_cookie(
        settings.LANGUAGE_COOKIE_NAME,
        desired,
        max_age=settings.JWT_REFRESH_TOKEN_TTL,
        httponly=False,
        secure=settings.JWT_COOKIE_SECURE,
        samesite=settings.JWT_COOKIE_SAMESITE,
    )

class JWTAuthenticationMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        _path = _strip_language_prefix(request.path)
        is_ignored = _path.startswith(_IGNORED_PREFIXES) or _path in _IGNORED_EXACT_PATHS

        if is_ignored:
            # Публичная страница (about/self/login и т.п.): доступ разрешён
            # в любом случае, но если есть валидный access_token — подставляем
            # request.user, чтобы navbar в base.html показывал авторизованное
            # состояние (аватар/ФИО/Выйти), а не всегда "Войти".
            self._try_soft_authenticate(request)
            return self.get_response(request)

        access_token = request.COOKIES.get(settings.JWT_ACCESS_COOKIE_NAME)
        if not access_token:
            return self._clear_cookies_and_redirect_login()

        new_tokens = None

        try:
            payload = decode_token(access_token, token_type="access")
        except TokenExpired:
            refresh_token = request.COOKIES.get(settings.JWT_REFRESH_COOKIE_NAME)
            if not refresh_token:
                return self._clear_cookies_and_redirect_login()

            try:
                new_tokens = attempt_token_refresh(refresh_token)
            except (TokenExpired, TokenInvalid):
                return self._clear_cookies_and_redirect_login()
            except RefreshRace as race:
                p = race.payload
                if not AuthRedisService.validate_session(p["sub"], p["device_id"]):
                    return self._clear_cookies_and_redirect_login()
                try:
                    request.user = User.objects.get(id=int(p["sub"]))
                except User.DoesNotExist:
                    return self._clear_cookies_and_redirect_login()
                response = self.get_response(request)
                _sync_language_cookie(request, response, request.user)
                return response

            if new_tokens is None:
                return self._clear_cookies_and_redirect_login()

            payload = decode_token(new_tokens["access_token"], token_type="access")
        except TokenInvalid:
            return self._clear_cookies_and_redirect_login()

        if AuthRedisService.is_token_revoked(payload["jti"]):
            return self._clear_cookies_and_redirect_login()

        if not AuthRedisService.validate_session(payload["sub"], payload["device_id"]):
            return self._clear_cookies_and_redirect_login()

        try:
            request.user = User.objects.get(id=int(payload["sub"]))
        except User.DoesNotExist:
            return self._clear_cookies_and_redirect_login()

        response = self.get_response(request)

        if new_tokens is not None:
            response.set_cookie(
                settings.JWT_ACCESS_COOKIE_NAME,
                new_tokens["access_token"],
                max_age=settings.JWT_ACCESS_TOKEN_TTL,
                httponly=settings.JWT_COOKIE_HTTPONLY,
                secure=settings.JWT_COOKIE_SECURE,
                samesite=settings.JWT_COOKIE_SAMESITE,
            )
            response.set_cookie(
                settings.JWT_REFRESH_COOKIE_NAME,
                new_tokens["refresh_token"],
                max_age=settings.JWT_REFRESH_TOKEN_TTL,
                httponly=settings.JWT_COOKIE_HTTPONLY,
                secure=settings.JWT_COOKIE_SECURE,
                samesite=settings.JWT_COOKIE_SAMESITE,
            )

        _sync_language_cookie(request, response, request.user)

        return response
    @staticmethod
    def _try_soft_authenticate(request):
        """
        Best-effort аутентификация для публичных страниц: если есть валидный
        access_token — подставляем request.user. Никаких редиректов и попыток
        тихого рефреша здесь нет — страница обязана остаться доступной
        в любом случае (валиден токен или нет, есть он или нет).
        """
        access_token = request.COOKIES.get(settings.JWT_ACCESS_COOKIE_NAME)
        if not access_token:
            return

        try:
            payload = decode_token(access_token, token_type="access")
        except (TokenExpired, TokenInvalid):
            return

        if AuthRedisService.is_token_revoked(payload["jti"]):
            return

        if not AuthRedisService.validate_session(payload["sub"], payload["device_id"]):
            return

        try:
            request.user = User.objects.get(id=int(payload["sub"]))
        except User.DoesNotExist:
            return

    @staticmethod
    def _clear_cookies_and_redirect_login():
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

def _strip_language_prefix(path: str) -> str:
    """
    "/uz/about/"  -> "/about/"
    "/ru/"        -> "/"
    "/en"         -> "/"
    "/about/"     -> "/about/"      (без префикса — не трогаем)
    "/dashboard/" -> "/dashboard/"  (не под i18n_patterns — не трогаем)
    """
    match = _LANGUAGE_PREFIX_RE.match(path)
    if not match:
        return path
    rest = match.group(2)
    return rest if rest else "/"