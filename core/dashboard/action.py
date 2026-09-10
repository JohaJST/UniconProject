from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.files.storage import default_storage
from django.db import transaction
from django.db.models.fields import DateField
from django.shortcuts import redirect, render

from core.dashboard.subject_crud import view_subject, edit_subject
from core.dashboard.potok_crud import view_potok, edit_potok
from core.dashboard.user_crud import view_user, edit_user
from core.dashboard.quiz_crud import view_quiz, edit_quiz
from core.dashboard.selfctg_crud import view_selfctg, edit_selfctg
# ХОТФИКС (появятся на шагах 3-4): модули ещё не существуют — до их
# создания весь дашборд не запустится (ImportError при старте приложения).
# Импорты заведены заранее по явному требованию текущего этапа.
from core.dashboard.courses_crud import view_courses, edit_courses
from core.dashboard.teachers_crud import view_teachers, edit_teachers
from core.dashboard.news_crud import view_news, edit_news
from core.dashboard.partners_crud import view_partners, edit_partners

from core.media_utils import InvalidImageError, process_uploaded_image
from core.models import (
    Potok,
    Question,
    Result,
    Subject,
    Test,
    User,
    Variant,
)
from core.models.about import Courses, News, Partners, Teachers
from core.dashboard.selfuser_crud import view_selfuser
from core.models.self import SelfCtg, SelfQuestion, SelfResult, SelfUser


