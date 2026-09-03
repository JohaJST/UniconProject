"""
core/dashboard/pagination/keyset_engine.py
─────────────────────────────────────────────
Keyset-движок пагинации: курсорная выборка по (sort_field, id).

Общая идея направлений навигации:
  - "start" — первая страница в натуральном порядке (spec.sort_direction),
    без фильтра, без курсора.
  - "next"  — продолжение натурального порядка СТРОГО ПОСЛЕ курсора
    (последней строки текущей страницы); order_by = натуральный.
  - "prev"  — строки СТРОГО ДО курсора (первой строки текущей страницы);
    запрашиваются в ОБРАТНОМ порядке (эффективный LIMIT с нужной стороны),
    затем разворачиваются в Python обратно в натуральный порядок для показа.
  - "last"  — последняя страница целиком; запрашивается сразу в обратном
    порядке без фильтра, затем разворачивается.

has_more (для флагов has_prev/has_next на новых границах) определяется
через классический приём "LIMIT page_size + 1" — без отдельного COUNT().

ВАЖНОЕ ОГРАНИЧЕНИЕ (документируется, не исправляется в рамках этого этапа):
курсор НЕ несёт идентификатор списка (tip) — теоретически валидный курсор,
выданный для одного tip (например, question), можно подставить в URL
другого tip с таким же именем sort_field (например, result), и сервер
его примет, так как decode_cursor() ничего не знает о том, для какого
списка курсор был выдан. Практического риска ниже, чем кажется: подпись
signing защищает только от подделки значений, а не от "конфьюжна списков"
между собой. Если это станет проблемой — курсор нужно будет расширить
полем "tip" и сверять его в paginate_keyset(), это отдельная будущая
доработка, не блокирующая текущий этап.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode

from django.db.models import Q, QuerySet
from django.http import HttpRequest

from core.dashboard.pagination.registry import ListSpec
from core.dashboard.pagination.tokens import (
    decode_cursor,
    encode_cursor,
    make_filters_fingerprint,
)

_VALID_DIRECTIONS = ("start", "next", "prev", "last")

# (natural_sort_direction, requested_direction) -> оператор сравнения
# относительно значения курсора.
#   desc + next -> берём строки МЕНЬШЕ курсора (продолжаем убывающий список)
#   desc + prev -> берём строки БОЛЬШЕ курсора (идём назад, к началу списка)
#   asc  + next -> берём строки БОЛЬШЕ курсора
#   asc  + prev -> берём строки МЕНЬШЕ курсора
_COMPARISON_OP = {
    ("desc", "next"): "lt",
    ("desc", "prev"): "gt",
    ("asc", "next"): "gt",
    ("asc", "prev"): "lt",
}


@dataclass
class KeysetPage:
    """
    Результат курсорной выборки одного списка.

    :param items: строки текущей страницы, ВСЕГДА в натуральном порядке
        отображения (spec.sort_direction) — независимо от того, каким
        внутренним order_by они реально были получены из БД.
    :param has_prev: есть ли страница до текущей.
    :param has_next: есть ли страница после текущей.
    :param urls: ссылки для шаблона — ключи "start"/"prev"/"next"/"last".
        None, если переход недоступен — шаблон должен рендерить кнопку
        неактивной, а не битую ссылку без courser/dir.
    """
    items: List[Any]
    has_prev: bool
    has_next: bool
    urls: Dict[str, Optional[str]] = field(default_factory=dict)


def _natural_order_fields(spec: ListSpec) -> List[str]:
    """Поля order_by() для натурального (spec.sort_direction) порядка."""
    sign = "-" if spec.sort_direction == "desc" else ""
    if spec.sort_field == "id":
        return [f"{sign}id"]
    return [f"{sign}{spec.sort_field}", f"{sign}id"]


def _reversed_order_fields(spec: ListSpec) -> List[str]:
    """Поля order_by() для порядка, ОБРАТНОГО натуральному."""
    sign = "" if spec.sort_direction == "desc" else "-"
    if spec.sort_field == "id":
        return [f"{sign}id"]
    return [f"{sign}{spec.sort_field}", f"{sign}id"]


def _cursor_filter(spec: ListSpec, sort_value: Any, id_value: int, direction: str) -> Q:
    """
    Строит Q-фильтр "строки по одну сторону от курсора" для direction
    "next"/"prev".

    Если spec.sort_field == "id" — сравнение ПРОСТОЕ (id__lt/id__gt),
    составной Q не нужен: id уникален сам по себе, отдельный tie-breaker
    избыточен (variant, selfquestion идут этим путём).

    Иначе — составной Q(sort_field__op=X) | Q(sort_field=X, id__op=Y):
    основное условие ловит строго "дальше" по sort_field, а вторая часть —
    строки с ТЕМ ЖЕ значением sort_field, но однозначно упорядоченные
    по id (tie-break при совпадающих значениях сортировки).
    """
    op = _COMPARISON_OP[(spec.sort_direction, direction)]

    if spec.sort_field == "id":
        return Q(**{f"id__{op}": id_value})

    field_op_lookup = f"{spec.sort_field}__{op}"
    id_op_lookup = f"id__{op}"
    return Q(**{field_op_lookup: sort_value}) | Q(**{spec.sort_field: sort_value, id_op_lookup: id_value})


def _sort_value_of(item: Any, spec: ListSpec) -> Any:
    if spec.sort_field == "id":
        return item.pk
    return getattr(item, spec.sort_field)


def _extract_filter_params(request: HttpRequest) -> Dict[str, Any]:
    """
    GET-параметры БЕЗ служебных cursor/dir — то, что реально должно входить
    в фингерпринт фильтров (см. tokens.make_filters_fingerprint). Сейчас
    (пока в списках дашборда нет фильтров) этот словарь на практике всегда
    пуст — механизм закладывается на будущее.
    """
    return {k: v for k, v in request.GET.items() if k not in ("cursor", "dir")}


def _build_url(request: HttpRequest, dir_value: str, cursor_token: Optional[str] = None) -> str:
    """
    Собирает URL текущего пути с обновлёнными cursor/dir, сохраняя
    остальные текущие GET-параметры (будущие фильтры не теряются).
    """
    params = request.GET.copy()
    params["dir"] = dir_value
    if cursor_token is None:
        params.pop("cursor", None)
    else:
        params["cursor"] = cursor_token
    return f"{request.path}?{urlencode(params)}"


def paginate_keyset(queryset: QuerySet, spec: ListSpec, request: HttpRequest) -> KeysetPage:
    """
    Нарезает queryset постранично через курсор (?cursor=, ?dir=) согласно
    спецификации spec (sort_field/sort_direction/page_size).

    Невалидный/просроченный/отсутствующий cursor, мусорный dir, либо
    расхождение filters_fingerprint курсора с текущими фильтрами — во всех
    случаях мягкий откат на первую страницу, никогда не исключение наружу.
    """
    raw_dir = request.GET.get("dir", "start")
    if raw_dir not in _VALID_DIRECTIONS:
        raw_dir = "start"

    cursor_token = request.GET.get("cursor")
    cursor_data = decode_cursor(cursor_token) if cursor_token else None

    current_fp = make_filters_fingerprint(_extract_filter_params(request))

    if cursor_data is not None and cursor_data.get("fp") != current_fp:
        # Фильтры изменились с момента выдачи курсора (или курсор битый
        # содержимо) — курсор больше не доверенный, сбрасываем на старт.
        cursor_data = None

    direction = raw_dir
    if direction in ("next", "prev") and cursor_data is None:
        direction = "start"

    if direction == "start":
        qs = queryset.order_by(*_natural_order_fields(spec))
        fetch = list(qs[: spec.page_size + 1])
        has_next = len(fetch) > spec.page_size
        items = fetch[: spec.page_size]
        has_prev = False

    elif direction == "next":
        filt = _cursor_filter(spec, cursor_data["sort"], cursor_data["id"], "next")
        qs = queryset.filter(filt).order_by(*_natural_order_fields(spec))
        fetch = list(qs[: spec.page_size + 1])
        has_next = len(fetch) > spec.page_size
        items = fetch[: spec.page_size]
        # Мы попали сюда по валидному курсору предыдущей страницы —
        # значит страница "до текущей" точно существует.
        has_prev = True

    elif direction == "prev":
        filt = _cursor_filter(spec, cursor_data["sort"], cursor_data["id"], "prev")
        qs = queryset.filter(filt).order_by(*_reversed_order_fields(spec))
        fetch = list(qs[: spec.page_size + 1])
        has_prev = len(fetch) > spec.page_size
        items = list(reversed(fetch[: spec.page_size]))
        # Мы пришли сюда через "назад" — значит после этой страницы точно
        # есть та, с которой мы начали навигацию.
        has_next = True

    else:  # direction == "last"
        total_count = queryset.count()
        if total_count == 0:
            items, has_prev, has_next = [], False, False
        else:
            remainder = total_count % spec.page_size
            last_page_len = remainder or spec.page_size
            qs = queryset.order_by(*_reversed_order_fields(spec))
            fetch = list(qs[: last_page_len + 1])
            has_prev = len(fetch) > last_page_len
            items = list(reversed(fetch[:last_page_len]))
            has_next = False

    urls: Dict[str, Optional[str]] = {
        "start": _build_url(request, "start") if has_prev else None,
        "last": _build_url(request, "last") if has_next else None,
        "prev": (
            _build_url(request, "prev", encode_cursor(
                sort_value=_sort_value_of(items[0], spec),
                id_value=items[0].pk,
                direction="prev",
                filters_fingerprint=current_fp,
            ))
            if (has_prev and items) else None
        ),
        "next": (
            _build_url(request, "next", encode_cursor(
                sort_value=_sort_value_of(items[-1], spec),
                id_value=items[-1].pk,
                direction="next",
                filters_fingerprint=current_fp,
            ))
            if (has_next and items) else None
        ),
    }

    return KeysetPage(items=items, has_prev=has_prev, has_next=has_next, urls=urls)