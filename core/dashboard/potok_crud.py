"""
core/dashboard/potok_crud.py
────────────────────────────────
CRUD-view для потока (Potok) в дашборде.

Реализованы просмотр (view_potok) и редактирование (edit_potok).
RBAC и sliding-window таймаут дашборда проверяет DashboardSecurityMiddleware —
свои проверки прав здесь не нужны.
"""
from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db.models import Avg, Count
from django.db.models.fields import DateTimeField
from django.shortcuts import get_object_or_404, redirect, render

from core.models import Potok, Test, User
from core.models.auth import Role


@login_required(login_url="login")
def view_potok(request, pk):
    """
    Карточка потока: даты начала/конца, список учеников (со счётчиком
    попыток и средним баллом) и тесты потока.
    """
    potok = get_object_or_404(Potok, pk=pk)

    students = (
        User.objects
        .filter(potok=potok, role=Role.STUDENT)
        .select_related('potok')
        .annotate(
            attempt_count=Count('results', distinct=True),
            avg_score=Avg('results__foyiz'),
        )
        .order_by('last_name', 'name')
    )

    tests = (
        Test.objects
        .filter(potok=potok)
        .select_related('subject')
        .annotate(question_count=Count('questions', distinct=True))
        .order_by('-created')
    )

    ctx = {
        "potok": potok,
        "students": students,
        "tests": tests,
    }
    return render(request, "pages/dashboard/potok_detail.html", ctx)


@login_required(login_url="login")
def edit_potok(request, pk):
    """
    Редактирование потока: меняются только даты начала и конца.
    """
    potok = get_object_or_404(Potok, pk=pk)

    if request.method == "POST":
        start = request.POST.get("potok_start")
        end = request.POST.get("potok_end")

        if not start or not end:
            return render(request, "pages/dashboard/potok_edit.html", {
                "potok": potok,
                "error": "Даты начала и конца потока обязательны",
                "post_data": request.POST,
            })

        # Парсим ДО сохранения: DateTimeField.to_python принимает ISO-строку
        # формы (datetime-local: 2026-05-22T09:00) и отклоняет мусор —
        # без try/except здесь был бы 500 на ValidationError.
        try:
            start_dt = DateTimeField().to_python(start)
            end_dt = DateTimeField().to_python(end)
            if not start_dt or not end_dt:
                raise ValueError("empty datetime")
        except (ValidationError, ValueError):
            return render(request, "pages/dashboard/potok_edit.html", {
                "potok": potok,
                "error": "Неверный формат дат. Используйте формат: 2026-05-22T09:00",
                "post_data": request.POST,
            })

        if end_dt <= start_dt:
            return render(request, "pages/dashboard/potok_edit.html", {
                "potok": potok,
                "error": "Дата конца потока должна быть позже даты начала",
                "post_data": request.POST,
            })

        potok.start = start_dt
        potok.end = end_dt
        potok.save()

        return redirect("action", status="view", path="potok", pk=potok.id)

    return render(request, "pages/dashboard/potok_edit.html", {
        "potok": potok,
    })
