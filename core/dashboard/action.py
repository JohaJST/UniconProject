from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.files.storage import default_storage
from django.db.models.fields import DateField
from django.shortcuts import redirect, render

from core.dashboard.subject_crud import view_subject, edit_subject
from core.dashboard.potok_crud import view_potok, edit_potok
from core.dashboard.user_crud import view_user, edit_user
from core.dashboard.quiz_crud import view_quiz, edit_quiz
from core.dashboard.selfctg_crud import view_selfctg, edit_selfctg

from core.models import (
    Potok,
    Question,
    Result,
    Subject,
    Test,
    User,
    Variant,
)
from core.models.self import SelfCtg, SelfQuestion, SelfResult


@login_required(login_url="login")
def action(request, status, path, pk=None):
    # RBAC и sliding-window таймаут дашборда теперь проверяет
    # DashboardSecurityMiddleware — внешний if/else с "locked" удалён,
    # весь код ниже разрезиндентирован на один уровень.
    if status == "create":
        if path == "test":
            if request.method == "GET":
                potoks = Potok.objects.all()
                subjects = Subject.objects.all()
                return render(
                    request,
                    "pages/dashboard/new.html",
                    {
                        "potoks": potoks,
                        "subjects": subjects,
                        "action": "test",
                    },
                )
            elif request.method == "POST":
                return redirect("dashboard")
        elif path == "subject":
            if request.method == "GET":
                return render(
                    request, "pages/dashboard/new.html", {"action": "subject"}
                )
            elif request.method == "POST":
                raw_name = request.POST.get("subject_name", "")
                subject = Subject.objects.create(
                    name_uz=request.POST.get("subject_name_uz") or raw_name,
                    name_ru=request.POST.get("subject_name_ru") or raw_name,
                    name_en=request.POST.get("subject_name_en") or raw_name,
                )
                subject.save()
                return redirect("dlist", tip=path)
        elif path == "selfctg":
            if request.method == "GET":
                return render(
                    request, "pages/dashboard/new.html", {"action": "selfctg"}
                )
            elif request.method == "POST":
                raw_name = request.POST.get("selfctg_name", "")
                ctg = SelfCtg.objects.create(
                    name_uz=request.POST.get("selfctg_name_uz") or raw_name,
                    name_ru=request.POST.get("selfctg_name_ru") or raw_name,
                    name_en=request.POST.get("selfctg_name_en") or raw_name,
                )
                ctg.save()
                return redirect("dlist", tip=path)
        elif path == "potok":
            if request.method == "GET":
                return render(
                    request, "pages/dashboard/new.html", {"action": "potok"}
                )
            elif request.method == "POST":
                # Валидация ДО создания: start/end — DateField (только дата),
                # мусорная строка не должна ронять 500 (ValidationError).
                try:
                    start = DateField().to_python(request.POST.get("potok_start"))
                    end = DateField().to_python(request.POST.get("potok_end"))
                    if not start or not end:
                        raise ValueError("empty date")
                    if end <= start:
                        return render(
                            request, "pages/dashboard/new.html",
                            {"action": "potok",
                             "error": "Дата конца потока должна быть позже даты начала"},
                        )
                except (ValidationError, ValueError):
                    return render(
                        request, "pages/dashboard/new.html",
                        {"action": "potok",
                         "error": "Неверный формат дат. Используйте формат: 2026-05-22"},
                    )

                Potok.objects.create(start=start, end=end)
                return redirect("dlist", tip=path)
        return redirect("dlist", tip=path)
    elif status == "delete":
        if path == "subject":
            Subject.objects.get(id=pk).delete()
            return redirect("dlist", tip=path)
        elif path == "potok":
            Potok.objects.get(id=pk).delete()
            return redirect("dlist", tip=path)
        elif path == "quiz":
            Test.objects.get(id=pk).delete()
            return redirect("dlist", tip=path)
        elif path == "question":
            Question.objects.get(id=pk).delete()
            return redirect("dlist", tip=path)
        elif path == "variant":
            Variant.objects.get(id=pk).delete()
            return redirect("dlist", tip=path)
        elif path == "result":
            result = Result.objects.get(id=pk)
            User.objects.filter(id=result.user.id).update(is_result=False)
            result.delete()
            return redirect("dlist", tip=path)
        elif path == "user":
            User.objects.filter(id=pk).delete()
            return redirect("dlist", tip=path)
        elif path == "selfquestion":
            q = SelfQuestion.objects.prefetch_related("selfanswer_set").get(id=pk)

            # Собираем пути ко всем файлам ДО удаления записей из БД —
            # после q.delete() доступ к q.img / answer.img через ORM уже
            # недоступен (объекты каскадно удалены).
            image_names = []
            if q.img:
                image_names.append(q.img.name)
            for answer in q.selfanswer_set.all():
                if answer.img:
                    image_names.append(answer.img.name)

            q.delete()

            # Физически удаляем файлы с диска — Django не делает этого
            # автоматически при удалении модели.
            for name in image_names:
                default_storage.delete(name)

            return redirect("dlist", tip=path)
        elif path == "selfresult":
            SelfResult.objects.get(id=pk).delete()
            return redirect("dlist", tip=path)
        elif path == "selfctg":
            # Вопросы категории не удаляются: FK SET_NULL — они остаются
            # без категории, а не пропадают вместе с ней.
            SelfCtg.objects.get(id=pk).delete()
            return redirect("dlist", tip=path)
        else:
            return redirect("dlist", tip=path)
    elif status == "edit":
        if path == "subject":
            return edit_subject(request, pk)
        elif path == "potok":
            return edit_potok(request, pk)
        elif path == "user":
            return edit_user(request, pk)
        elif path == "quiz":
            return edit_quiz(request, pk)
        elif path == "selfctg":
            return edit_selfctg(request, pk)
        return redirect("dlist", tip=path)

    elif status == "view":
        if path == "subject":
            return view_subject(request, pk)
        elif path == "potok":
            return view_potok(request, pk)
        elif path == "user":
            return view_user(request, pk)
        elif path == "quiz":
            return view_quiz(request, pk)
        elif path == "selfctg":
            return view_selfctg(request, pk)
        return redirect("dlist", tip=path)
    else:
        return redirect("dlist", tip=path)


@login_required(login_url="login")
def form(req):
    # Проверка доступа к дашборду — в DashboardSecurityMiddleware.
    potoks = Potok.objects.all()
    if req.POST:
        data = req.POST
        try:
            User.objects.create_user(
                username=None,
                password=data.get("password") or "1234",
                name=data["first_name"],
                last_name=data["last_name"],
                potok_id=int(data["potok"]) if data.get("potok") else None,
                position=data.get("position"),
                company_name=data.get("company_name"),
                role=int(data["role"]),
                lang=data.get("lang")
            )
        except Exception:
            return render(
                req,
                "pages/dashboard/form.html",
                {"potoks": potoks, "error": "Проверьте данные", "user_data": data},
            )
        return render(
            req,
            "pages/dashboard/form.html",
            {"potoks": potoks, "success": "Пользователь добавлен"},
        )
    return render(req, "pages/dashboard/form.html", {"potoks": potoks})
