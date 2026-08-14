from django.contrib.auth.decorators import login_required
from django.core.files.storage import default_storage
from django.shortcuts import redirect, render
import datetime
from core.dashboard.subject_crud import view_subject, edit_subject

from core.models import (
    ClassRooms,
    ClassRoomsSubjects,
    Question,
    Result,
    Subject,
    Test,
    User,
    Variant,
)
from core.models.self import SelfQuestion, SelfResult


@login_required(login_url="login")
def action(request, status, path, pk=None):
    # RBAC и sliding-window таймаут дашборда теперь проверяет
    # DashboardSecurityMiddleware — внешний if/else с "locked" удалён,
    # весь код ниже разрезиндентирован на один уровень.
    if status == "start":
        try:
            t = Test.objects.filter(pk=pk).first()
            t.is_start = True
            t.save()
            return redirect("dlist", tip=path)
        except:
            return redirect("dlist", tip=path)
    elif status == "end":
        try:
            t = Test.objects.filter(pk=pk).first()
            t.is_start = False
            t.save()
            return redirect("dlist", tip=path)
        except:
            return redirect("dlist", tip=path)
    elif status == "create":
        if path == "test":
            if request.method == "GET":
                classrooms = ClassRooms.objects.all()
                subjects = Subject.objects.all()
                return render(
                    request,
                    "pages/dashboard/new.html",
                    {
                        "classrooms": classrooms,
                        "subjects": subjects,
                        "action": "test",
                    },
                )
            elif request.method == "POST":
                return redirect("dashboard")
        elif path == "subject":
            if request.method == "GET":
                classrooms = ClassRooms.objects.all()
                return render(
                    request,
                    "pages/dashboard/new.html",
                    {"action": "subject", "classrooms": classrooms},
                )
            elif request.method == "POST":
                raw_name = request.POST.get("subject_name", "")
                subject = Subject.objects.create(
                    name_uz=request.POST.get("subject_name_uz") or raw_name,
                    name_ru=request.POST.get("subject_name_ru") or raw_name,
                    name_en=request.POST.get("subject_name_en") or raw_name,
                )
                subject.save()
                classroom_id = 0
                while f"classroom_{classroom_id}" in request.POST:
                    clsb = ClassRoomsSubjects.objects.get_or_create(
                        classroom_id=ClassRooms.objects.get(
                            id=request.POST.get(f"classroom_{classroom_id}")
                        ).id,
                        subject_id=subject.id,
                    )
                    try:
                        clsb.save()
                    except:
                        pass
                    classroom_id += 1
                return redirect("dlist", tip=path)
        elif path == "classroom":
            if request.method == "GET":
                return render(
                    request, "pages/dashboard/new.html", {"action": "classroom"}
                )
            elif request.method == "POST":
                class_room = ClassRooms.objects.create(
                    name=request.POST.get("classroom_name")
                )
                class_room.save()
                return redirect("dlist", tip=path)
        return redirect("dlist", tip=path)
    elif status == "delete":
        if path == "subject":
            subject = Subject.objects.get(id=pk)
            subject.delete()
            return redirect("dlist", tip=path)
        elif path == "classroom":
            classroom = ClassRooms.objects.get(id=pk)
            classroom.delete()
            return redirect("dlist", tip=path)
        elif path == "quiz":
            test = Test.objects.get(id=pk)
            test.delete()
            return redirect("dlist", tip=path)
        elif path == "question":
            question = Question.objects.get(id=pk)
            question.delete()
            return redirect("dlist", tip=path)
        elif path == "variant":
            variant = Variant.objects.get(id=pk)
            variant.delete()
            return redirect("dlist", tip=path)
        elif path == "result":
            result = Result.objects.get(id=pk)
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
        else:
            return redirect("dlist", tip=path)
    elif status == "edit":
        if path == "subject":
            return edit_subject(request, pk)
    elif status == "view":
        if path == "subject":
            return view_subject(request, pk)
        pass
    else:
        return redirect("dlist", tip=path)


@login_required(login_url="login")
def form(req):
    # Проверка доступа к дашборду — в DashboardSecurityMiddleware.
    c = ClassRooms.objects.all()
    if req.POST:
        data = req.POST
        # try:
        User.objects.create_user(
            phone=data.get("phone") or 1234,
            username=None,
            password=data.get("password") or "1234",
            birthday = data.get("birthday") or datetime.datetime.today().strftime('%Y-%m-%d'),
            name=data["first_name"],
            last_name=data["last_name"],
            classroom_id=int(data["classroom"]),
            role=int(data["role"]),
            lang=data.get("lang")
        )
        # except:
        #     return render(
        #         req,
        #         "pages/dashboard/form.html",
        #         {"classrooms": c, "error": "Проверьте данные", "user_data": data},
        #     )
        return render(
            req,
            "pages/dashboard/form.html",
            {"classrooms": c, "success": "Пользователь добавлен"},
        )
    return render(req, "pages/dashboard/form.html", {"classrooms": c})
