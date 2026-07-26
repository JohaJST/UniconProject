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

        AuthRedisService.clear_login_attempts(user.id)

        # Админов — сразу на форму пароля дашборда, остальных — на главную.
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
        payload = decode_token(refresh_token, token_type="refresh")
    except (TokenExpired, TokenInvalid):
        return _redirect_to_login_clearing_cookies()

    user_id = payload.get("sub")
    device_id = payload.get("device_id")
    family_id = payload.get("family_id")

    family = AuthRedisService.get_family(family_id)
    current_hash = family.get("current_token_hash") if family else None
    is_compromised = family.get("compromised", False) if family else True

    presented_hash = hashlib.sha256(refresh_token.encode("utf-8")).hexdigest()

    if is_compromised or presented_hash != current_hash:
        # Reuse Attack (или семья потеряна/протухла в Redis) — убиваем
        # всю сессию пользователя, а не только эту семью.
        AuthRedisService.mark_family_compromised(family_id)
        AuthRedisService.kick_user(user_id)
        return _redirect_to_login_clearing_cookies()

    # ── Всё совпало — сессия легитимна ────────────────────────────────────
    # Продлеваем TTL active_device ещё на JWT_REFRESH_TOKEN_TTL: без этого
    # вызова пользователь вылетал бы ровно через 7 дней после первого входа,
    # даже оставаясь активным (set_active_session ставится только при логине).
    AuthRedisService.touch_active_session(user_id, timeout=settings.JWT_REFRESH_TOKEN_TTL)

    # ── Ротация: новая пара токенов, старый device_id/family_id ──────────
    new_tokens = generate_tokens(user_id=user_id, device_id=device_id, family_id=family_id)
    new_refresh_hash = hashlib.sha256(new_tokens["refresh_token"].encode("utf-8")).hexdigest()
    AuthRedisService.rotate_refresh_family(family_id, new_refresh_hash)

    response = redirect(request.GET.get('next', 'home'))

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