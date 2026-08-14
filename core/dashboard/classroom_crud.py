"""
core/dashboard/classroom_crud.py
────────────────────────────────
CRUD-view для класса (ClassRooms) в дашборде.

Реализован только просмотр (view_classroom) — по аналогии с
core/dashboard/subject_crud.py::view_subject. RBAC и sliding-window
таймаут дашборда проверяет DashboardSecurityMiddleware — свои проверки
прав здесь не нужны.
"""
from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.db.models import Avg, Count
from django.shortcuts import get_object_or_404, render

from core.models import ClassRooms, Subject, Test, User
from core.models.auth import Role


@login_required(login_url="login")
def view_classroom(request, pk):
    """
    Карточка класса: список учеников (со счётчиком попыток и средним
    баллом), привязанные предметы и тесты класса.
    """
    classroom = get_object_or_404(ClassRooms, pk=pk)

    students = (
        User.objects
        .filter(classroom=classroom, role=Role.STUDENT)
        .select_related('classroom')
        .annotate(
            attempt_count=Count('results', distinct=True),
            avg_score=Avg('results__foyiz'),
        )
        .order_by('last_name', 'name')
    )

    subjects = (
        Subject.objects
        .filter(classroomssubjects__classroom=classroom)
        .distinct()
    )

    tests = (
        Test.objects
        .filter(test_classrooms__classroom=classroom)
        .select_related('subject')
        .distinct()
        .order_by('-created')
    )

    ctx = {
        "classroom": classroom,
        "students": students,
        "subjects": subjects,
        "tests": tests,
    }
    return render(request, "pages/dashboard/classroom_detail.html", ctx)