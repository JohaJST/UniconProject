"""
core/dashboard/user_crud.py
────────────────────────────
CRUD-view для пользователя (User) в дашборде.

Реализован только просмотр (view_user) — по аналогии с
core/dashboard/subject_crud.py::view_subject /
core/dashboard/classroom_crud.py::view_classroom. RBAC и sliding-window
таймаут дашборда проверяет DashboardSecurityMiddleware — свои проверки
прав здесь не нужны.
"""
from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.db.models import Avg
from django.shortcuts import get_object_or_404, render

from core.models import Result, User


@login_required(login_url="login")
def view_user(request, pk):
    """
    Карточка пользователя: личные данные + история результатов и
    средний балл (тот же запрос, что в core/quiz/index.py::user_profile).
    """
    target_user = get_object_or_404(
        User.objects.select_related('classroom'), pk=pk
    )

    results = (
        Result.objects
        .filter(user=target_user)
        .select_related('test', 'test__subject')
        .order_by('-created')
    )

    average = results.aggregate(avg=Avg('foyiz'))['avg']

    ctx = {
        "target_user": target_user,
        "results": results,
        "average": round(average, 1) if average is not None else None,
    }
    return render(request, "pages/dashboard/user_detail.html", ctx)