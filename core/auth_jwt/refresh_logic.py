"""
core/auth_jwt/refresh_logic.py
────────────────────────────────
Общая логика ротации refresh-токена, переиспользуемая:
  - JWTAuthenticationMiddleware — для "тихого" обновления истёкшего
    access-токена без прерывания текущего запроса (GET/POST);
  - refresh_token_view (core/auth.py) — как явный fallback-эндпоинт.

ВАЖНО (фикс): presented_hash != current_token_hash сам по себе НЕ означает
атаку. Он возникает КАЖДЫЙ РАЗ, когда параллельный запрос (вторая вкладка,
автосейв + навигация, повторный fetch) уже успел завершить ротацию раньше
нас — тогда current_token_hash навсегда меняется, и наш sleep+recheck
никогда не совпадёт заново. Поэтому перед тем, как объявлять compromise,
проверяем grace-окно: если presented_hash — это токен, который только что
(последние _REFRESH_GRACE_SECONDS) был легитимно заменён этой же семьёй,
это гонка, а не reuse-attack.
"""
from __future__ import annotations

import hashlib
import time
from typing import Optional

from django.conf import settings

from core.auth_jwt.exceptions import TokenExpired, TokenInvalid, RefreshRace
from core.auth_jwt.services import AuthRedisService
from core.auth_jwt.tokens import decode_token, generate_tokens


def attempt_token_refresh(refresh_token: str) -> Optional[dict]:
    """
    Пытается ротировать refresh-токен.

    :raises TokenExpired: refresh-токен истёк — вызывающий код должен
        разлогинить пользователя (дальше продлевать нечего).
    :raises TokenInvalid: токен повреждён/неверного типа.
    :raises RefreshRace: presented-токен только что был легитимно заменён
        параллельным запросом той же сессии — НЕ атака, сессия валидна.
    :return: dict с новыми access_token/refresh_token при успехе,
             None — если обнаружен реальный reuse-attack (сессия убита
             через kick_user, вызывающий код должен разлогинить пользователя).
    """
    payload = decode_token(refresh_token, token_type="refresh")  # может бросить TokenExpired/TokenInvalid

    user_id = payload.get("sub")
    device_id = payload.get("device_id")
    family_id = payload.get("family_id")
    presented_hash = hashlib.sha256(refresh_token.encode("utf-8")).hexdigest()

    family = AuthRedisService.get_family(family_id)

    # Семьи нет вообще — на живой сессии такого быть не должно; если
    # случилось — это повод разлогинить.
    if family is None:
        AuthRedisService.kick_user(user_id)
        return None

    if family.get("compromised", False):
        AuthRedisService.kick_user(user_id)
        return None

    if presented_hash != family.get("current_token_hash"):
        # 1. Быстрая проверка: этот именно хеш уже легитимно заменён
        #    (grace-окно после чужой ротации) → точно гонка, не атака.
        if AuthRedisService.is_within_grace(family_id, presented_hash):
            raise RefreshRace(payload)

        # 2. Даём небольшой шанс — вдруг ротация другого запроса идёт
        #    прямо сейчас и ещё не записалась.
        time.sleep(0.2)
        family = AuthRedisService.get_family(family_id)

        if family and presented_hash == family.get("current_token_hash"):
            # Другой запрос ещё не закоммитил — на самом деле мы совпали.
            pass  # провалится ниже в обычный acquire_refresh_lock путь
        elif family and AuthRedisService.is_within_grace(family_id, presented_hash):
            raise RefreshRace(payload)
        else:
            # Хеш не совпадает ни с текущим, ни с недавно замененным —
            # это реальный reuse старого, давно неактуального токена.
            AuthRedisService.mark_family_compromised(family_id)
            AuthRedisService.kick_user(user_id)
            return None

    if not AuthRedisService.acquire_refresh_lock(family_id):
        # Кто-то другой ротирует прямо сейчас — тоже не атака.
        raise RefreshRace(payload)

    try:
        AuthRedisService.touch_active_session(user_id, timeout=settings.JWT_REFRESH_TOKEN_TTL)
        new_tokens = generate_tokens(user_id=user_id, device_id=device_id, family_id=family_id)
        new_refresh_hash = hashlib.sha256(new_tokens["refresh_token"].encode("utf-8")).hexdigest()
        AuthRedisService.rotate_refresh_family(family_id, new_refresh_hash, previous_token_hash=presented_hash)
        return new_tokens
    finally:
        AuthRedisService.release_refresh_lock(family_id)