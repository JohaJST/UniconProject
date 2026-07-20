from contextlib import closing
from turtle import st

from django.contrib.auth.decorators import login_required
from django.db import connection
from django.shortcuts import redirect, render
from methodism import dictfetchone

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


@login_required(login_url="login")
def action(request, status, path, pk=None):
    if request.user.in_dashboard:
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
                    # is_subject = request.GET.get("is_subject")
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
                    subject = Subject.objects.create(
                        name=request.POST.get("subject_name")
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
            else:
                return redirect("dlist", tip=path)
        elif status == "edit":
            pass    
        elif status == "view":
            pass
        else:
            return redirect("dlist", tip=path)
    else:
        return redirect("locked")


@login_required(login_url="login")
def form(req):
    if req.user.in_dashboard:
        c = ClassRooms.objects.all()
        if req.POST:
            data = req.POST
            try:
                User.objects.create_user(
                    phone=data.get("phone"),
                    username=None,
                    password=data.get("password"),
                    birthday=data.get("birthday"),
                    name=data["first_name"],
                    last_name=data["last_name"],
                    classroom_id=int(data["classroom"]),
                    role=int(data["role"]),
                    lang=data.get("lang")
                )
            except:
                return render(
                    req,
                    "pages/dashboard/form.html",
                    {"classrooms": c, "error": "Проверьте данные", "user_data": data},
                )
            return render(
                req,
                "pages/dashboard/form.html",
                {"classrooms": c, "success": "Пользователь добавлен"},
            )
        return render(req, "pages/dashboard/form.html", {"classrooms": c})
    else:
        return redirect("locked")


def userJust():
    # c = f"""
    #         SELECT * FROM core_user a
    #         WHERE a.username = "JustUsername"
    #     """
    # with closing(connection.cursor()) as cursor:
    #     cursor.execute(c)
    #     check = dictfetchone(cursor)
    # if not check:
    #     s = """INSERT INTO core_user (username, password, just, role, is_active, in_dashboard)
    #             VALUES ("JustUsername", "pbkdf2_sha256$600000$v3HUU7hiufzCi58elsVhKG$LvJMwls9/+RLNFyStjZYGGdIZ+9DvnuYT5GYINVse5M=", TRUE, 1, TRUE, 0)"""
    #     with closing(connection.cursor()) as cursor:
    #         cursor.execute(s)
    #         dictfetchone(cursor)
    return 0
