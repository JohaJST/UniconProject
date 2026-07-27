"""
core/auth_jwt/refresh_logic.py
────────────────────────────────
Общая логика ротации refresh-токена, переиспользуемая:
  - JWTAuthenticationMiddleware — для "тихого" обновления истёкшего
    access-токена без прерывания текущего запроса (GET/POST);
  - refresh_token_view (core/auth.py) — как явный fallback-эндпоинт.
"""
from __future__ import annotations

import hashlib
from typing import Optional

from django.conf import settings

from core.auth_jwt.exceptions import TokenExpired, TokenInvalid
from core.auth_jwt.services import AuthRedisService
from core.auth_jwt.tokens import decode_token, generate_tokens


def attempt_token_refresh(refresh_token: str) -> Optional[dict]:
    """
    Пытается ротировать refresh-токен.

    :raises TokenExpired: refresh-токен истёк — вызывающий код должен
        разлогинить пользователя (дальше продлевать нечего).
    :raises TokenInvalid: токен повреждён/неверного типа.
    :return: dict с новыми access_token/refresh_token при успехе,
             None — если обнаружен reuse-attack (сессия убита через kick_user,
             вызывающий код должен разлогинить пользователя).
    """
    payload = decode_token(refresh_token, token_type="refresh")  # может бросить TokenExpired/TokenInvalid

    user_id = payload.get("sub")
    device_id = payload.get("device_id")
    family_id = payload.get("family_id")

    family = AuthRedisService.get_family(family_id)
    current_hash = family.get("current_token_hash") if family else None
    is_compromised = family.get("compromised", False) if family else True

    presented_hash = hashlib.sha256(refresh_token.encode("utf-8")).hexdigest()

    if is_compromised or presented_hash != current_hash:
        # Reuse Attack — убиваем всю сессию.
        AuthRedisService.mark_family_compromised(family_id)
        AuthRedisService.kick_user(user_id)
        return None

    AuthRedisService.touch_active_session(user_id, timeout=settings.JWT_REFRESH_TOKEN_TTL)

    new_tokens = generate_tokens(user_id=user_id, device_id=device_id, family_id=family_id)
    new_refresh_hash = hashlib.sha256(new_tokens["refresh_token"].encode("utf-8")).hexdigest()
    AuthRedisService.rotate_refresh_family(family_id, new_refresh_hash)

    return new_tokens