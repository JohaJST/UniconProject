"""
core/auth_jwt/exceptions.py
────────────────────────────
Кастомные исключения слоя JWT-аутентификации.

Эти исключения бросаются в tokens.py / services.py (Redis-сервисы) и
перехватываются в middleware / контроллерах логина-рефреша-лока
(см. Карту Зависимостей — уровни 3 и 4), которые превращают их в
соответствующие HTTP-ответы (401/403/429 и редиректы).
"""


class TokenExpired(Exception):
    """
    Токен (access или refresh) технически валиден (подпись верна),
    но истёк срок его действия (claim ``exp``).
    """
    pass


class TokenInvalid(Exception):
    """
    Токен повреждён, подпись не совпадает, формат неверный, либо тип
    токена (``access``/``refresh``) не совпадает с ожидаемым в месте вызова.
    """
    pass


class DeviceMismatch(Exception):
    """
    Токен предъявлен с устройства, не совпадающего с зафиксированным
    в Redis-ключе ``user:{user_id}:active_device``
    (сверяются ``device_id`` / ``ua_hash`` / ``ip_subnet``).

    Сигнализирует о потенциальном угоне сессии — используется для
    инвалидации refresh-семьи (``rt_family:{family_id}``) в сервисном слое.
    """
    pass


class RateLimitError(Exception):
    """
    Превышен лимит попыток аутентификации.

    Связан с Redis-ключами ``lock:user:{user_id}:attempts`` (счётчик)
    и ``lock:user:{user_id}:blocked`` (флаг активной блокировки).
    """
    pass