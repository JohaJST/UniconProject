from django.contrib.auth.decorators import login_required
from django.db.models import Count
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
    if tip == "selfresult":
        return list_selfuser(request)

    from core.dashboard.pagination.registry import get_list_spec

    spec = get_list_spec(tip)
    if spec is None:
        return render(request, 'pages/dashboard/list.html')

    # Этот этап: у всех списков engine="none" — поведение идентично
    # прежнему (весь queryset целиком, без пагинации). Подключение
    # offset/keyset-движков — отдельные последующие этапы, см.
    # core/dashboard/pagination/facade.py.
    return render(request, 'pages/dashboard/list.html', {
        "name": _DISPLAY_NAMES[tip],
        "root": spec.queryset_factory(),
    })