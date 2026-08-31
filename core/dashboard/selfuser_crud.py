"""
core/dashboard/selfuser_crud.py
────────────────────────────────
CRUD-view для агрегированного списка участников Self Check (SelfUser)
и детальной карточки одного участника с полной историей SelfResult.

list_selfuser — заменяет собой старый "плоский" список SelfResult
                (пункт дашборда "Результаты Self Check"): теперь это
                список SelfUser с агрегатами (средний %, % последней
                попытки, кол-во попыток, дата/время последней попытки).
view_selfuser  — карточка одного участника: агрегаты + таблица всех
                его попыток (SelfResult), от новых к старым.

RBAC и sliding-window таймаут дашборда проверяет DashboardSecurityMiddleware —
свои проверки прав здесь не нужны.
"""
from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.db.models import Avg, Count, F, Max, OuterRef, Subquery
from django.shortcuts import get_object_or_404, render

from core.models.self import SelfResult, SelfUser


@login_required(login_url="login")
def list_selfuser(request):
    """
    Список участников Self Check с агрегированной статистикой.

    last_score вычисляется корреляционным подзапросом (Subquery), а не
    через annotate(Max(...)) по foiz — так избегаем неоднозначности
    "максимальный %" vs "% последней по времени попытки" (это разные вещи:
    у пользователя максимальный % мог быть на самой первой попытке).

    Сортировка — по дате/времени последней попытки (новые сверху);
    пользователи без единой попытки (last_attempt=None) уходят в конец.
    """
    latest_result_qs = (
        SelfResult.objects
        .filter(user=OuterRef("pk"))
        .order_by("-updated", "-id")
    )

    users = (
        SelfUser.objects
        .annotate(
            attempts=Count("selfresult", distinct=True),
            avg_score=Avg("selfresult__foiz"),
            last_attempt=Max("selfresult__updated"),
            last_score=Subquery(latest_result_qs.values("foiz")[:1]),
        )
        .order_by(F("last_attempt").desc(nulls_last=True), "-id")
    )

    return render(request, "pages/dashboard/selfuser_list.html", {
        "users": users,
    })


@login_required(login_url="login")
def view_selfuser(request, pk):
    """
    Карточка участника Self Check: ФИО + агрегаты + полная история
    попыток (SelfResult), отсортированная от новых к старым.
    """
    target_selfuser = get_object_or_404(SelfUser, pk=pk)

    results = (
        SelfResult.objects
        .filter(user=target_selfuser)
        .order_by("-updated", "-id")
    )

    avg_score = results.aggregate(avg=Avg("foiz"))["avg"]
    last_result = results.first()

    ctx = {
        "target_selfuser": target_selfuser,
        "results": results,
        "attempts": results.count(),
        "avg_score": round(avg_score, 1) if avg_score is not None else None,
        "last_score": round(last_result.foiz, 1) if last_result else None,
        "last_attempt": last_result.updated if last_result else None,
    }
    return render(request, "pages/dashboard/selfuser_detail.html", ctx)