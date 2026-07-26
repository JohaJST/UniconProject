"""
core/auth_jwt/tokens.py
────────────────────────
Генерация и декодирование JWT access/refresh токенов (PyJWT).

Payload access-токена:
    {
        "sub":       int,   # ID пользователя (стандартный JWT-claim "subject")
        "device_id": str,
        "jti":       str,   # уникальный ID именно этого access-токена
        "type":      "access",
        "iat":       <timestamp>,
        "exp":       <timestamp>,   # settings.JWT_ACCESS_TOKEN_TTL (900s)
    }

Payload refresh-токена:
    {
        "sub":       int,
        "device_id": str,
        "family_id": str,           # см. Redis-ключ rt_family:{family_id}
        "jti":       str,           # уникальный ID именно этого refresh-токена
        "type":      "refresh",
        "iat":       <timestamp>,
        "exp":       <timestamp>,   # settings.JWT_REFRESH_TOKEN_TTL (604800s)
    }

ХОТФИКС: ключ пользователя переименован user_id -> sub (стандартное имя
JWT-claim'а), а claim ``jti`` теперь генерируется для ОБОИХ токенов, а не
только для refresh — это нужно, чтобы AuthRedisService.revoke_token /
is_token_revoked могли атомарно отзывать конкретный access-токен точно так
же, как и refresh (например, при logout с одного устройства или при
обнаружении DeviceMismatch в middleware).
"""
from __future__ import annotations

import datetime
import uuid

import jwt
from django.conf import settings

from core.auth_jwt.exceptions import TokenExpired, TokenInvalid

# Алгоритм подписи. Отдельный JWT-секрет в Shared Context не заявлен,
# поэтому переиспользуем settings.SECRET_KEY проекта.
JWT_ALGORITHM = "HS256"


def _utcnow() -> datetime.datetime:
    """Единая точка получения текущего времени — упрощает тестирование/мокинг."""
    return datetime.datetime.utcnow()


def generate_tokens(user_id: int, device_id: str, family_id: str) -> dict:
    """
    Создаёт пару access/refresh токенов для одной сессии логина.

    :param user_id:   ID пользователя (core.models.User.id) — кладётся в
                       payload под стандартным claim'ом "sub"
    :param device_id: идентификатор устройства — сверяется middleware
                       с Redis-ключом ``user:{user_id}:active_device``
    :param family_id:  идентификатор "семьи" refresh-токенов; один и тот же
                       на протяжении всех ротаций одной сессии логина
                       (владелец генерации uuid — вызывающий код, например
                       контроллер логина; см. Redis-ключ ``rt_family:{family_id}``)
    :return: {"access_token": str, "refresh_token": str, "family_id": str}
    """
    now = _utcnow()

    # ── Access-токен ────────────────────────────────────────────────────
    access_payload = {
        "sub": user_id,
        "device_id": device_id,
        # jti — уникальный ID именно этого access-токена, нужен для
        # точечного отзыва (token:revoked:{jti}) без ожидания истечения TTL.
        "jti": uuid.uuid4().hex,
        "type": "access",
        "iat": now,
        "exp": now + datetime.timedelta(seconds=settings.JWT_ACCESS_TOKEN_TTL),
    }
    access_token = jwt.encode(access_payload, settings.SECRET_KEY, algorithm=JWT_ALGORITHM)

    # ── Refresh-токен ───────────────────────────────────────────────────
    refresh_payload = {
        "sub": user_id,
        "device_id": device_id,
        "family_id": family_id,
        # jti — уникальный идентификатор именно этого refresh-токена,
        # используется для детекта повторного использования старого токена
        # после ротации (см. rt_family:{family_id}.current_token_hash).
        "jti": uuid.uuid4().hex,
        "type": "refresh",
        "iat": now,
        "exp": now + datetime.timedelta(seconds=settings.JWT_REFRESH_TOKEN_TTL),
    }
    refresh_token = jwt.encode(refresh_payload, settings.SECRET_KEY, algorithm=JWT_ALGORITHM)

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "family_id": family_id,
    }


def decode_token(token: str, token_type: str = "access") -> dict:
    """
    Декодирует и валидирует JWT-токен из cookie ``access_token``/``refresh_token``.

    :param token:      сырая строка токена
    :param token_type: ожидаемый тип — "access" или "refresh"
    :raises TokenExpired: истёк срок действия токена (claim ``exp``)
    :raises TokenInvalid: неверная подпись/формат, либо тип токена не совпал
                          с ожидаемым (например, refresh подсунут вместо access)
    :return: payload токена (dict)
    """
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError as exc:
        raise TokenExpired("Срок действия токена истёк") from exc
    except jwt.InvalidTokenError as exc:
        raise TokenInvalid("Токен повреждён или имеет неверную подпись") from exc

    # Проверка типа токена — защищает от подмены access <-> refresh.
    if payload.get("type") != token_type:
        raise TokenInvalid(
            f"Ожидался токен типа '{token_type}', получен '{payload.get('type')}'"
        )

    return payload