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
from django.db.models import Avg, Count, F, Max, OuterRef, QuerySet, Subquery
from django.shortcuts import get_object_or_404, render

from core.dashboard.pagination.offset_engine import paginate_offset
from core.models.self import SelfResult, SelfUser

_SELFUSER_PAGE_SIZE = 20


def _selfuser_queryset() -> QuerySet:
    """
    Базовый (БЕЗ пагинации) queryset списка участников Self Check с
    агрегированной статистикой.

    Вынесен в отдельную функцию, а не встроен прямо в list_selfuser(),
    чтобы list_selfuser() и registry.py::LIST_REGISTRY["selfuser"]
    использовали РОВНО один и тот же запрос — без риска, что они со
    временем разойдутся (иначе один и тот же список мог бы по-разному
    сортироваться в зависимости от точки входа).

    last_score вычисляется корреляционным подзапросом (Subquery), а не
    через annotate(Max(...)) по foiz — так избегаем неоднозначности
    "максимальный %" vs "% последней по времени попытки" (это разные вещи:
    у пользователя максимальный % мог быть на самой первой попытке).

    Сортировка — по дате/времени последней попытки (новые сверху);
    пользователи без единой попытки (last_attempt=None) уходят в конец.
    Это ВЫЧИСЛЯЕМАЯ сортировка (F(...) поверх annotate Max/Subquery) —
    физической колонки под неё нет и быть не может, поэтому Keyset Engine
    здесь принципиально бесполезен; Offset Engine — постоянное решение
    для этого списка (см. core/dashboard/pagination/offset_engine.py).
    """
    latest_result_qs = (
        SelfResult.objects
        .filter(user=OuterRef("pk"))
        .order_by("-updated", "-id")
    )

    return (
        SelfUser.objects
        .annotate(
            attempts=Count("selfresult", distinct=True),
            avg_score=Avg("selfresult__foiz"),
            last_attempt=Max("selfresult__updated"),
            last_score=Subquery(latest_result_qs.values("foiz")[:1]),
        )
        .order_by(F("last_attempt").desc(nulls_last=True), "-id")
    )


@login_required(login_url="login")
def list_selfuser(request):
    """
    Список участников Self Check с агрегированной статистикой, постранично
    через Offset Engine (см. docstring _selfuser_queryset() — почему именно
    offset, а не keyset).
    """
    page = paginate_offset(_selfuser_queryset(), request, page_size=_SELFUSER_PAGE_SIZE)

    return render(request, "pages/dashboard/selfuser_list.html", {
        "users": page.items,
        "page": page,
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