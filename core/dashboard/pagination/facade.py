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
        return PageResult(items=spec.queryset_factory(), spec=spec, pagination={})

    if spec.engine == "offset":
        raise NotImplementedError(
            f"Offset-движок пагинации для tip={tip!r} ещё не реализован. "
            "Будет добавлен в core/dashboard/pagination/offset_engine.py "
            "(см. план: этап подключения Offset Engine к selfuser/др. спискам)."
        )

    if spec.engine == "keyset":
        from core.dashboard.pagination.keyset_engine import paginate_keyset

        page = paginate_keyset(spec.queryset_factory(), spec, request)
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