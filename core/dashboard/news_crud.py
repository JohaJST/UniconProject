"""
core/dashboard/news_crud.py
────────────────────────────────
CRUD-view для новостей (News) в дашборде.

Реализованы просмотр (view_news) и редактирование (edit_news).
Создание — в core/dashboard/action.py (status="create", path="news"),
удаление — там же (status="delete", path="news") с физической
чисткой файла фото.

RBAC и sliding-window таймаут дашборда проверяет DashboardSecurityMiddleware —
свои проверки прав здесь не нужны.

Обработка фото — по паттерну core/dashboard/self_check.py:
process_uploaded_image() вызывается ДО transaction.atomic() (декодирование/
ресайз в Pillow не должны держать транзакцию открытой), а старый файл
удаляется физически только ПОСЛЕ успешного commit. Чекбокса "удалить фото"
здесь нет (как и у Courses/Teachers) — фото News обязательно, поэтому оно
либо остаётся прежним, либо заменяется новым.

Поле date — обычный DateField, НЕ переводится (в отличие от title/desc,
зарегистрированных в core/translation.py через django-modeltranslation).
Валидация даты — тот же паттерн, что в core/dashboard/potok_crud.py::edit_potok
и core/dashboard/action.py (создание News): мусорная строка не должна
ронять 500 (ValidationError/ValueError ловятся явно).
"""
from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.files.storage import default_storage
from django.db import transaction
from django.db.models.fields import DateField
from django.shortcuts import get_object_or_404, redirect, render

from core.media_utils import InvalidImageError, process_uploaded_image
from core.models import News


@login_required(login_url="login")
def view_news(request, pk):
    """Карточка новости: заголовок/описание на 3 языках, дата, фото."""
    news = get_object_or_404(News, pk=pk)
    ctx = {"news": news}
    return render(request, "pages/dashboard/news_detail.html", ctx)


@login_required(login_url="login")
def edit_news(request, pk):
    """
    Редактирование новости.

    GET  — форма с текущими данными.
    POST — валидация обязательных полей (title/desc/date) -> обработка
           нового фото (если пришло) ДО транзакции -> одна атомарная
           транзакция сохранения полей + (опционально) фото. Старое фото
           удаляется с диска только после успешного commit и только если
           оно реально было заменено.

    Fallback-паттерн как у subject_crud/courses_crud: пустой uz-перевод
    заполняется значением видимого поля формы; ru/en остаются как
    прислала форма (пустыми, если явного перевода не было).
    """
    news = get_object_or_404(News, pk=pk)

    if request.method != "POST":
        return render(request, "pages/dashboard/news_edit.html", {
            "news": news,
        })

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

    if errors:
        return render(request, "pages/dashboard/news_edit.html", {
            "news": news,
            "error": "; ".join(errors),
            "post_data": post,
        }, status=400)

    # ── Картинка: обработка ДО транзакции (см. self_check.py) ─────────────
    new_photo_file = None
    raw_photo = files.get("news_photo")
    if raw_photo:
        try:
            new_photo_file = process_uploaded_image(raw_photo)
        except InvalidImageError as exc:
            return render(request, "pages/dashboard/news_edit.html", {
                "news": news,
                "error": f"Ошибка изображения: {exc}",
                "post_data": post,
            }, status=400)

    title_uz = (post.get("news_title_uz") or "").strip() or raw_title
    title_ru = (post.get("news_title_ru") or "").strip()
    title_en = (post.get("news_title_en") or "").strip()
    desc_uz = (post.get("news_desc_uz") or "").strip() or raw_desc
    desc_ru = (post.get("news_desc_ru") or "").strip()
    desc_en = (post.get("news_desc_en") or "").strip()

    old_photo_name = news.photo.name if news.photo else None
    new_image_name = None

    try:
        with transaction.atomic():
            news.title_uz = title_uz
            news.title_ru = title_ru
            news.title_en = title_en
            news.desc_uz = desc_uz
            news.desc_ru = desc_ru
            news.desc_en = desc_en
            news.date = news_date

            if new_photo_file:
                news.photo = new_photo_file

            news.save()

            if new_photo_file:
                new_image_name = news.photo.name
    except Exception:
        # Транзакция откатилась — но уже записанный на диск новый файл
        # сам по себе не исчезает, подчищаем вручную.
        if new_photo_file:
            default_storage.delete(new_photo_file.name)

        return render(request, "pages/dashboard/news_edit.html", {
            "news": news,
            "error": "Не удалось сохранить новость. Попробуйте ещё раз.",
            "post_data": post,
        }, status=400)

    # ── Успех: старое фото удаляем ТОЛЬКО если оно реально было заменено ──
    if new_image_name and old_photo_name and old_photo_name != new_image_name:
        default_storage.delete(old_photo_name)

    return redirect("action", status="view", path="news", pk=news.id)