"""
core/auth.py
──────────────
Вход и выход пользователя на JWT-аутентификации.

Django session-логин (login/logout/authenticate) не используется —
аутентификация запроса выполняется JWTAuthenticationMiddleware по
access_token cookie (см. core/auth_jwt/middleware.py).
"""
import hashlib
import time
import uuid

import jwt
from django.conf import settings
from django.shortcuts import redirect, render

from core.models import ClassRooms, User
from core.auth_jwt.exceptions import TokenExpired, TokenInvalid
from core.auth_jwt.services import AuthRedisService
from core.auth_jwt.tokens import decode_token, generate_tokens
from core.auth_jwt.refresh_logic import attempt_token_refresh

def _redirect_to_login_clearing_cookies():
    """Общий хелпер: редирект на login с удалением обеих JWT-кук."""
    response = redirect("login")
    response.delete_cookie(settings.JWT_ACCESS_COOKIE_NAME)
    response.delete_cookie(settings.JWT_REFRESH_COOKIE_NAME)
    return response


def sign_in(requests):
    if not requests.user.is_anonymous:
        return redirect("home")

    ctx = {
        "u": User.objects.all(),
        "c": ClassRooms.objects.all(),
    }

    if requests.POST:
        data = requests.POST
        user = User.objects.filter(id=int(data["user"])).first()
        if not user:
            ctx["error"] = "Абитуриент(ка) не найден(а)"
            return render(requests, 'pages/auth/login.html', ctx)

        if not user.is_active:
            ctx["error"] = "Профиль не активен"
            return render(requests, 'pages/auth/login.html', ctx)

        # ── Новая JWT-сессия ──────────────────────────────────────────────
        device_id = uuid.uuid4().hex
        family_id = uuid.uuid4().hex

        ua_raw = requests.META.get("HTTP_USER_AGENT", "")
        ua_hash = hashlib.sha256(ua_raw.encode("utf-8")).hexdigest()

        ip_raw = requests.META.get("REMOTE_ADDR", "")
        ip_parts = ip_raw.split(".")
        ip_subnet = ".".join(ip_parts[:3]) + ".0/24" if len(ip_parts) == 4 else ip_raw

        AuthRedisService.set_active_session(
            user_id=user.id,
            device_id=device_id,
            ua_hash=ua_hash,
            ip_subnet=ip_subnet,
        )

        tokens = generate_tokens(user_id=user.id, device_id=device_id, family_id=family_id)
        initial_refresh_hash = hashlib.sha256(tokens["refresh_token"].encode("utf-8")).hexdigest()
        AuthRedisService.rotate_refresh_family(family_id, initial_refresh_hash)
        
        AuthRedisService.clear_login_attempts(user.id)
        # Админов — сразу на форму пароля дашборда, остальных — на главную.
        # 
        response = redirect("lock") if user.is_admin else redirect("home")

        response.set_cookie(
            settings.JWT_ACCESS_COOKIE_NAME,
            tokens["access_token"],
            max_age=settings.JWT_ACCESS_TOKEN_TTL,
            httponly=settings.JWT_COOKIE_HTTPONLY,
            secure=settings.JWT_COOKIE_SECURE,
            samesite=settings.JWT_COOKIE_SAMESITE,
        )
        response.set_cookie(
            settings.JWT_REFRESH_COOKIE_NAME,
            tokens["refresh_token"],
            max_age=settings.JWT_REFRESH_TOKEN_TTL,
            httponly=settings.JWT_COOKIE_HTTPONLY,
            secure=settings.JWT_COOKIE_SECURE,
            samesite=settings.JWT_COOKIE_SAMESITE,
        )

        return response

    return render(requests, 'pages/auth/login.html', ctx)


def refresh_token_view(request):
    """
    Ротация access/refresh токенов по действующему refresh_token cookie.

    Reuse-detection: если хэш предъявленного refresh-токена не совпадает
    с current_token_hash в Redis (или семья уже compromised) — токен был
    скомпрометирован (украден). В этом случае убивается вся сессия.
    """
    refresh_token = request.COOKIES.get(settings.JWT_REFRESH_COOKIE_NAME)
    if not refresh_token:
        return _redirect_to_login_clearing_cookies()

    try:
        new_tokens = attempt_token_refresh(refresh_token)
    except (TokenExpired, TokenInvalid):
        return _redirect_to_login_clearing_cookies()

    if new_tokens is None:
        return _redirect_to_login_clearing_cookies()

    response = redirect(request.GET.get('next', 'home'))
    response.set_cookie(
        settings.JWT_ACCESS_COOKIE_NAME, new_tokens["access_token"],
        max_age=settings.JWT_ACCESS_TOKEN_TTL, httponly=settings.JWT_COOKIE_HTTPONLY,
        secure=settings.JWT_COOKIE_SECURE, samesite=settings.JWT_COOKIE_SAMESITE,
    )
    response.set_cookie(
        settings.JWT_REFRESH_COOKIE_NAME, new_tokens["refresh_token"],
        max_age=settings.JWT_REFRESH_TOKEN_TTL, httponly=settings.JWT_COOKIE_HTTPONLY,
        secure=settings.JWT_COOKIE_SECURE, samesite=settings.JWT_COOKIE_SAMESITE,
    )
    return response


def sign_out(request):
    """
    Логаут: отзывает текущий access-токен по jti, удаляет активную сессию
    устройства в Redis и стирает обе JWT-куки.

    @login_required не используется: без валидного access_token запрос
    вообще не дойдёт до защищённых путей — это гарантирует
    JWTAuthenticationMiddleware.
    """
    access_token = request.COOKIES.get(settings.JWT_ACCESS_COOKIE_NAME)

    if access_token:
        try:
            # verify_signature=False: на логауте токен может быть уже
            # просроченным — это не повод падать, нужен только payload.
            payload = jwt.decode(access_token, options={"verify_signature": False})
        except jwt.DecodeError:
            payload = {}

        jti = payload.get("jti")
        exp = payload.get("exp")

        if jti:
            remaining_ttl = max(int(exp - time.time()), 1) if exp else settings.JWT_ACCESS_TOKEN_TTL
            AuthRedisService.revoke_token(jti, remaining_ttl)

        user_id = payload.get("sub")
        if user_id is not None:
            AuthRedisService.clear_active_session(user_id)

    return _redirect_to_login_clearing_cookies()