def _require_photo(files, field_name):
    """
    Валидирует и обрабатывает ОБЯЗАТЕЛЬНОЕ фото для форм создания
    Courses/Teachers/News/Partners.

    Вызывать ДО transaction.atomic() — как и process_uploaded_image()
    в core/quiz/create.py и core/dashboard/self_check.py: декодирование/
    ресайз в Pillow не должны держать транзакцию открытой.

    :return: (ContentFile, None) при успехе, (None, error_message) если
        файла нет вовсе или он не прошёл валидацию media_utils.
    """
    raw_photo = files.get(field_name)
    if not raw_photo:
        return None, "Фото обязательно"
    try:
        return process_uploaded_image(raw_photo), None
    except InvalidImageError as exc:
        return None, f"Ошибка изображения: {exc}"
        

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
        elif path == "courses":
            if request.method == "GET":
                return render(request, "pages/dashboard/courses_new.html")
            elif request.method == "POST":
                post = request.POST
                files = request.FILES

                raw_title = (post.get("courses_title") or "").strip()
                raw_name = (post.get("courses_name") or "").strip()
                raw_desc = (post.get("courses_desc") or "").strip()

                errors = []
                if not raw_title:
                    errors.append("Заголовок обязателен")
                if not raw_name:
                    errors.append("Название обязательно")
                if not raw_desc:
                    errors.append("Описание обязательно")

                photo_file, photo_error = _require_photo(files, "courses_photo")
                if photo_error:
                    errors.append(photo_error)

                if errors:
                    return render(request, "pages/dashboard/courses_new.html", {
                        "error": "; ".join(errors),
                        "post_data": post,
                    }, status=400)

                title_uz = (post.get("courses_title_uz") or "").strip() or raw_title
                title_ru = (post.get("courses_title_ru") or "").strip() or raw_title
                title_en = (post.get("courses_title_en") or "").strip() or raw_title
                name_uz = (post.get("courses_name_uz") or "").strip() or raw_name
                name_ru = (post.get("courses_name_ru") or "").strip() or raw_name
                name_en = (post.get("courses_name_en") or "").strip() or raw_name
                desc_uz = (post.get("courses_desc_uz") or "").strip() or raw_desc
                desc_ru = (post.get("courses_desc_ru") or "").strip() or raw_desc
                desc_en = (post.get("courses_desc_en") or "").strip() or raw_desc

                try:
                    with transaction.atomic():
                        Courses.objects.create(
                            title_uz=title_uz, title_ru=title_ru, title_en=title_en,
                            name_uz=name_uz, name_ru=name_ru, name_en=name_en,
                            desc_uz=desc_uz, desc_ru=desc_ru, desc_en=desc_en,
                            photo=photo_file,
                        )
                except Exception:
                    default_storage.delete(photo_file.name)
                    return render(request, "pages/dashboard/courses_new.html", {
                        "error": "Не удалось создать курс. Попробуйте ещё раз.",
                        "post_data": post,
                    }, status=400)

                return redirect("dlist", tip=path)
        elif path == "teachers":
            if request.method == "GET":
                return render(request, "pages/dashboard/teachers_new.html")
            elif request.method == "POST":
                post = request.POST
                files = request.FILES

                raw_fio = (post.get("teacher_fio") or "").strip()
                raw_phone = (post.get("teacher_phone") or "").strip()
                raw_position = (post.get("teacher_position") or "").strip()

                errors = []
                if not raw_fio:
                    errors.append("ФИО обязательно")
                if not raw_phone:
                    errors.append("Телефон обязателен")
                if not raw_position:
                    errors.append("Должность обязательна")

                photo_file, photo_error = _require_photo(files, "teacher_photo")
                if photo_error:
                    errors.append(photo_error)

                if errors:
                    return render(request, "pages/dashboard/teachers_new.html", {
                        "error": "; ".join(errors),
                        "post_data": post,
                    }, status=400)

                position_uz = (post.get("teacher_position_uz") or "").strip() or raw_position
                position_ru = (post.get("teacher_position_ru") or "").strip() or raw_position
                position_en = (post.get("teacher_position_en") or "").strip() or raw_position

                try:
                    with transaction.atomic():
                        Teachers.objects.create(
                            fio=raw_fio,
                            phone=raw_phone,
                            position_uz=position_uz,
                            position_ru=position_ru,
                            position_en=position_en,
                            photo=photo_file,
                        )
                except Exception:
                    default_storage.delete(photo_file.name)
                    return render(request, "pages/dashboard/teachers_new.html", {
                        "error": "Не удалось добавить преподавателя. Попробуйте ещё раз.",
                        "post_data": post,
                    }, status=400)

                return redirect("dlist", tip=path)
        elif path == "news":
            if request.method == "GET":
                return render(request, "pages/dashboard/news_new.html")
            elif request.method == "POST":
                post = request.POST
                files = request.FILES

                raw_title = (post.get("news_title") or "").strip()
                raw_desc = (post.get("news_desc") or "").strip()
                raw_date = (post.get("news_date") or "").strip()

                errors = []
                if not raw_title:
                    errors.append("Заголовок обязателен")
                if not raw_desc:
                    errors.append("Описание обязательно")

                news_date = None
                if not raw_date:
                    errors.append("Дата обязательна")
                else:
                    try:
                        news_date = DateField().to_python(raw_date)
                        if not news_date:
                            raise ValueError("empty date")
                    except (ValidationError, ValueError):
                        errors.append("Неверный формат даты. Используйте формат: 2026-05-22")

                photo_file, photo_error = _require_photo(files, "news_photo")
                if photo_error:
                    errors.append(photo_error)

                if errors:
                    return render(request, "pages/dashboard/news_new.html", {
                        "error": "; ".join(errors),
                        "post_data": post,
                    }, status=400)

                title_uz = (post.get("news_title_uz") or "").strip() or raw_title
                title_ru = (post.get("news_title_ru") or "").strip() or raw_title
                title_en = (post.get("news_title_en") or "").strip() or raw_title
                desc_uz = (post.get("news_desc_uz") or "").strip() or raw_desc
                desc_ru = (post.get("news_desc_ru") or "").strip() or raw_desc
                desc_en = (post.get("news_desc_en") or "").strip() or raw_desc

                try:
                    with transaction.atomic():
                        News.objects.create(
                            title_uz=title_uz, title_ru=title_ru, title_en=title_en,
                            desc_uz=desc_uz, desc_ru=desc_ru, desc_en=desc_en,
                            date=news_date,
                            photo=photo_file,
                        )
                except Exception:
                    default_storage.delete(photo_file.name)
                    return render(request, "pages/dashboard/news_new.html", {
                        "error": "Не удалось добавить новость. Попробуйте ещё раз.",
                        "post_data": post,
                    }, status=400)

                return redirect("dlist", tip=path)
        elif path == "partners":
            if request.method == "GET":
                return render(request, "pages/dashboard/partners_new.html")
            elif request.method == "POST":
                post = request.POST
                files = request.FILES

                raw_name = (post.get("partners_name") or "").strip()
                raw_link = (post.get("partners_link") or "").strip()

                errors = []
                if not raw_name:
                    errors.append("Название обязательно")
                if not raw_link:
                    errors.append("Ссылка обязательна")

                photo_file, photo_error = _require_photo(files, "partners_photo")
                if photo_error:
                    errors.append(photo_error)

                if errors:
                    return render(request, "pages/dashboard/partners_new.html", {
                        "error": "; ".join(errors),
                        "post_data": post,
                    }, status=400)

                try:
                    with transaction.atomic():
                        Partners.objects.create(
                            name=raw_name,
                            link=raw_link,
                            photo=photo_file,
                        )
                except Exception:
                    default_storage.delete(photo_file.name)
                    return render(request, "pages/dashboard/partners_new.html", {
                        "error": "Не удалось добавить партнёра. Попробуйте ещё раз.",
                        "post_data": post,
                    }, status=400)

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
            # После удаления одной попытки возвращаем не на плоский список
            # (его больше нет), а обратно на карточку участника, которому
            # принадлежала эта попытка.
            result = SelfResult.objects.select_related("user").get(id=pk)
            redirect_user_id = result.user_id
            result.delete()
            if redirect_user_id:
                return redirect("action", status="view", path="selfuser", pk=redirect_user_id)
            return redirect("dlist", tip="selfresult")
        elif path == "selfctg":
            # Вопросы категории не удаляются: FK SET_NULL — они остаются
            # без категории, а не пропадают вместе с ней.
            SelfCtg.objects.get(id=pk).delete()
            return redirect("dlist", tip=path)
        elif path == "selfuser":
                    target = SelfUser.objects.get(id=pk)
                    SelfResult.objects.filter(user=target).delete()
                    target.delete()
                    return redirect("dlist", tip="selfresult")
        elif path == "courses":
            obj = Courses.objects.get(id=pk)
            photo_name = obj.photo.name if obj.photo else None
            obj.delete()
            if photo_name:
                default_storage.delete(photo_name)
            return redirect("dlist", tip=path)
        elif path == "teachers":
            obj = Teachers.objects.get(id=pk)
            photo_name = obj.photo.name if obj.photo else None
            obj.delete()
            if photo_name:
                default_storage.delete(photo_name)
            return redirect("dlist", tip=path)
        elif path == "news":
            obj = News.objects.get(id=pk)
            photo_name = obj.photo.name if obj.photo else None
            obj.delete()
            if photo_name:
                default_storage.delete(photo_name)
            return redirect("dlist", tip=path)
        elif path == "partners":
            obj = Partners.objects.get(id=pk)
            photo_name = obj.photo.name if obj.photo else None
            obj.delete()
            if photo_name:
                default_storage.delete(photo_name)
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
        elif path == "courses":
            return edit_courses(request, pk)
        elif path == "teachers":
            return edit_teachers(request, pk)
        elif path == "news":
            return edit_news(request, pk)
        elif path == "partners":
            return edit_partners(request, pk)
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
        elif path == "selfuser":
            return view_selfuser(request, pk)
        elif path == "courses":
            return view_courses(request, pk)
        elif path == "teachers":
            return view_teachers(request, pk)
        elif path == "news":
            return view_news(request, pk)
        elif path == "partners":
            return view_partners(request, pk)
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
