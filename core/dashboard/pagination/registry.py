"""
core/dashboard/pagination/registry.py
────────────────────────────────────────
Реестр спецификаций списков дашборда для пагинации.

Каждый список (tip), доступный через /dashboard/list/<tip>/, описывается
одной ListSpec — она фиксирует, каким движком пагинации он обслуживается
и (для offset/keyset) по какому полю идёт сортировка.

ВАЖНО (этот этап): для ВСЕХ списков engine="none" — это чистый рефакторинг,
переносящий существующие _QUERYSETS-лямбды (core/dashboard/list.py) под
единый реестр без изменения поведения. Подключение offset/keyset-движков
к конкретным спискам — отдельные последующие этапы (см. будущий
core/dashboard/pagination/facade.py).

sort_field/sort_direction уже проставлены корректно даже для engine="none" —
они сверены с текущими order_by() в _QUERYSETS и служат подготовкой на
будущее: когда какой-то список переключат на "keyset"/"offset", реестр
трогать повторно не придётся.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, Literal, Optional

from django.db.models import QuerySet

from core.dashboard.list import _QUERYSETS

from core.dashboard.selfuser_crud import _selfuser_queryset
Engine = Literal["none", "offset", "keyset"]
SortDirection = Literal["asc", "desc"]


@dataclass(frozen=True)
class ListSpec:
    """
    Спецификация одного списка дашборда для пагинации.

    :param queryset_factory: без-аргументная функция, возвращающая базовый
        QuerySet списка (со всеми select_related/prefetch_related/annotate) —
        переиспользуется 1-в-1 из core.dashboard.list._QUERYSETS, чтобы
        логика построения queryset жила в одном месте и не расходилась
        между обычным списком и его пагинированной версией.
    :param engine:
        "none"   — пагинация не применяется, список рендерится целиком,
                   как сейчас (текущее поведение всех 9 списков).
        "offset" — LIMIT/OFFSET с COUNT() (для списков с невычислимой
                   через индекс сортировкой, напр. агрегаты/Subquery).
        "keyset" — курсорная пагинация по (sort_field, id).
    :param sort_field: поле сортировки. Для списков, сортируемых
        напрямую по id (variant, selfquestion) — это "id", и отдельный
        tie-breaker не нужен: id уникален и уже проиндексирован как PK.
        Для engine="none" это поле пока чисто информационное (описывает
        текущую сортировку queryset) — движками ещё не используется.
    :param sort_direction: направление сортировки — ДОЛЖНО совпадать
        с order_by() внутри соответствующей лямбды _QUERYSETS.
    :param page_size: размер страницы для offset/keyset-движков
        (используется только когда engine != "none").
    """
    queryset_factory: Callable[[], QuerySet]
    engine: Engine
    sort_field: Optional[str]
    sort_direction: SortDirection
    page_size: int = 20


# ─────────────────────────────────────────────────────────────────────────────
# Реестр
# ─────────────────────────────────────────────────────────────────────────────
# sort_field/sort_direction сверены с order_by() в core/dashboard/list.py::
# _QUERYSETS на момент написания этого файла:
#
#   subject      -> order_by('-created')
#   potok        -> order_by('-start')      (НЕ 'created' — см. комментарий ниже)
#   result       -> order_by('-created')
#   user         -> order_by('-created')
#   quiz         -> order_by('-created')
#   variant      -> order_by('id')
#   question     -> order_by('-created')
#   selfctg      -> order_by('-created')
#   selfquestion -> order_by('-id')
#
# Если order_by() в _QUERYSETS изменится — обнови и здесь, иначе при
# будущем переключении engine на "keyset"/"offset" курсор/страница будут
# считаться по неверному полю.
LIST_REGISTRY: Dict[str, ListSpec] = {
    "subject": ListSpec(
        queryset_factory=_QUERYSETS["subject"],
        engine="none",
        sort_field="created",
        sort_direction="desc",
    ),
    "potok": ListSpec(
        queryset_factory=_QUERYSETS["potok"],
        engine="none",
        # ВАЖНО: Potok сортируется по 'start' (дата начала потока), а не
        # по 'created' — это осознанная бизнес-сортировка, сохраняем как
        # есть, а не унифицируем с остальными списками "для красоты".
        sort_field="start",
        sort_direction="desc",
    ),
    "result": ListSpec(
        queryset_factory=_QUERYSETS["result"],
        # Первый список, реально переключённый на Keyset Engine — самый
        # быстрорастущий лог в дашборде. Опорный индекс (created, id)
        # добавлен в core/migrations/0010_result_created_not_null.py.
        engine="keyset",
        sort_field="created",
        sort_direction="desc",
    ),
    "user": ListSpec(
        queryset_factory=_QUERYSETS["user"],
        # Третий список, переключённый на Keyset Engine (после result,
        # question). Опорный индекс (created, id) — user_created_id_idx.
        # created — DateField (дневная точность): несколько User с
        # одинаковым created — штатная ситуация, разруливается tie-break'ом
        # по id внутри keyset_engine.py (составной Q как для datetime-полей).
        engine="keyset",
        sort_field="created",
        sort_direction="desc",
    ),
    "quiz": ListSpec(
        queryset_factory=_QUERYSETS["quiz"],
        engine="none",
        sort_field="created",
        sort_direction="desc",
    ),
    "variant": ListSpec(
        queryset_factory=_QUERYSETS["variant"],
        engine="none",
        # Сортировка напрямую по id (см. _QUERYSETS['variant']) — id уже
        # уникален и уже проиндексирован как PK, отдельный tie-breaker
        # не понадобится даже при переключении на keyset.
        sort_field="id",
        sort_direction="asc",
    ),
    "question": ListSpec(
        queryset_factory=_QUERYSETS["question"],
        # Второй список, переключённый на Keyset Engine (после result).
        # Опорный индекс (created, id) — question_created_id_idx.
        engine="keyset",
        sort_field="created",
        sort_direction="desc",
    ),
    "selfctg": ListSpec(
        queryset_factory=_QUERYSETS["selfctg"],
        engine="none",
        sort_field="created",
        sort_direction="desc",
    ),
    "selfquestion": ListSpec(
        queryset_factory=_QUERYSETS["selfquestion"],
        engine="none",
        # Сортировка напрямую по id (см. _QUERYSETS['selfquestion']).
        sort_field="id",
        sort_direction="desc",
    ),
    "selfuser": ListSpec(
        queryset_factory=_selfuser_queryset,
        engine="offset",
        # Сортировка построена через F("last_attempt").desc(nulls_last=True)
        # поверх annotate(Max(...)/Subquery(...)) — это НЕ физическая колонка
        # таблицы SelfUser, индекс здесь принципиально не помогает.
        # sort_field указан как имя аннотации ЧИСТО информационно —
        # offset_engine.py его не читает и не использует.
        #
        # ВАЖНО: текущий URL-роутинг (/dashboard/list/selfresult/) вызывает
        # list_selfuser() напрямую отдельной веткой в dlist() (см.
        # core/dashboard/list.py) — ДО обращения к реестру, ключом "selfresult",
        # а не "selfuser". Эта запись реестра сейчас не участвует в
        # реальной маршрутизации, она существует для документирования
        # архитектурного решения (offset — постоянно, не временно) и на
        # случай, если в будущем selfuser/selfresult унифицируют с
        # остальными списками через paginate_list().
        sort_field="last_attempt",
        sort_direction="desc",
        page_size=20,
    ),
}


def get_list_spec(tip: str) -> Optional[ListSpec]:
    """
    Возвращает ListSpec для данного tip, либо None, если tip не
    зарегистрирован. "new" сюда не входит намеренно — он обрабатывается
    в dlist() отдельной веткой ДО обращения к реестру и не является
    списком в смысле пагинации.
    """
    return LIST_REGISTRY.get(tip)