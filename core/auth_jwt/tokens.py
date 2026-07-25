"""
core/auth_jwt/tokens.py
────────────────────────
Генерация и декодирование JWT access/refresh токенов (PyJWT).

Payload access-токена:
    {
        "user_id":   int,
        "device_id": str,
        "type":      "access",
        "iat":       <timestamp>,
        "exp":       <timestamp>,   # settings.JWT_ACCESS_TOKEN_TTL (900s)
    }

Payload refresh-токена:
    {
        "user_id":   int,
        "device_id": str,
        "family_id": str,           # см. Redis-ключ rt_family:{family_id}
        "jti":       str,           # уникальный ID именно этого токена
        "type":      "refresh",
        "iat":       <timestamp>,
        "exp":       <timestamp>,   # settings.JWT_REFRESH_TOKEN_TTL (604800s)
    }

``jti`` refresh-токена нужен сервисному слою (Redis, промпт 5) для хранения
хэша "текущего" токена внутри ``rt_family:{family_id}`` и обнаружения
повторного использования уже заротированного токена (reuse detection).
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

    :param user_id:   ID пользователя (core.models.User.id)
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
        "user_id": user_id,
        "device_id": device_id,
        "type": "access",
        "iat": now,
        "exp": now + datetime.timedelta(seconds=settings.JWT_ACCESS_TOKEN_TTL),
    }
    access_token = jwt.encode(access_payload, settings.SECRET_KEY, algorithm=JWT_ALGORITHM)

    # ── Refresh-токен ───────────────────────────────────────────────────
    refresh_payload = {
        "user_id": user_id,
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