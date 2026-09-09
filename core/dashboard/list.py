import operator
from functools import reduce

from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q, QuerySet
from django.shortcuts import render

from core.models import Potok, Question, Result, Subject, Test, User, Variant
from core.models.self import SelfCtg, SelfQuestion

from .selfuser_crud import list_selfuser

_QUERYSETS = {
    "subject":      lambda: Subject.objects.all().order_by('-created'),
    "potok":        lambda: Potok.objects.all().order_by('-start'),
    "result":       lambda: Result.objects.select_related('user', 'test').order_by('-created'),
    "user":         lambda: User.objects.all().order_by('-created'),
    "quiz":         lambda: Test.objects.select_related('subject').order_by('-created'),
    "variant":      lambda: Variant.objects.select_related('question').all().order_by('id'),
    "question":     lambda: Question.objects.select_related('test__subject').all().order_by('-created'),
    "selfctg":      lambda: SelfCtg.objects.annotate(question_count=Count('selfquestion')).order_by('-created'),
    "selfquestion": lambda: SelfQuestion.objects.prefetch_related('selfanswer_set').select_related('ctg').order_by('-id'),
}

_DISPLAY_NAMES = {
    "subject":      "Subject",
    "potok":        "Potok",
    "result":       "Result",
    "user":         "User",
    "quiz":         "Quiz",
    "variant":      "Variant",
    "question":     "Question",
    "selfctg":      "SelfCtg",
    "selfquestion": "Self Question",
}

# ─────────────────────────────────────────────────────────────────────────────
# Локальный текстовый поиск (?q=)
# ─────────────────────────────────────────────────────────────────────────────
# Поля указываются относительно МОДЕЛИ, которую реально возвращает
# соответствующая фабрика в _QUERYSETS (а не относительно "смыслового"
# объекта — так, "quiz" -> Test.objects..., поэтому путь к предмету
# теста — "subject__name", а не "test__subject__name"; тот же префикс
# "test__subject__name" используется у "question", т.к. там базовая
# модель — Question, и к Subject нужно идти через test).
#
# Отсутствие tip в этом словаре (или пустой список) означает "поиск для
# этого списка не поддерживается" — apply_search() в этом случае вернёт
# queryset без изменений, а не упадёт.
SEARCH_FIELDS: dict[str, list[str]] = {
    "subject":      ["name_uz", "name_ru", "name_en"],
    "potok":        [],  # нет текстовых полей, по которым имеет смысл искать
    "result":       ["user__name", "user__last_name", "user__username",
                        "test__subject__name_uz", "test__subject__name_ru", 
                        "test__subject__name_en", "time", "foyiz", "result"
                    ],
    "user":         ["name", "last_name", "username", "company_name", 
                        "position", "subject__name_uz", "subject__name_ru",
                        "subject__name_en"
                    ],
    "quiz":         ["subject__name_uz", "subject__name_ru", 
                        "subject__name_en", "potok__start", "potok__end"
                    ],
    "variant":      ["text_uz", "text_ru", "text_en", "question__text_uz",
                        "question__text_ru", "question__text_en",
                        "question__test__subject__name_uz", "question__test__subject__name_ru",
                        "question__test__subject__name_en"
                    ],
    "question":     ["text_uz", "text_ru", "text_en", "test__subject__name_uz",
                        "test__subject__name_ru", "test__subject__name_en"
                    ],
    "selfctg":      ["name_uz", "name_ru", "name_en"],
    "selfquestion": ["text_uz", "text_ru", "text_en", "ctg__name_uz",
                        "ctg__name_ru", "ctg__name_en"],
}


def apply_search(qs: QuerySet, tip: str, query: str) -> QuerySet:
    """
    Фильтрует queryset по свободному текстовому запросу ``query``, используя
    поля из SEARCH_FIELDS[tip] (case-insensitive icontains, объединённые
    через OR).

    Вызывать СТРОГО после queryset_factory() и ДО передачи в движки
    пагинации (keyset_engine/offset_engine) — фильтрация должна сузить
    выборку раньше, чем движок начнёт считать страницы/курсоры, иначе
    постраничность будет считаться по неотфильтрованным данным.

    :param qs: queryset, полученный из spec.queryset_factory() (см. registry.py)
    :param tip: ключ списка, тот же, что используется в _QUERYSETS/LIST_REGISTRY
    :param query: сырой ?q= из request.GET, может быть пустой строкой/None
    :return: qs без изменений, если query пуст или для tip не заданы
        SEARCH_FIELDS; иначе — qs.filter(Q(...) | Q(...) | ...).distinct()
        (.distinct() обязателен: OR через join-поля из разных связанных
        таблиц может размножить строки).
    """
    query = (query or "").strip()
    fields = SEARCH_FIELDS.get(tip) or []
    if not query or not fields:
        return qs

    lookups = reduce(
        operator.or_,
        (Q(**{f"{field}__icontains": query}) for field in fields),
    )
    return qs.filter(lookups).distinct()


@login_required(login_url="login")
def dlist(request, tip=None):
    # Проверка доступа к дашборду теперь в DashboardSecurityMiddleware —
    # guard "if not request.user.in_dashboard" удалён.
    if tip == "new":
        return render(request, 'pages/dashboard/new.html', {
            "subjects": Subject.objects.all(),
            "potoks": Potok.objects.all(),
        })

    # "selfresult" — теперь не плоский список результатов, а агрегированный
    # список участников (SelfUser) с их статистикой Self Check; клик по
    # участнику открывает подробную карточку с историей попыток
    # (см. core/dashboard/selfuser_crud.py).
    # ПРИМЕЧАНИЕ: поиск для этого маршрута сюда не подключён — list_selfuser
    # работает через отдельный offset-queryset (_selfuser_queryset), это
    # отдельная задача на будущее (SEARCH_FIELDS["selfuser"] тут не поможет,
    # т.к. этот путь вообще не проходит через paginate_list/facade.py).
    if tip == "selfresult":
        return list_selfuser(request)

    from core.dashboard.pagination.facade import paginate_list

    page = paginate_list(tip, request)
    if page is None:
        return render(request, 'pages/dashboard/list.html')

    # page.pagination — пустой dict {} для engine="none" (истинностное
    # значение — False), поэтому {% if pagination %} в list.html молчит
    # для всех списков, кроме реально пагинированных. search_query
    # передаём отдельно — понадобится в list.html для value="" поля ввода,
    # чтобы поиск не сбрасывался визуально при переходе по страницам.
    return render(request, 'pages/dashboard/list.html', {
        "name": _DISPLAY_NAMES[tip],
        "root": page.items,
        "pagination": page.pagination,
        "search_query": request.GET.get("q", ""),
        "search_supported": bool(SEARCH_FIELDS.get(tip)),
    })