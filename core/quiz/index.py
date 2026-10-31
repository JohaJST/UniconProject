from django.contrib.auth.decorators import login_required
from django.db.models import Avg, Count
from django.shortcuts import redirect, render

from core.models import Result, Test


def _is_missing_field(value) -> bool:
    return not (value and str(value).strip())


def _needs_required_profile_data(user) -> bool:
    if getattr(user, "is_admin", False):
        return False
    return (
        _is_missing_field(user.position)
        or _is_missing_field(user.company_name)
        or _is_missing_field(user.phone)
    )


@login_required(login_url="login")
def index(request, pk=None):
    """
    Единый список всех тестов, доступных потоку текущего пользователя.

    Параметр `pk` (subject id) сохранён для совместимости с URL /subject/<pk>/,
    но в данной версии он не используется — все тесты отображаются
    на одной странице.
    """
    if _needs_required_profile_data(request.user):
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
    if _needs_required_profile_data(request.user):
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


@login_required(login_url="login")
def required(request):
    """Требование дозаполнить должность, организацию и телефон перед допуском к тесту."""
    u = request.user
    if not _needs_required_profile_data(u):
        return redirect("v2_test")

    if request.method == "POST":
        data = request.POST
        new_position = (data.get("position") or "").strip() or u.position
        new_company = (data.get("company_name") or "").strip() or u.company_name
        new_phone = (data.get("phone") or "").strip() or u.phone

        if not (new_position and str(new_position).strip()) \
           or not (new_company and str(new_company).strip()) \
           or not (new_phone and str(new_phone).strip()):
            return render(request, 'pages/reqPB.html', {'error': 'Пожалуйста, заполните все обязательные поля'})

        u.position = str(new_position).strip()
        u.company_name = str(new_company).strip()
        u.phone = str(new_phone).strip()
        u.save()
        return redirect("v2_test")

    return render(request, 'pages/reqPB.html')
