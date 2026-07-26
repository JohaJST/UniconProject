"""
core/auth_jwt/services.py
────────────────────────────
Redis-сервис управления состоянием JWT-сессий и защитой аккаунта.

Работает поверх стандартного Django cache API (``settings.CACHES["default"]``),
который в проде указывает на Redis (``RedisCache``), а в DEBUG — на
``LocMemCache``. Все ключи и их формат зафиксированы в Shared Context и
не должны меняться:

    user:{user_id}:active_device  -> JSON {"device_id", "ua_hash", "ip_subnet"}
    user:{user_id}:dashboard_auth -> "1" (TTL 600s, sliding window)
    rt_family:{family_id}         -> JSON {"current_token_hash", "compromised"}
    lock:user:{user_id}:attempts  -> int
    lock:user:{user_id}:blocked   -> "1"
    lock:ip:{ip_hash}:attempts    -> int
    lock:ip:{ip_hash}:blocked     -> "1"
    token:revoked:{jti}           -> "1"

Класс — единая точка входа во все Redis-операции JWT-подсистемы;
middleware и контроллеры (уровни 3-4) не работают с ``cache``/``json`` напрямую.
"""
import json
from typing import Optional

from django.core.cache import cache

from .exceptions import RateLimitError


class AuthRedisService:
    """
    Сервис-фасад над Redis-ключами JWT-подсистемы. Методы сгруппированы
    по функциональным блокам: Active device / Token revocation /
    Dashboard auth / Refresh token families / Anti-bruteforce.
    """

    # ── Active device session ────────────────────────────────────────────
    # Ключ: user:{user_id}:active_device -> JSON {device_id, ua_hash, ip_subnet}

    @staticmethod
    def _active_device_key(user_id: int) -> str:
        """Собирает имя Redis-ключа для активного устройства пользователя."""
        return f"user:{user_id}:active_device"

    @staticmethod
    def set_active_session(user_id: int, device_id: str, ua_hash: str, ip_subnet: str) -> None:
        """
        Фиксирует устройство как единственное активное для пользователя.

        Вызывается при успешном логине: перезаписывает предыдущую запись
        целиком, тем самым технически "выкидывая" сессию с другого устройства
        (последующая проверка validate_session для старого device_id вернёт False).
        """
        payload = {
            "device_id": device_id,
            "ua_hash": ua_hash,
            "ip_subnet": ip_subnet,
        }
        # ИЗМЕНЕНО: timeout=None -> timeout=604800 (= TTL refresh-токена).
        # Вечных ключей быть не должно: живая сессия не может пережить
        # refresh-токен, которым она была выдана.
        cache.set(
            AuthRedisService._active_device_key(user_id),
            json.dumps(payload),
            timeout=604800,
        )

    @staticmethod
    def touch_active_session(user_id: int, timeout: int = 604800) -> None:
        """
        Продлевает TTL ключа user:{user_id}:active_device в Redis.

        Вызывается из refresh_token_view при КАЖДОЙ успешной ротации
        refresh-токена. Без этого вызова set_active_session() ставит TTL
        только один раз — при логине — и активная сессия умирает ровно
        через 7 дней, даже если пользователь непрерывно продлевает токены.

        cache.touch() продлевает TTL существующего ключа, не трогая
        значение (device_id/ua_hash/ip_subnet остаются как есть).
        Если ключа уже нет (истёк / logout / kick_user) — touch() тихо
        вернёт False, и это ожидаемо: validate_session() и так вернёт
        False на следующей проверке, создавать ключ заново здесь не нужно.
        """
        cache.touch(
            AuthRedisService._active_device_key(user_id),
            timeout=timeout,
        )

    @staticmethod
    def validate_session(user_id: int, device_id: str) -> bool:
        """
        Сверяет device_id из предъявленного access/refresh-токена с тем,
        что записан в Redis как активное устройство пользователя.

        :return: True  — device_id совпадает, сессия валидна;
                 False — ключ отсутствует в Redis ИЛИ device_id не совпадает
                 (в обоих случаях middleware уровня 3 должен трактовать это
                 как повод разлогинить / бросить DeviceMismatch — сам метод
                 исключений не бросает, только сообщает факт).
        """
        raw = cache.get(AuthRedisService._active_device_key(user_id))
        if raw is None:
            return False

        try:
            stored = json.loads(raw)
        except (TypeError, ValueError):
            # Повреждённые/неожиданные данные в Redis — считаем сессию невалидной.
            return False

        return stored.get("device_id") == device_id

    @staticmethod
    def clear_active_session(user_id: int) -> None:
        """
        Удаляет запись об активном устройстве пользователя из Redis.

        Вызывается при logout: после удаления ключа validate_session для
        любого device_id вернёт False, что фактически разлогинивает
        и любые другие ещё не истёкшие по exp токены этого пользователя.
        """
        cache.delete(AuthRedisService._active_device_key(user_id))

    # ── Token revocation ─────────────────────────────────────────────────
    # Ключ: token:revoked:{jti} -> "1"
    # Используется, например, при logout/ротации, чтобы старый (ещё не
    # истёкший по exp) токен нельзя было использовать повторно.

    @staticmethod
    def _revoked_token_key(jti: str) -> str:
        return f"token:revoked:{jti}"

    @staticmethod
    def revoke_token(jti: str, remaining_ttl: int) -> None:
        """
        Помечает токен с данным ``jti`` как отозванный.

        :param jti: уникальный идентификатор токена (claim ``jti``)
        :param remaining_ttl: сколько секунд ключ должен жить в Redis —
            обычно это оставшееся время жизни самого токена (exp - now),
            чтобы запись не переживала токен и не копилась в Redis вечно.
        """
        cache.set(AuthRedisService._revoked_token_key(jti), "1", timeout=remaining_ttl)

    @staticmethod
    def is_token_revoked(jti: str) -> bool:
        """True, если токен с данным jti был отозван и ещё не истёк по TTL."""
        return cache.get(AuthRedisService._revoked_token_key(jti)) is not None

    # ── Dashboard auth ───────────────────────────────────────────────────
    # Ключ: user:{user_id}:dashboard_auth -> "1" (TTL 600s, sliding window)
    # Заменяет собой удалённые в Промпте 2 поля User.in_dashboard/interval.

    @staticmethod
    def _dashboard_auth_key(user_id: int) -> str:
        return f"user:{user_id}:dashboard_auth"

    @staticmethod
    def authorize_dashboard(user_id: int) -> None:
        """
        Открывает доступ к дашборду на 600 секунд (после ввода пароля дашборда).

        Sliding window: DashboardSecurityMiddleware (уровень 3) должен вызывать
        этот метод повторно на каждый успешный запрос к дашборду, тем самым
        продлевая TTL, пока пользователь активен — здесь же фиксируется только
        факт установки ключа с TTL 600s.
        """
        cache.set(AuthRedisService._dashboard_auth_key(user_id), "1", timeout=600)

    @staticmethod
    def is_dashboard_authorized(user_id: int) -> bool:
        """True, если ключ dashboard_auth ещё не истёк (пользователь в дашборде)."""
        return cache.get(AuthRedisService._dashboard_auth_key(user_id)) is not None

    # ── Refresh token families (ротация + reuse-detection) ──────────────
    # Ключ: rt_family:{family_id} -> JSON {"current_token_hash", "compromised"}

    @staticmethod
    def _family_key(family_id: str) -> str:
        return f"rt_family:{family_id}"

    @staticmethod
    def rotate_refresh_family(family_id: str, new_token_hash: str) -> None:
        """
        Фиксирует новый "текущий" refresh-токен для семейства при ротации.

        Полностью перезаписывает запись: старый current_token_hash больше
        нигде не хранится, поэтому его повторное предъявление контроллер
        рефреша (уровень 4) должен трактовать как компрометацию семьи
        (см. mark_family_compromised).
        """
        payload = {
            "current_token_hash": new_token_hash,
            "compromised": False,
        }
        cache.set(AuthRedisService._family_key(family_id), json.dumps(payload), timeout=604800)

    @staticmethod
    def mark_family_compromised(family_id: str) -> None:
        """
        Помечает семейство refresh-токенов как скомпрометированное
        (обнаружено повторное использование старого токена — reuse attack).

        Существующий current_token_hash сохраняется как есть (для аудита),
        меняется только флаг compromised; TTL продлевается заново на 604800s.
        """
        raw = cache.get(AuthRedisService._family_key(family_id))
        try:
            data = json.loads(raw) if raw else {}
        except (TypeError, ValueError):
            data = {}

        data["compromised"] = True
        data.setdefault("current_token_hash", None)

        cache.set(AuthRedisService._family_key(family_id), json.dumps(data), timeout=604800)

    @staticmethod
    def get_family(family_id: str) -> Optional[dict]:
        """
        Возвращает распарсенный JSON из rt_family:{family_id}.

        :return: {"current_token_hash": str, "compromised": bool} либо None,
            если запись не найдена в Redis (ключ истёк или никогда не
            создавался) или содержит повреждённые данные.
        """
        raw = cache.get(AuthRedisService._family_key(family_id))
        if raw is None:
            return None

        try:
            return json.loads(raw)
        except (TypeError, ValueError):
            return None

    # ── Global kick (полный сброс сессии пользователя) ───────────────────
    # Используется, например, при обнаружении reuse-attack на refresh-токен
    # в refresh_token_view (core/auth.py): пользователя нужно выкинуть
    # отовсюду, а не только скомпрометировать одну refresh-семью.

    @staticmethod
    def kick_user(user_id: int) -> None:
        """
        Полностью выкидывает пользователя из системы на уровне Redis:
        удаляет активное устройство (после этого validate_session для
        ЛЮБОГО device_id вернёт False — все ещё не истёкшие токены
        перестают работать) и доступ к дашборду.
        """
        cache.delete(AuthRedisService._active_device_key(user_id))
        cache.delete(AuthRedisService._dashboard_auth_key(user_id))

    # ── Anti-bruteforce ──────────────────────────────────────────────────
    # Ключи:
    #   lock:user:{user_id}:attempts / lock:user:{user_id}:blocked
    #   lock:ip:{ip_hash}:attempts   / lock:ip:{ip_hash}:blocked

    @staticmethod
    def _user_attempts_key(user_id: int) -> str:
        return f"lock:user:{user_id}:attempts"

    @staticmethod
    def _user_blocked_key(user_id: int) -> str:
        return f"lock:user:{user_id}:blocked"

    @staticmethod
    def _ip_attempts_key(ip_hash: str) -> str:
        return f"lock:ip:{ip_hash}:attempts"

    @staticmethod
    def _ip_blocked_key(ip_hash: str) -> str:
        return f"lock:ip:{ip_hash}:blocked"

    @staticmethod
    def check_lock_bruteforce(user_id: int, ip_hash: str) -> None:
        """
        Вызывается на каждую неуспешную попытку логина: сначала проверяет,
        не заблокированы ли уже юзер/IP, затем инкрементирует счётчики
        попыток и, при превышении порогов, ставит новую блокировку.

        :raises RateLimitError: если юзер или IP уже заблокированы
            (ключ *:blocked* существует) — счётчики в этом случае НЕ трогаем.
        """
        # 1. Уже заблокирован? — сразу выходим с исключением, счётчики не растим.
        if cache.get(AuthRedisService._user_blocked_key(user_id)) is not None:
            raise RateLimitError(f"Пользователь {user_id} временно заблокирован")
        if cache.get(AuthRedisService._ip_blocked_key(ip_hash)) is not None:
            raise RateLimitError(f"IP {ip_hash} временно заблокирован")

        # 2. Инкрементируем счётчик попыток юзера.
        # cache.incr требует существующий ключ — если его ещё нет (ValueError),
        # создаём с начальным значением 1 и TTL 900s.
        user_key = AuthRedisService._user_attempts_key(user_id)
        try:
            user_attempts = cache.incr(user_key)
        except ValueError:
            cache.set(user_key, 1, timeout=900)
            user_attempts = 1

        # 3. Инкрементируем счётчик попыток по IP (TTL 3600s при первом создании).
        ip_key = AuthRedisService._ip_attempts_key(ip_hash)
        try:
            ip_attempts = cache.incr(ip_key)
        except ValueError:
            cache.set(ip_key, 1, timeout=3600)
            ip_attempts = 1

        # 4. Эскалация блокировки пользователя по нарастающей.
        #    Проверяем от большего порога к меньшему, чтобы не перезаписать
        #    длинную блокировку более короткой при том же вызове.
        if user_attempts >= 7:
            cache.set(AuthRedisService._user_blocked_key(user_id), "1", timeout=600)
        elif user_attempts >= 5:
            cache.set(AuthRedisService._user_blocked_key(user_id), "1", timeout=120)
        elif user_attempts >= 3:
            cache.set(AuthRedisService._user_blocked_key(user_id), "1", timeout=30)

        # 5. Блокировка IP при переборе учёток с одного адреса.
        if ip_attempts >= 20:
            cache.set(AuthRedisService._ip_blocked_key(ip_hash), "1", timeout=3600)

    @staticmethod
    def clear_login_attempts(user_id: int) -> None:
        """Сбрасывает счётчик неуспешных попыток юзера — вызывать при успешном логине."""
        cache.delete(AuthRedisService._user_attempts_key(user_id))