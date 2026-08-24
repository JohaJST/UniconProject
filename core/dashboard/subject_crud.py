"""
core/dashboard/subject_crud.py
────────────────────────────────
CRUD-view для предмета (Subject) в дашборде.

Реализованы просмотр (view_subject) и редактирование (edit_subject).
RBAC и sliding-window таймаут дашборда проверяет DashboardSecurityMiddleware —
свои проверки прав здесь не нужны.
"""
from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.db.models import Avg, Count
from django.shortcuts import get_object_or_404, redirect, render

from core.models import Subject, Test


@login_required(login_url="login")
def view_subject(request, pk):
    """
    Карточка предмета: название на 3 языках, список тестов предмета
    (со счётчиком вопросов) и средний % по результатам этих тестов.
    """
    subject = get_object_or_404(Subject, pk=pk)

    tests = (
        Test.objects
        .filter(subject=subject)
        .select_related('potok')
        .annotate(question_count=Count('questions', distinct=True))
        .order_by('-created')
    )

    avg_score = (
        Test.objects
        .filter(subject=subject)
        .aggregate(avg=Avg('results__foyiz'))['avg']
    )

    ctx = {
        "subject": subject,
        "tests": tests,
        "avg_score": round(avg_score, 1) if avg_score is not None else None,
    }
    return render(request, "pages/dashboard/subject_detail.html", ctx)


@login_required(login_url="login")
def edit_subject(request, pk):
    """
    Редактирование предмета: перевод названия (uz/ru/en, тот же fallback-
    паттерн, что и в create — core/dashboard/action.py).
    """
    subject = get_object_or_404(Subject, pk=pk)

    if request.method == "POST":
        raw_name = (request.POST.get("subject_name") or "").strip()
        name_uz = (request.POST.get("subject_name_uz") or "").strip() or raw_name
        name_ru = (request.POST.get("subject_name_ru") or "").strip()
        name_en = (request.POST.get("subject_name_en") or "").strip()

        if not (name_uz or name_ru or name_en):
            return render(request, "pages/dashboard/subject_edit.html", {
                "subject": subject,
                "error": "Название предмета обязательно хотя бы на одном языке",
                "post_data": request.POST,
            })

        subject.name_uz = name_uz
        subject.name_ru = name_ru
        subject.name_en = name_en
        subject.save()

        return redirect("action", status="view", path="subject", pk=subject.id)

    return render(request, "pages/dashboard/subject_edit.html", {
        "subject": subject,
    })
