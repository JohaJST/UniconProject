"""
core/dashboard/partners_crud.py
────────────────────────────────
CRUD-view для партнёров (Partners) в дашборде.

Реализованы просмотр (view_partners) и редактирование (edit_partners).
Создание — в core/dashboard/action.py (status="create", path="partners"),
удаление — там же (status="delete", path="partners") с физической
чисткой файла фото.

RBAC и sliding-window таймаут дашборда проверяет DashboardSecurityMiddleware —
свои проверки прав здесь не нужны.

В ОТЛИЧИЕ от Courses/Teachers/News, у Partners НЕТ переводимых полей —
name (CharField) и link (URLField) не зарегистрированы в
core/translation.py — поэтому здесь нет ни кнопки AI-перевода, ни
uz/ru/en fallback-логики: форма и обработка полей заметно проще.

Обработка фото — тот же паттерн, что и в courses_crud.py/teachers_crud.py:
process_uploaded_image() вызывается ДО transaction.atomic(), а старый файл
удаляется физически только ПОСЛЕ успешного commit. Чекбокса "удалить фото"
здесь нет — фото Partners обязательно, поэтому оно либо остаётся прежним,
либо заменяется новым.
"""
from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.core.files.storage import default_storage
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render

from core.media_utils import InvalidImageError, process_uploaded_image
from core.models import Partners


@login_required(login_url="login")
def view_partners(request, pk):
    """Карточка партнёра: название, ссылка, фото."""
    partner = get_object_or_404(Partners, pk=pk)
    ctx = {"partner": partner}
    return render(request, "pages/dashboard/partners_detail.html", ctx)


@login_required(login_url="login")
def edit_partners(request, pk):
    """
    Редактирование партнёра.

    GET  — форма с текущими данными.
    POST — валидация обязательных полей (name/link) -> обработка нового
           фото (если пришло) ДО транзакции -> одна атомарная транзакция
           сохранения полей + (опционально) фото. Старое фото удаляется
           с диска только после успешного commit и только если оно
           реально было заменено.

    Никакого fallback-паттерна uz/ru/en здесь нет — у Partners нет
    переводимых полей.
    """
    partner = get_object_or_404(Partners, pk=pk)

    if request.method != "POST":
        return render(request, "pages/dashboard/partners_edit.html", {
            "partner": partner,
        })

    post = request.POST
    files = request.FILES

    raw_name = (post.get("partners_name") or "").strip()
    raw_link = (post.get("partners_link") or "").strip()

    errors = []
    if not raw_name:
        errors.append("Название обязательно")
    if not raw_link:
        errors.append("Ссылка обязательна")

    if errors:
        return render(request, "pages/dashboard/partners_edit.html", {
            "partner": partner,
            "error": "; ".join(errors),
            "post_data": post,
        }, status=400)

    # ── Картинка: обработка ДО транзакции (см. self_check.py) ─────────────
    new_photo_file = None
    raw_photo = files.get("partners_photo")
    if raw_photo:
        try:
            new_photo_file = process_uploaded_image(raw_photo)
        except InvalidImageError as exc:
            return render(request, "pages/dashboard/partners_edit.html", {
                "partner": partner,
                "error": f"Ошибка изображения: {exc}",
                "post_data": post,
            }, status=400)

    old_photo_name = partner.photo.name if partner.photo else None
    new_image_name = None

    try:
        with transaction.atomic():
            partner.name = raw_name
            partner.link = raw_link

            if new_photo_file:
                partner.photo = new_photo_file

            partner.save()

            if new_photo_file:
                new_image_name = partner.photo.name
    except Exception:
        if new_photo_file:
            default_storage.delete(new_photo_file.name)

        return render(request, "pages/dashboard/partners_edit.html", {
            "partner": partner,
            "error": "Не удалось сохранить партнёра. Попробуйте ещё раз.",
            "post_data": post,
        }, status=400)

    if new_image_name and old_photo_name and old_photo_name != new_image_name:
        default_storage.delete(old_photo_name)

    return redirect("action", status="view", path="partners", pk=partner.id)