from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from core.models import ClassRooms, Question, Result, Subject, Test, User, Variant
from core.models.self import SelfQuestion, SelfResult

_QUERYSETS = {
    "subject":      lambda: Subject.objects.all().order_by('-created'),
    "classroom":    lambda: ClassRooms.objects.all().order_by('-created'),
    "result":       lambda: Result.objects.select_related('user', 'test').order_by('-created'),
    "user":         lambda: User.objects.all().order_by('-created'),
    "quiz":         lambda: Test.objects.select_related('subject').order_by('-created'),
    "variant":      lambda: Variant.objects.select_related('question').all().order_by('-created'),
    "question":     lambda: Question.objects.select_related('varianta__test').all().order_by('-created'),
    "selfquestion": lambda: SelfQuestion.objects.prefetch_related('selfanswer_set').order_by('-id'),
    "selfresult":   lambda: SelfResult.objects.order_by('-created'),
}

_DISPLAY_NAMES = {
    "subject":      "Subject",
    "classroom":    "ClassRoom",
    "result":       "Result",
    "user":         "User",
    "quiz":         "Quiz",
    "variant":      "Variant",
    "question":     "Question",
    "selfquestion": "Self Question",
    "selfresult":   "Self Result",
}


@login_required(login_url="login")
def dlist(request, tip=None):
    # Проверка доступа к дашборду теперь в DashboardSecurityMiddleware —
    # guard "if not request.user.in_dashboard" удалён.
    if tip == "new":
        return render(request, 'pages/dashboard/new.html', {
            "subjects": Subject.objects.all(),
            "classrooms": ClassRooms.objects.all(),
        })

    qs_factory = _QUERYSETS.get(tip)
    if qs_factory is None:
        return render(request, 'pages/dashboard/list.html')

    return render(request, 'pages/dashboard/list.html', {
        "name": _DISPLAY_NAMES[tip],
        "root": qs_factory(),
    })