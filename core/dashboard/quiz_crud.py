"""
core/dashboard/quiz_crud.py
────────────────────────────
CRUD-view для теста (Test) в дашборде.

Реализован только просмотр (view_quiz) — по аналогии с
core/dashboard/subject_crud.py::view_subject /
core/dashboard/classroom_crud.py::view_classroom. RBAC и sliding-window
таймаут дашборда проверяет DashboardSecurityMiddleware — свои проверки
прав здесь не нужны.
"""
from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.db.models import Avg
from django.shortcuts import get_object_or_404, render

from core.models import ClassRooms, Result, Test


@login_required(login_url="login")
def view_quiz(request, pk):
    """
    Карточка теста: метаданные (название/описание/предмет/статус),
    привязанные классы, статистика попыток + полная структура
    Variant -> Question -> Answer для просмотра содержимого теста.

    prefetch_related('variantas__questions__answers') обязателен: в шаблоне
    цикл variantas -> questions -> answers иначе даст классический N+1
    (отдельный запрос на каждый Question и на каждый Variant ответа).
    """
    test = get_object_or_404(
        Test.objects
        .select_related('subject')
        .prefetch_related('variantas__questions__answers'),
        pk=pk,
    )

    classrooms = (
        ClassRooms.objects
        .filter(test_classrooms__test=test)
        .distinct()
    )

    results = Result.objects.filter(test=test)
    attempt_count = results.count()
    avg_score = results.aggregate(avg=Avg('foyiz'))['avg']

    ctx = {
        "test": test,
        "classrooms": classrooms,
        "attempt_count": attempt_count,
        "avg_score": round(avg_score, 1) if avg_score is not None else None,
    }
    return render(request, "pages/dashboard/quiz_detail.html", ctx)