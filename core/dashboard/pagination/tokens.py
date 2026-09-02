"""
core/dashboard/pagination/tokens.py
──────────────────────────────────────
Подписанные курсоры пагинации (Keyset Engine) и фингерпринт фильтров.

Курсор кодирует значения последней/первой строки текущей страницы
(sort_value, id_value), направление навигации и хэш применённых фильтров —
всё это подписывается через django.core.signing поверх settings.SECRET_KEY.

ВАЖНО: используется ОТДЕЛЬНЫЙ salt ("dashboard-pagination-v1"), не
пересекающийся с core/auth_jwt (там свой алгоритм — PyJWT HS256 напрямую
поверх SECRET_KEY, без django.core.signing). Разный salt гарантирует, что
токен пагинации нельзя перепутать/переиспользовать как auth-токен даже
теоретически: signing.dumps() с разным salt даёт разные подписи для
одного и того же SECRET_KEY.

signing.dumps() всегда встраивает временную метку (через TimestampSigner
внутри) — срок годности НЕ фиксируется при кодировании, а проверяется
только при декодировании через параметр max_age у signing.loads(). Это
осознанное решение: один и тот же закодированный курсор можно
интерпретировать с разным TTL-требованием на стороне читателя.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, Optional

from django.core import signing

_SALT = "dashboard-pagination-v1"

_DEFAULT_MAX_AGE = 3600  # 1 час — согласовано с TTL курсора Keyset Engine


def encode_cursor(sort_value: Any, id_value: int, direction: str, filters_fingerprint: str) -> str:
    """
    Кодирует и подписывает курсор пагинации.

    :param sort_value: значение поля сортировки последней/первой строки
        текущей страницы (например, datetime для created, либо int для id
        у списков с sort_field="id"). Сериализуется через DjangoJSONEncoder
        (используется signing.dumps по умолчанию) — datetime/date/Decimal/UUID
        поддерживаются "из коробки"; при decode_cursor() значение вернётся
        уже как JSON-примитив (например, ISO-строка для datetime) — разбор
        обратно в нужный Python-тип на совести вызывающего кода
        (keyset_engine.py), который точно знает тип sort_field конкретного
        списка.
    :param id_value: id строки-границы страницы (тай-брейкер).
    :param direction: направление навигации, например "next"/"prev".
    :param filters_fingerprint: хэш применённых на момент выдачи курсора
        фильтров (см. make_filters_fingerprint) — при декодировании
        сверяется с текущим отпечатком, чтобы не листать курсор, выданный
        под другими фильтрами.
    :return: подписанная строка курсора, безопасная для передачи в URL.
    """
    payload = {
        "sort": sort_value,
        "id": id_value,
        "dir": direction,
        "fp": filters_fingerprint,
    }
    return signing.dumps(payload, salt=_SALT)


def decode_cursor(token: Optional[str], max_age: int = _DEFAULT_MAX_AGE) -> Optional[Dict[str, Any]]:
    """
    Декодирует и валидирует курсор пагинации.

    :param token: строка курсора, полученная из encode_cursor() (обычно —
        значение query-параметра ?cursor= из запроса).
    :param max_age: сколько секунд курсор считается ещё действительным
        (проверяется по встроенной в подпись временной метке). Курсор
        старше этого значения трактуется как просроченный.
    :return: словарь {"sort", "id", "dir", "fp"} при успехе, либо None —
        если токен отсутствует/пуст, просрочен, подпись повреждена/не
        совпадает, либо токен в принципе не похож на валидную строку
        signing.dumps(). Ни при каких обстоятельствах не бросает исключение
        наружу — вызывающий код (keyset_engine.py) должен трактовать None
        как "показать первую страницу", а не падать 500.
    """
    if not token:
        return None

    try:
        return signing.loads(token, salt=_SALT, max_age=max_age)
    except signing.SignatureExpired:
        return None
    except signing.BadSignature:
        return None
    except (ValueError, TypeError):
        # Мусорная строка, которая не проходит даже base64/JSON-разбор
        # (случайный текст в ?cursor= вместо реального токена) — signing
        # может бросить не только BadSignature, а и более низкоуровневые
        # исключения на этапе base64-декодирования/JSON-парсинга payload.
        return None


def make_filters_fingerprint(query_params: Dict[str, Any]) -> str:
    """
    Строит детерминированный отпечаток набора фильтров списка.

    Канонизация перед хэшированием:
      - ключи сортируются (порядок в исходном dict/QueryDict не важен);
      - значения приводятся к строкам (str()) — единообразно для чисел,
        None, и т.п.;
      - служебные параметры пагинации (cursor, dir, page) должны быть
        исключены ДО вызова этой функции самим вызывающим кодом — сюда
        передаются только содержательные фильтры списка (например,
        будущие ?subject=, ?potok=). Сейчас (см. list.html) таких
        фильтров нет вообще, поэтому на практике query_params будет
        пустым словарём, а отпечаток — фиксированным хэшем пустого
        набора. Это ожидаемо: механизм закладывается на будущее, когда
        в списки добавят фильтры.

    :return: hex-строка MD5 от канонизированного представления.
    """
    canonical = {str(key): str(value) for key, value in query_params.items()}
    serialized = json.dumps(canonical, sort_keys=True, ensure_ascii=True)
    return hashlib.md5(serialized.encode("utf-8")).hexdigest()