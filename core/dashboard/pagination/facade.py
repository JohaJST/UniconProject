"""
core/dashboard/pagination/facade.py
──────────────────────────────────────
Единая точка входа для получения страницы данных списка дашборда.

Скрывает от вызывающего кода (core/dashboard/list.py::dlist), какой
именно движок пагинации обслуживает конкретный список — "none" (без
пагинации, текущее поведение), "offset" или "keyset". Вызывающий код
получает единый результат PageResult независимо от движка и не должен
знать о деталях offset_engine.py / keyset_engine.py.

ВАЖНО (этот этап): offset_engine.py и keyset_engine.py ещё не существуют.
Это не проблема — в реестре (registry.py) у ВСЕХ списков сейчас
engine="none", поэтому соответствующие ветки ниже физически не
исполняются. Как только появится первый список с engine="offset"/"keyset"
(следующие этапы), заглушки NotImplementedError в этом файле нужно будет
заменить на реальный вызов движка.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Union

from django.db.models import QuerySet
from django.http import HttpRequest

from core.dashboard.pagination.registry import ListSpec, get_list_spec



@dataclass
class PageResult:
    """
    Унифицированный результат постраничной выборки одного списка дашборда.

    :param items: данные текущей страницы. При engine="none" — это ВЕСЬ
        queryset целиком (идентично старому поведению dlist() до введения
        реестра/фасада). При offset/keyset — уже нарезанная страница.
    :param spec: ListSpec, из которого получен результат — не обязателен
        для рендера, но полезен вызывающему коду для отладки/логирования.
    :param pagination: контекст пагинации для шаблона (ссылки Start/Prev/
        Next/Last, флаги has_prev/has_next и т.п.). При engine="none" —
        всегда пустой словарь: list.html пока ничего не знает про
        пагинацию и ничего лишнего не отрендерит.
    """
    items: Union[QuerySet, list]
    spec: ListSpec
    pagination: Dict[str, Any] = field(default_factory=dict)


def _get_searched_queryset(tip: str, spec: ListSpec, request: HttpRequest) -> QuerySet:
    """
    Строит базовый queryset через spec.queryset_factory() и, если в запросе
    передан ?q=, сужает его через apply_search() из core.dashboard.list.

    ВАЖНО: вызывается ОДИН РАЗ на каждую точку входа в paginate_list()
    (для each ветки engine — свой отдельный вызов spec.queryset_factory(),
    как и раньше), но фильтрация по q применяется единообразно во всех
    трёх ветках — до того, как queryset попадёт в PageResult.items (engine
    "none") или будет передан в keyset_engine/offset_engine.

    Импорт apply_search — локальный (внутри функции), а не на уровне
    модуля: core.dashboard.list уже импортируется из registry.py
    (для _QUERYSETS), а registry.py, в свою очередь, импортируется этим
    же facade.py — локальный импорт исключает даже теоретический риск
    цикла при изменении порядка импортов в будущем.
    
    Поиск: если запрос содержит ?q=<текст>, queryset сужается через
        core.dashboard.list.apply_search() ПОСЛЕ вызова queryset_factory(),
        но ДО того, как он попадёт в PageResult.items (engine="none") или
        будет передан в keyset_engine/offset_engine — так пагинация всегда
        считается по уже отфильтрованным данным, а не по полному списку.
    """
    from core.dashboard.list import apply_search

    qs = spec.queryset_factory()
    return apply_search(qs, tip, request.GET.get("q"))


def paginate_list(tip: str, request: HttpRequest) -> Optional[PageResult]:
    """
    Возвращает PageResult для данного tip, либо None, если tip не
    зарегистрирован в реестре — вызывающий код (dlist()) должен
    трактовать None так же, как раньше трактовал отсутствие qs_factory:
    рендерить пустой list.html без "root".

    :raises NotImplementedError: если для данного списка в реестре
        указан engine="offset" или "keyset" — движки для них появятся
        в следующих этапах (core/dashboard/pagination/offset_engine.py,
        core/dashboard/pagination/keyset_engine.py). Сейчас это НЕ должно
        происходить ни для одного tip, так как весь реестр — engine="none".
    :raises ValueError: если в реестре указан неизвестный движок
        (защита от опечатки при будущем редактировании registry.py).
    """
    spec = get_list_spec(tip)
    if spec is None:
        return None

    if spec.engine == "none":
        return PageResult(items=_get_searched_queryset(tip, spec, request), spec=spec, pagination={})

    if spec.engine == "offset":
        from core.dashboard.pagination.offset_engine import paginate_offset

        page = paginate_offset(_get_searched_queryset(tip, spec, request), request, page_size=spec.page_size)
        return PageResult(
            items=page.items,
            spec=spec,
            pagination={
                "current_page": page.current_page,
                "total_pages": page.total_pages,
                "has_prev": page.has_prev,
                "has_next": page.has_next,
                "urls": page.urls,
            },
        )

    if spec.engine == "keyset":
        from core.dashboard.pagination.keyset_engine import paginate_keyset

        page = paginate_keyset(_get_searched_queryset(tip, spec, request), spec, request)
       return PageResult(
            items=page.items,
            spec=spec,
            pagination={
                "has_prev": page.has_prev,
                "has_next": page.has_next,
                "urls": page.urls,
            },
        )

    raise ValueError(f"Неизвестный движок пагинации engine={spec.engine!r} для tip={tip!r}")