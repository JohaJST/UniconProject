"""
core/dashboard/courses_crud.py
────────────────────────────────
CRUD-view для курсов (Courses) в дашборде.

Реализованы просмотр (view_courses) и редактирование (edit_courses).
Создание — в core/dashboard/action.py (status="create", path="courses"),
удаление — там же (status="delete", path="courses") с физической
чисткой файла фото.

RBAC и sliding-window таймаут дашборда проверяет DashboardSecurityMiddleware —
свои проверки прав здесь не нужны.

Обработка фото — по паттерну core/dashboard/self_check.py:
process_uploaded_image() вызывается ДО transaction.atomic() (декодирование/
ресайз в Pillow не должны держать транзакцию открытой), а старый файл
удаляется физически только ПОСЛЕ успешного commit. Чекбокса "удалить фото"
здесь нет (в отличие от question/answer в self_check.py) — фото Courses
обязательно (см. модель), поэтому оно либо остаётся прежним, либо
заменяется новым.
"""
from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.core.files.storage import default_storage
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render

from core.media_utils import InvalidImageError, process_uploaded_image
from core.models import Courses


@login_required(login_url="login")
def view_courses(request, pk):
    """Карточка курса: заголовок/название/описание на 3 языках + фото."""
    course = get_object_or_404(Courses, pk=pk)
    ctx = {"course": course}
    return render(request, "pages/dashboard/courses_detail.html", ctx)


@login_required(login_url="login")
def edit_courses(request, pk):
    """
    Редактирование курса.

    GET  — форма с текущими данными.
    POST — валидация обязательных полей (title/name/desc) -> обработка
           нового фото (если пришло) ДО транзакции -> одна атомарная
           транзакция сохранения полей + (опционально) фото. Старое фото
           удаляется с диска только после успешного commit и только если
           оно реально было заменено.

    Fallback-паттерн как у subject_crud/selfctg_crud: пустой uz-перевод
    заполняется значением видимого поля формы; ru/en остаются как
    прислала форма (пустыми, если явного перевода не было).
    """
    course = get_object_or_404(Courses, pk=pk)

    if request.method != "POST":
        return render(request, "pages/dashboard/courses_edit.html", {
            "course": course,
        })

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

    if errors:
        return render(request, "pages/dashboard/courses_edit.html", {
            "course": course,
            "error": "; ".join(errors),
            "post_data": post,
        }, status=400)

    # ── Картинка: обработка ДО транзакции (см. self_check.py) ─────────────
    new_photo_file = None
    raw_photo = files.get("courses_photo")
    if raw_photo:
        try:
            new_photo_file = process_uploaded_image(raw_photo)
        except InvalidImageError as exc:
            return render(request, "pages/dashboard/courses_edit.html", {
                "course": course,
                "error": f"Ошибка изображения: {exc}",
                "post_data": post,
            }, status=400)

    title_uz = (post.get("courses_title_uz") or "").strip() or raw_title
    title_ru = (post.get("courses_title_ru") or "").strip()
    title_en = (post.get("courses_title_en") or "").strip()
    name_uz = (post.get("courses_name_uz") or "").strip() or raw_name
    name_ru = (post.get("courses_name_ru") or "").strip()
    name_en = (post.get("courses_name_en") or "").strip()
    desc_uz = (post.get("courses_desc_uz") or "").strip() or raw_desc
    desc_ru = (post.get("courses_desc_ru") or "").strip()
    desc_en = (post.get("courses_desc_en") or "").strip()

    old_photo_name = course.photo.name if course.photo else None
    new_image_name = None

    try:
        with transaction.atomic():
            course.title_uz = title_uz
            course.title_ru = title_ru
            course.title_en = title_en
            course.name_uz = name_uz
            course.name_ru = name_ru
            course.name_en = name_en
            course.desc_uz = desc_uz
            course.desc_ru = desc_ru
            course.desc_en = desc_en

            if new_photo_file:
                course.photo = new_photo_file

            course.save()

            if new_photo_file:
                new_image_name = course.photo.name
    except Exception:
        # Транзакция откатилась — но уже записанный на диск новый файл
        # сам по себе не исчезает, подчищаем вручную.
        if new_photo_file:
            default_storage.delete(new_photo_file.name)

        return render(request, "pages/dashboard/courses_edit.html", {
            "course": course,
            "error": "Не удалось сохранить курс. Попробуйте ещё раз.",
            "post_data": post,
        }, status=400)

    # ── Успех: старое фото удаляем ТОЛЬКО если оно реально было заменено ──
    if new_image_name and old_photo_name and old_photo_name != new_image_name:
        default_storage.delete(old_photo_name)

    return redirect("action", status="view", path="courses", pk=course.id)