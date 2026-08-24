from django.contrib.auth.decorators import login_required
from django.db.models import Avg, Count
from django.shortcuts import redirect, render

from core.models import Result, Test


@login_required(login_url="login")
def index(request, pk=None):
    """
    Единый список всех тестов, доступных потоку текущего пользователя.

    Параметр `pk` (subject id) сохранён для совместимости с URL /subject/<pk>/,
    но в данной версии он не используется — все тесты отображаются
    на одной странице.
    """
    if not request.user.position or not request.user.company_name:
        return redirect("required")

    # Тесты для потока пользователя + subject через JOIN (select_related).
    tests = (
        Test.objects
        .filter(potok=request.user.potok)
        .select_related('subject', 'potok')
        .annotate(question_count=Count('questions', distinct=True))
        .distinct()
        .order_by('-created')
    )

    completed_test_ids = set(
        Result.objects
        .filter(user=request.user)
        .values_list('test_id', flat=True)
    )

    return render(request, 'index.html', {'tests': tests, 'completed_test_ids': completed_test_ids})


@login_required(login_url="login")
def user_profile(request):
    if not request.user.position or not request.user.company_name:
        return redirect("required")

    """Профиль пользователя с историей результатов и средним баллом."""
    results = (
        Result.objects
        .filter(user=request.user)
        .select_related('test')
        .order_by('-created')
    )
    average = results.aggregate(avg=Avg('foyiz'))['avg']

    ctx = {
        "user": request.user,
        "results": results,
        "average": round(average, 1) if average is not None else None,
    }
    return render(request, "profile.html", ctx)


def required(request):
    """Требование заполнить должность и компанию при первом входе."""
    if request.method == "POST":
        try:
            u = request.user
            u.position = request.POST['position']
            u.company_name = request.POST['company_name']
            u.save()
            return redirect("home")
        except Exception:
            return render(request, 'pages/reqPB.html', {'error': 'Проверьте данные пожалуйста'})
    return render(request, 'pages/reqPB.html')
