"""
core/dashboard/selfctg_crud.py
────────────────────────────────
CRUD-view для категории Self Check (SelfCtg) в дашборде.

Реализованы просмотр (view_selfctg) и редактирование (edit_selfctg).
Создание — в core/dashboard/action.py (status="create", path="selfctg"),
удаление — там же (status="delete", path="selfctg") с SET_NULL на вопросах.

RBAC и sliding-window таймаут дашборда проверяет DashboardSecurityMiddleware —
свои проверки прав здесь не нужны.
"""
from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.db.models import Count
from django.shortcuts import get_object_or_404, redirect, render

from core.models.self import SelfCtg, SelfQuestion


@login_required(login_url="login")
def view_selfctg(request, pk):
    """
    Карточка категории: название на 3 языках + список вопросов категории.
    """
    ctg = get_object_or_404(SelfCtg, pk=pk)

    questions = (
        SelfQuestion.objects
        .filter(ctg=ctg)
        .prefetch_related('selfanswer_set')
        .order_by('id')
    )

    ctx = {
        "ctg": ctg,
        "questions": questions,
        "question_count": questions.count(),
    }
    return render(request, "pages/dashboard/selfctg_detail.html", ctx)


@login_required(login_url="login")
def edit_selfctg(request, pk):
    """
    Редактирование категории: название + переводы (uz/ru/en).

    Fallback-паттерн как у subject_crud: пустой uz-перевод заполняется
    значением видимого поля формы.
    """
    ctg = get_object_or_404(SelfCtg, pk=pk)

    if request.method == "POST":
        raw_name = (request.POST.get("selfctg_name") or "").strip()
        name_uz = (request.POST.get("selfctg_name_uz") or "").strip() or raw_name
        name_ru = (request.POST.get("selfctg_name_ru") or "").strip()
        name_en = (request.POST.get("selfctg_name_en") or "").strip()

        if not (name_uz or name_ru or name_en):
            return render(request, "pages/dashboard/selfctg_edit.html", {
                "ctg": ctg,
                "error": "Название категории обязательно хотя бы на одном языке",
                "post_data": request.POST,
            })

        ctg.name_uz = name_uz
        ctg.name_ru = name_ru
        ctg.name_en = name_en
        ctg.save()

        return redirect("action", status="view", path="selfctg", pk=ctg.id)

    return render(request, "pages/dashboard/selfctg_edit.html", {
        "ctg": ctg,
    })
