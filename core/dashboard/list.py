from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from core.models import ClassRooms, Question, Result, Subject, Test, User, Variant

# Словарь вместо цепочки if-elif: добавление нового типа — одна строка.
_QUERYSETS = {
    "subject":   lambda: Subject.objects.all(),
    "classroom": lambda: ClassRooms.objects.all(),
    "result":    lambda: Result.objects.select_related('user', 'test').order_by('-created'),
    "user":      lambda: User.objects.all(),
    "quiz":      lambda: Test.objects.select_related('subject').order_by('-created'),
    "variant":   lambda: Variant.objects.select_related('question').all(),
    "question":  lambda: Question.objects.select_related('varianta__test').all(),
}       

_DISPLAY_NAMES = {
    "subject":   "Subject",
    "classroom": "ClassRoom",
    "result":    "Result",
    "user":      "User",
    "quiz":      "Quiz",
    "variant":   "Variant",
    "question":  "Question",
}


@login_required(login_url="login")
def dlist(request, tip=None):
    if not request.user.in_dashboard:
        return redirect('lock')

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
