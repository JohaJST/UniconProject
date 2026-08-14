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

from core.models import ClassRooms, ClassRoomsSubjects, Subject, Test


@login_required(login_url="login")
def view_subject(request, pk):
    """
    Карточка предмета: название на 3 языках, привязанные классы,
    список тестов предмета (со счётчиком вопросов) и средний % по
    результатам этих тестов.
    """
    subject = get_object_or_404(Subject, pk=pk)

    classrooms = (
        ClassRoomsSubjects.objects
        .filter(subject=subject)
        .select_related('classroom')
    )

    tests = (
        Test.objects
        .filter(subject=subject)
        .annotate(question_count=Count('variantas__questions', distinct=True))
        .order_by('-created')
    )

    avg_score = (
        Test.objects
        .filter(subject=subject)
        .aggregate(avg=Avg('results__foyiz'))['avg']
    )

    ctx = {
        "subject": subject,
        "classrooms": classrooms,
        "tests": tests,
        "avg_score": round(avg_score, 1) if avg_score is not None else None,
    }
    return render(request, "pages/dashboard/subject_detail.html", ctx)


# ─────────────────────────────────────────────────────────────────────────────
# edit_subject
# ─────────────────────────────────────────────────────────────────────────────

def _linked_classroom_ids(subject) -> set:
    """ID классов, уже привязанных к subject через ClassRoomsSubjects."""
    return set(
        ClassRoomsSubjects.objects
        .filter(subject=subject)
        .values_list("classroom_id", flat=True)
    )


@login_required(login_url="login")
def edit_subject(request, pk):
    """
    Редактирование предмета: перевод названия (uz/ru/en, тот же fallback-паттерн,
    что и в create — core/dashboard/action.py::action(status="create", path="subject"))
    + синхронизация привязанных классов (ClassRoomsSubjects).

    Форма рендерит чекбокс на каждый существующий ClassRooms (а не динамически
    добавляемые селекты, как в create) — поэтому классы идентифицируются по
    своему собственному id (name="classroom_<classroom.id>"), а не по
    последовательному индексу: с чекбоксами последовательная схема
    "classroom_{idx} есть в POST, пока не встретится дырка" ломается на первом
    же снятом чекбоксе в середине списка. Собранный набор submitted id —
    по смыслу тот же список "привязать вот эти классы", что и в create.
    """
    subject = get_object_or_404(Subject, pk=pk)

    if request.method == "POST":
        raw_name = (request.POST.get("subject_name") or "").strip()
        name_uz = (request.POST.get("subject_name_uz") or "").strip() or raw_name
        name_ru = (request.POST.get("subject_name_ru") or "").strip()
        name_en = (request.POST.get("subject_name_en") or "").strip()

        # ── Валидация: название обязательно хотя бы на одном языке ─────────
        if not (name_uz or name_ru or name_en):
            return render(request, "pages/dashboard/subject_edit.html", {
                "subject": subject,
                "classrooms": ClassRooms.objects.all(),
                "linked_classroom_ids": _linked_classroom_ids(subject),
                "error": "Название предмета обязательно хотя бы на одном языке",
                "post_data": request.POST,
            })

        subject.name_uz = name_uz
        subject.name_ru = name_ru
        subject.name_en = name_en
        subject.save()

        # ── Синхронизация привязанных классов ───────────────────────────────
        submitted_ids = [
            classroom.id
            for classroom in ClassRooms.objects.all()
            if f"classroom_{classroom.id}" in request.POST
        ]

        ClassRoomsSubjects.objects.filter(subject=subject).exclude(
            classroom_id__in=submitted_ids
        ).delete()

        for classroom_id in submitted_ids:
            ClassRoomsSubjects.objects.get_or_create(
                subject=subject, classroom_id=classroom_id
            )

        return redirect("action", status="view", path="subject", pk=subject.id)

    return render(request, "pages/dashboard/subject_edit.html", {
        "subject": subject,
        "classrooms": ClassRooms.objects.all(),
        "linked_classroom_ids": _linked_classroom_ids(subject),
    })