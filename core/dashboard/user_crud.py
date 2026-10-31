"""
core/dashboard/user_crud.py
────────────────────────────
CRUD-view для пользователя (User) в дашборде.

Просмотр (view_user) и редактирование (edit_user). RBAC и sliding-window
таймаут дашборда проверяет DashboardSecurityMiddleware — свои проверки
прав здесь не нужны.
"""
from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.db.models import Avg
from django.shortcuts import get_object_or_404, redirect, render

from core.models import Potok, Result, Subject, User
from core.models.auth import Role


@login_required(login_url="login")
def view_user(request, pk):
    """
    Карточка пользователя: личные данные + история результатов и
    средний балл (тот же запрос, что в core/quiz/index.py::user_profile).
    """
    target_user = get_object_or_404(
        User.objects.select_related('potok', 'subject'), pk=pk
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


@login_required(login_url="login")
def edit_user(request, pk):
    """
    Редактирование пользователя.

    Пароль опционален: пустое поле "password" в форме означает "не менять" —
    в этом случае текущий хэш пароля не трогаем и set_password() не вызываем.
    Ошибки валидации/сохранения не приводят к 500 — форма возвращается
    с error и уже введёнными данными (user_data=request.POST).
    """
    target_user = get_object_or_404(User, pk=pk)
    potoks = Potok.objects.all()
    subjects = Subject.objects.all().order_by("name_uz")

    def _error(message, data):
        return render(
            request,
            "pages/dashboard/user_edit.html",
            {
                "target_user": target_user,
                "potoks": potoks,
                "subjects": subjects,
                "error": message,
                "user_data": data,
            },
            status=400,
        )

    if request.method == "POST":
        data = request.POST

        # ── Роль ────────────────────────────────────────────────────────
        raw_role = (data.get("role") or "").strip()
        if not raw_role.isdigit():
            return _error("Выберите роль", data)
        new_role = int(raw_role)

        # ── Предмет: если поле не пришло вообще — текущее значение не трогаем ──
        new_subject_id = target_user.subject_id
        if "subject" in data:
            raw_subject = (data.get("subject") or "").strip()
            if not raw_subject:
                new_subject_id = None
            elif raw_subject.isdigit() and Subject.objects.filter(id=int(raw_subject)).exists():
                new_subject_id = int(raw_subject)
            else:
                return _error("Выберите корректный предмет", data)

        # Ученик без предмета не виден на странице логина.
        if new_role == Role.STUDENT and new_subject_id is None:
            return _error("Для ученика обязательно выберите предмет", data)

        try:
            target_user.name = data["first_name"]
            target_user.last_name = data["last_name"]
            target_user.second_name = data["second_name"]

            target_user.position = data.get("position") or None
            target_user.company_name = data.get("company_name") or None

            potok_id = (data.get("potok") or "").strip()
            target_user.potok_id = int(potok_id) if potok_id.isdigit() else None

            target_user.subject_id = new_subject_id

            target_user.role = new_role
            target_user.lang = data.get("lang")

            password = data.get("password")
            if password:
                target_user.set_password(password)

            target_user.save()
        except Exception:
            return _error("Проверьте данные", data)

        return redirect("action", status="view", path="user", pk=target_user.id)

    return render(request, "pages/dashboard/user_edit.html", {
        "target_user": target_user,
        "potoks": potoks,
        "subjects": subjects,
    })
