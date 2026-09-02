"""
core/dashboard/pagination/offset_engine.py
─────────────────────────────────────────────
Offset-движок пагинации: классический LIMIT/OFFSET + COUNT().

Применяется к спискам, где сортировка построена через вычисляемое поле
(annotate с Subquery/Max/F(...).desc(nulls_last=True) и т.п.) и поэтому
принципиально не может использовать составной B-Tree индекс — Keyset Engine
здесь не даёт никакого преимущества перед классическим оффсетом. Для
дашборда это постоянное решение для списка selfuser, а не временный
компромисс до появления keyset-варианта (см. core/dashboard/selfuser_crud.py).

Постраничность через ?page=N (номер страницы, 1-indexed) — без
криптографической подписи: значение page само по себе не является
чувствительным идентификатором строки (в отличие от курсора Keyset Engine,
который несёт значения ключевых полей строки), поэтому IDOR-риска здесь
нет — максимум пользователь получит пустую/клампованную страницу за
пределами диапазона, а не чужие данные.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict
from urllib.parse import urlencode

from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.db.models import QuerySet
from django.http import HttpRequest


@dataclass
class OffsetPage:
    """
    Результат оффсет-пагинации одного списка.

    :param items: строки текущей страницы (уже нарезанные LIMIT/OFFSET).
    :param current_page: номер текущей страницы (1-indexed).
    :param total_pages: общее количество страниц (>= 1 даже для пустого
        списка — так работает django.core.paginator.Paginator по умолчанию).
    :param has_prev: есть ли предыдущая страница.
    :param has_next: есть ли следующая страница.
    :param urls: ссылки для шаблона — ключи "start"/"prev"/"next"/"last".
        Значение — None, если переход недоступен (например, urls["prev"]
        is None на первой странице); шаблон должен рендерить кнопку
        неактивной в этом случае, а не битую ссылку с page=0.
    """
    items: list
    current_page: int
    total_pages: int
    has_prev: bool
    has_next: bool
    urls: Dict[str, Any] = field(default_factory=dict)


def _build_page_url(request: HttpRequest, page_number: int) -> str:
    """
    Собирает URL текущего пути с обновлённым query-параметром page,
    сохраняя остальные текущие параметры запроса (задел на будущее —
    если у списка появятся фильтры, они не потеряются при перелистывании).
    """
    params = request.GET.copy()
    params["page"] = str(page_number)
    return f"{request.path}?{urlencode(params)}"


def paginate_offset(queryset: QuerySet, request: HttpRequest, page_size: int = 20) -> OffsetPage:
    """
    Нарезает queryset постранично через django.core.paginator.Paginator
    по номеру страницы из request.GET["page"].

    Невалидное/отсутствующее/вне-диапазона значение page трактуется мягко:
    нечисловое или отсутствующее -> первая страница; больше total_pages ->
    последняя страница; меньше 1 -> первая страница. Никогда не 404/500.
    """
    paginator = Paginator(queryset, page_size)

    raw_page = request.GET.get("page", "1")
    try:
        page_number = int(raw_page)
    except (TypeError, ValueError):
        page_number = 1

    try:
        page = paginator.page(page_number)
    except PageNotAnInteger:
        page = paginator.page(1)
    except EmptyPage:
        page = paginator.page(paginator.num_pages if page_number > paginator.num_pages else 1)

    current = page.number
    total_pages = paginator.num_pages

    urls = {
        "start": _build_page_url(request, 1) if current > 1 else None,
        "prev": _build_page_url(request, current - 1) if page.has_previous() else None,
        "next": _build_page_url(request, current + 1) if page.has_next() else None,
        "last": _build_page_url(request, total_pages) if current < total_pages else None,
    }

    return OffsetPage(
        items=list(page.object_list),
        current_page=current,
        total_pages=total_pages,
        has_prev=page.has_previous(),
        has_next=page.has_next(),
        urls=urls,
    )