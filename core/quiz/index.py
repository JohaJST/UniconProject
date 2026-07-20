from django.contrib.auth.decorators import login_required
from django.db.models import Avg, Count
from django.shortcuts import redirect, render

from core.models import Result, Test


@login_required(login_url="login")
def index(request, pk=None):
    """
    Единый список всех тестов, доступных классу текущего пользователя.

    Параметр `pk` (subject id) сохранён для совместимости с URL /subject/<pk>/,
    но в данной версии он не используется — все активные тесты отображаются
    на одной странице.
    """
    if request.user.birthday is None or request.user.phone is None:
        return redirect("required")

    # Один запрос: тесты для класса + subject через JOIN (select_related).
    # .distinct() необходим, т.к. через test_classrooms возможны дубли.
    tests = (
        Test.objects
        .filter(
            test_classrooms__classroom=request.user.classroom,
        )
        .select_related('subject')
        .annotate(question_count=Count('variantas__questions', distinct=True))
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
    if request.user.birthday is None or request.user.phone is None:
        return redirect("required")

    """Профиль пользователя с историей результатов и средним баллом."""
    # Фильтруем на уровне БД вместо перебора всех записей в Python.
    results = (
        Result.objects
        .filter(user=request.user)
        .select_related('test')
        .order_by('-created')
    )
    # Avg корректно игнорирует NULL-значения.
    average = results.aggregate(avg=Avg('foyiz'))['avg']

    ctx = {
        "user": request.user,
        "results": results,
        "average": round(average, 1) if average is not None else None,
    }
    return render(request, "profile.html", ctx)


def required(request):
    """Требование заполнить дату рождения и телефон при первом входе."""
    if request.method == "POST":
        try:
            u = request.user
            u.birthday = request.POST['birthday']
            u.phone = request.POST['phone']
            u.save()
            return redirect("home")
        except Exception:
            return render(request, 'pages/reqPB.html', {'error': 'Проверьте данные пожалуйста'})
    return render(request, 'pages/reqPB.html')
