"""
core/dashboard/news_crud.py
────────────────────────────────
CRUD-view для новостей (News) + галерея дополнительных фото (NewsImage).

Паттерн картинок (как в self_check.py): process_uploaded_image() вызывается
ДО transaction.atomic(), старые файлы удаляются физически только ПОСЛЕ commit,
а файлы, записанные в упавшей транзакции, подчищаются вручную.

Удаление фото галереи защищено от IDOR: NewsImage ищется только среди
фото ЭТОЙ новости (filter(news=news, id__in=...)).
"""
from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.files.storage import default_storage
from django.db import transaction
from django.db.models.fields import DateField
from django.shortcuts import get_object_or_404, redirect, render

from core.media_utils import InvalidImageError, process_uploaded_image
from core.models import News, NewsImage

# Должно совпадать с data-max в templates/pages/dashboard/_gallery_input.html
MAX_GALLERY_PHOTOS = 20


def process_gallery(files, field: str = "news_gallery"):
    """
    Обрабатывает ВСЕ загруженные фото галереи через process_uploaded_image.
    Вызывать ДО transaction.atomic().
    :return: (list[ContentFile], None) либо ([], "текст ошибки")
    """
    raw = [f for f in files.getlist(field) if f]
    if len(raw) > MAX_GALLERY_PHOTOS:
        return [], f"Слишком много фото в галерее (максимум {MAX_GALLERY_PHOTOS})"

    processed = []
    for i, f in enumerate(raw, start=1):
        try:
            processed.append(process_uploaded_image(f))
        except InvalidImageError as exc:
            return [], f"Фото галереи №{i}: {exc}"
    return processed, None


def save_gallery(news, processed_files, saved_names: list) -> None:
    """
    Создаёт NewsImage для каждого файла (внутри transaction.atomic()).
    Имена реально записанных на диск файлов копятся в saved_names — по ним
    вызывающий код чистит диск, если транзакция откатилась.
    """
    for f in processed_files:
        img = NewsImage(news=news)
        img.image = f
        try:
            img.save()
        except Exception:
            if img.image and getattr(img.image, "_committed", False):
                saved_names.append(img.image.name)
            raise
        saved_names.append(img.image.name)


@login_required(login_url="login")
def view_news(request, pk):
    """Карточка новости: заголовок/описание на 3 языках, дата, фото + галерея."""
    news = get_object_or_404(News, pk=pk)
    ctx = {"news": news, "gallery": news.images.all()}
    return render(request, "pages/dashboard/news_detail.html", ctx)


@login_required(login_url="login")
def edit_news(request, pk):
    """
    Редактирование новости.

    POST — валидация -> обработка главного фото И новых фото галереи ДО
    транзакции -> одна атомарная транзакция (поля, удаление отмеченных фото
    галереи, добавление новых). Старые файлы удаляются после commit.
    """
    news = get_object_or_404(News, pk=pk)

    if request.method != "POST":
        return render(request, "pages/dashboard/news_edit.html", {"news": news})

    post = request.POST
    files = request.FILES

    def fail(message):
        return render(request, "pages/dashboard/news_edit.html", {
            "news": news,
            "error": message,
            "post_data": post,
        }, status=400)

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
        return fail("; ".join(errors))

    # ── Главное фото: ДО транзакции ───────────────────────────────────────
    new_photo_file = None
    raw_photo = files.get("news_photo")
    if raw_photo:
        try:
            new_photo_file = process_uploaded_image(raw_photo)
        except InvalidImageError as exc:
            return fail(f"Ошибка изображения: {exc}")

    # ── Галерея: ДО транзакции ────────────────────────────────────────────
    gallery_files, gallery_error = process_gallery(files)
    if gallery_error:
        return fail(gallery_error)

    delete_ids = {int(x) for x in post.getlist("gallery_delete") if x.isdigit()}
    kept = news.images.exclude(id__in=delete_ids).count()
    if kept + len(gallery_files) > MAX_GALLERY_PHOTOS:
        return fail(f"В галерее может быть не более {MAX_GALLERY_PHOTOS} фото")

    title_uz = (post.get("news_title_uz") or "").strip() or raw_title
    title_ru = (post.get("news_title_ru") or "").strip()
    title_en = (post.get("news_title_en") or "").strip()
    desc_uz = (post.get("news_desc_uz") or "").strip() or raw_desc
    desc_ru = (post.get("news_desc_ru") or "").strip()
    desc_en = (post.get("news_desc_en") or "").strip()

    old_photo_name = news.photo.name if news.photo else None
    new_image_name = None
    new_gallery_names: list[str] = []
    stale_gallery_names: list[str] = []

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

            # IDOR-защита: удаляем только фото ЭТОЙ новости.
            if delete_ids:
                doomed = list(NewsImage.objects.filter(news=news, id__in=delete_ids))
                stale_gallery_names = [d.image.name for d in doomed if d.image]
                NewsImage.objects.filter(pk__in=[d.pk for d in doomed]).delete()

            save_gallery(news, gallery_files, new_gallery_names)
    except Exception:
        stored_name = new_image_name
        if (
            stored_name is None
            and new_photo_file
            and news.photo
            and getattr(news.photo, "_committed", False)
            and news.photo.name != old_photo_name
        ):
            stored_name = news.photo.name
        if stored_name:
            default_storage.delete(stored_name)
        for name in new_gallery_names:
            default_storage.delete(name)

        return fail("Не удалось сохранить новость. Попробуйте ещё раз.")

    # ── Успех: физически удаляем заменённое/убранное ──────────────────────
    if new_image_name and old_photo_name and old_photo_name != new_image_name:
        default_storage.delete(old_photo_name)
    for name in stale_gallery_names:
        default_storage.delete(name)

    return redirect("action", status="view", path="news", pk=news.id)