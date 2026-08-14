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
from django.shortcuts import get_object_or_404, redirect, render

from core.models import ClassRooms, Result, User


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


# ─────────────────────────────────────────────────────────────────────────────
# edit_user
# ─────────────────────────────────────────────────────────────────────────────

@login_required(login_url="login")
def edit_user(request, pk):
    """
    Редактирование пользователя.

    Пароль опционален: пустое поле "password" в форме означает "не менять" —
    в этом случае текущий хэш пароля не трогаем и set_password() не вызываем.
    Ошибки валидации/сохранения (как в action.py::form()) не приводят к 500 —
    форма возвращается с error и уже введёнными данными (user_data=request.POST).
    """
    target_user = get_object_or_404(User, pk=pk)

    if request.method == "POST":
        data = request.POST
        try:
            target_user.name = data["first_name"]
            target_user.last_name = data["last_name"]

            birthday = data.get("birthday") or None
            target_user.birthday = birthday

            target_user.phone = data.get("phone") or None

            classroom_id = data.get("classroom")
            target_user.classroom_id = int(classroom_id) if classroom_id else None

            target_user.role = int(data["role"])
            target_user.lang = data.get("lang")

            password = data.get("password")
            if password:
                target_user.set_password(password)

            target_user.save()
        except Exception:
            return render(
                request,
                "pages/dashboard/user_edit.html",
                {
                    "target_user": target_user,
                    "classrooms": ClassRooms.objects.all(),
                    "error": "Проверьте данные",
                    "user_data": data,
                },
            )

        return redirect("action", status="view", path="user", pk=target_user.id)

    return render(request, "pages/dashboard/user_edit.html", {
        "target_user": target_user,
        "classrooms": ClassRooms.objects.all(),
    })