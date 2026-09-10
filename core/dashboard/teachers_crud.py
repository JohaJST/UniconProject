"""
core/dashboard/teachers_crud.py
────────────────────────────────
CRUD-view для преподавателей (Teachers) в дашборде.

Реализованы просмотр (view_teachers) и редактирование (edit_teachers).
Создание — в core/dashboard/action.py (status="create", path="teachers"),
удаление — там же (status="delete", path="teachers") с физической
чисткой файла фото.

RBAC и sliding-window таймаут дашборда проверяет DashboardSecurityMiddleware —
свои проверки прав здесь не нужны.

Обработка фото — по паттерну core/dashboard/self_check.py:
process_uploaded_image() вызывается ДО transaction.atomic(), а старый файл
удаляется физически только ПОСЛЕ успешного commit. Чекбокса "удалить фото"
здесь нет — фото Teachers обязательно, поэтому оно либо остаётся прежним,
либо заменяется новым.

fio и phone НЕ переводятся (одноязычные поля модели) — переводится только
position (position_uz/ru/en через django-modeltranslation).
"""
from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.core.files.storage import default_storage
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render

from core.media_utils import InvalidImageError, process_uploaded_image
from core.models import Teachers


@login_required(login_url="login")
def view_teachers(request, pk):
    """Карточка преподавателя: ФИО, должность на 3 языках, телефон, фото."""
    teacher = get_object_or_404(Teachers, pk=pk)
    ctx = {"teacher": teacher}
    return render(request, "pages/dashboard/teachers_detail.html", ctx)


@login_required(login_url="login")
def edit_teachers(request, pk):
    """
    Редактирование преподавателя.

    GET  — форма с текущими данными.
    POST — валидация обязательных полей (fio/phone/position) -> обработка
           нового фото (если пришло) ДО транзакции -> одна атомарная
           транзакция сохранения полей + (опционально) фото. Старое фото
           удаляется с диска только после успешного commit и только если
           оно реально было заменено.

    Fallback-паттерн как у subject_crud/selfctg_crud: пустой uz-перевод
    должности заполняется значением видимого поля формы; ru/en остаются
    как прислала форма.
    """
    teacher = get_object_or_404(Teachers, pk=pk)

    if request.method != "POST":
        return render(request, "pages/dashboard/teachers_edit.html", {
            "teacher": teacher,
        })

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

    if errors:
        return render(request, "pages/dashboard/teachers_edit.html", {
            "teacher": teacher,
            "error": "; ".join(errors),
            "post_data": post,
        }, status=400)

    # ── Картинка: обработка ДО транзакции (см. self_check.py) ─────────────
    new_photo_file = None
    raw_photo = files.get("teacher_photo")
    if raw_photo:
        try:
            new_photo_file = process_uploaded_image(raw_photo)
        except InvalidImageError as exc:
            return render(request, "pages/dashboard/teachers_edit.html", {
                "teacher": teacher,
                "error": f"Ошибка изображения: {exc}",
                "post_data": post,
            }, status=400)

    position_uz = (post.get("teacher_position_uz") or "").strip() or raw_position
    position_ru = (post.get("teacher_position_ru") or "").strip()
    position_en = (post.get("teacher_position_en") or "").strip()

    old_photo_name = teacher.photo.name if teacher.photo else None
    new_image_name = None

    try:
        with transaction.atomic():
            teacher.fio = raw_fio
            teacher.phone = raw_phone
            teacher.position_uz = position_uz
            teacher.position_ru = position_ru
            teacher.position_en = position_en

            if new_photo_file:
                teacher.photo = new_photo_file

            teacher.save()

            if new_photo_file:
                new_image_name = teacher.photo.name
    except Exception:
        if new_photo_file:
            default_storage.delete(new_photo_file.name)

        return render(request, "pages/dashboard/teachers_edit.html", {
            "teacher": teacher,
            "error": "Не удалось сохранить преподавателя. Попробуйте ещё раз.",
            "post_data": post,
        }, status=400)

    if new_image_name and old_photo_name and old_photo_name != new_image_name:
        default_storage.delete(old_photo_name)

    return redirect("action", status="view", path="teachers", pk=teacher.id)