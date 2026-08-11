"""
core/dashboard/self_check.py
──────────────────────────────
CRUD-view для вопросов самопроверки (SelfQuestion + SelfAnswer).

Один view обслуживает и создание, и редактирование:
    /dashboard/self-check/create/       (pk=None)
    /dashboard/self-check/<pk>/edit/

Правила:
  - Картинки валидируются/пережимаются через core.media_utils
    ДО начала транзакции — чтобы не держать транзакцию открытой на время
    декодирования/ресайза изображений в Pillow.
  - Переводы (uz/ru/en) разруливает _resolve_translation(): если явного
    перевода не пришло — используется страховочный fallback, а сам факт
    "перевод неполный" помечается флагом needs_review на вопросе.
  - Ответы сопоставляются с уже существующими по answer_id_{i}, но ТОЛЬКО
    в пределах текущего question (SelfAnswer.objects.filter(id=..,
    question=question)) — иначе можно было бы IDOR-ом переписать чужой
    ответ, подставив произвольный id в форму.
  - Если что-то в БД-транзакции пошло не так — уже физически записанные
    на диск файлы (Django не откатывает FileStorage вместе с транзакцией)
    подчищаются вручную.
"""
from __future__ import annotations

import re

from django.contrib.auth.decorators import login_required
from django.core.files.storage import default_storage
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render

from core.media_utils import InvalidImageError, process_uploaded_image
from core.models.self import SelfAnswer, SelfQuestion

_ANSWER_TEXT_RE = re.compile(r"answer_text_(\d+)$")


def _build_error_context(post_data, question, answers, errors=None):
    answer_indexes = sorted({
        int(m.group(1)) for key in post_data
        if (m := _ANSWER_TEXT_RE.fullmatch(key))
    })
    form_answers = [
        {
            "id": post_data.get(f"answer_id_{idx}", ""),
            "text": post_data.get(f"answer_text_{idx}", ""),
            "text_uz": post_data.get(f"answer_text_{idx}_uz", ""),
            "text_ru": post_data.get(f"answer_text_{idx}_ru", ""),
            "text_en": post_data.get(f"answer_text_{idx}_en", ""),
            "is_correct": f"answer_correct_{idx}" in post_data,
        }
        for idx in answer_indexes
    ]
    ctx = {"question": question, "answers": answers, "post_data": post_data, "form_answers": form_answers}
    if errors:
        ctx["errors"] = errors
    return ctx

# ─────────────────────────────────────────────────────────────────────────────
# Хелпер: разрешение перевода одного текстового поля
# ─────────────────────────────────────────────────────────────────────────────
def _resolve_translation(raw_text, uz, ru, en):
    """
    Собирает итоговые значения uz/ru/en для одного переводимого поля.

    :param raw_text: значение основного (видимого) поля формы — используется
        как fallback для uz, если явный uz-перевод не пришёл (например,
        AI-перевод не запускался и скрытые поля пустые).
    :param uz: значение скрытого поля <field>_uz (может быть None/пустым)
    :param ru: значение скрытого поля <field>_ru
    :param en: значение скрытого поля <field>_en
    :return: (uz, ru, en, was_missing) — was_missing=True, если хотя бы одно
        из трёх итоговых значений после strip() оказалось пустым.
    """
    raw = (raw_text or "").strip()

    uz = (uz or "").strip() or raw
    ru = (ru or "").strip()
    en = (en or "").strip()

    was_missing = not uz or not ru or not en
    return uz, ru, en, was_missing


# ─────────────────────────────────────────────────────────────────────────────
# View
# ─────────────────────────────────────────────────────────────────────────────
@login_required(login_url="login")
def create_or_edit_self_question(request, pk=None):
    question = get_object_or_404(SelfQuestion, pk=pk) if pk else None
    answers = question.selfanswer_set.order_by("id").all() if question else SelfAnswer.objects.none()

    # ── GET: просто рендерим форму ──────────────────────────────────────────
    if request.method != "POST":
        return render(request, "pages/dashboard/self_check_form.html", {
            "question": question,
            "answers": answers,
        })

    post_data = request.POST
    files = request.FILES

    # ═══════════════════════════════════════════════════════════════════════
    # 1. ВАЛИДАЦИЯ ФОРМЫ
    # ═══════════════════════════════════════════════════════════════════════
    errors = []

    question_text = (post_data.get("question_text") or "").strip()
    if not question_text:
        errors.append("Текст вопроса обязателен")

    # Индексы присланных ответов — по полю answer_text_{i}, отсортированные
    # по номеру, чтобы порядок отображения был стабильным.
    answer_indexes = sorted({
        int(m.group(1)) for key in post_data
        if (m := _ANSWER_TEXT_RE.fullmatch(key))
    })

    if len(answer_indexes) < 2:
        errors.append("Нужно как минимум 2 варианта ответа")

    correct_count = sum(
        1 for idx in answer_indexes
        if f"answer_correct_{idx}" in post_data
    )
    if correct_count < 1:
        errors.append("Нужно отметить хотя бы один верный ответ")

    # Тексты ответов не должны быть пустыми
    for idx in answer_indexes:
        if not (post_data.get(f"answer_text_{idx}") or "").strip():
            errors.append(f"Текст ответа #{idx} не может быть пустым")

    if errors:
        return render(request, "pages/dashboard/self_check_form.html",
                      _build_error_context(post_data, question, answers, errors), status=400)

    # ═══════════════════════════════════════════════════════════════════════
    # 2. ОБРАБОТКА КАРТИНОК — ДО ТРАНЗАКЦИИ
    # ═══════════════════════════════════════════════════════════════════════
    question_image_file = None
    answer_image_files = {}  # idx -> ContentFile

    try:
        raw_q_image = files.get("question_image")
        if raw_q_image:
            question_image_file = process_uploaded_image(raw_q_image)

        for idx in answer_indexes:
            raw_a_image = files.get(f"answer_image_{idx}")
            if raw_a_image:
                answer_image_files[idx] = process_uploaded_image(raw_a_image)

    except InvalidImageError as exc:
        errors.append(f"Ошибка изображения: {exc}")
        return render(request, "pages/dashboard/self_check_form.html",
                      _build_error_context(post_data, question, answers, errors), status=400)

    # ═══════════════════════════════════════════════════════════════════════
    # 3. ПЕРЕВОДЫ И ЧЕКБОКСЫ ОЧИСТКИ ИЗОБРАЖЕНИЙ
    # ═══════════════════════════════════════════════════════════════════════
    q_uz, q_ru, q_en, q_missing = _resolve_translation(
        question_text,
        post_data.get("question_text_uz"),
        post_data.get("question_text_ru"),
        post_data.get("question_text_en"),
    )

    any_missing = q_missing
    question_img_clear = post_data.get("question_img_clear") == "1"

    resolved_answers = {}  # idx -> (uz, ru, en, is_correct, img_clear)
    for idx in answer_indexes:
        raw_answer_text = post_data.get(f"answer_text_{idx}")
        a_uz, a_ru, a_en, a_missing = _resolve_translation(
            raw_answer_text,
            post_data.get(f"answer_text_{idx}_uz"),
            post_data.get(f"answer_text_{idx}_ru"),
            post_data.get(f"answer_text_{idx}_en"),
        )
        any_missing = any_missing or a_missing
        resolved_answers[idx] = {
            "uz": a_uz,
            "ru": a_ru,
            "en": a_en,
            "is_correct": f"answer_correct_{idx}" in post_data,
            "img_clear": post_data.get(f"answer_img_clear_{idx}") == "1",
        }

    needs_review = any_missing

    # ═══════════════════════════════════════════════════════════════════════
    # 4. СОХРАНЕНИЕ В ТРАНЗАКЦИИ
    # ═══════════════════════════════════════════════════════════════════════
    # Django не откатывает файлы на диске вместе с транзакцией БД — если
    # что-то упадёт по дороге, физически уже записанные файлы удаляем
    # вручную в except-ветке.
    new_image_names = []      # файлы, реально записанные на диск в этом запросе
    stale_image_names = []    # старые файлы, которые нужно удалить ПОСЛЕ commit

    try:
        with transaction.atomic():
            # ── Question ─────────────────────────────────────────────────
            if question is None:
                question = SelfQuestion(
                    text_uz=q_uz,
                    text_ru=q_ru,
                    text_en=q_en,
                    needs_review=needs_review,
                )
                if question_image_file:
                    question.img = question_image_file
                question.save()
                if question_image_file:
                    new_image_names.append(question.img.name)
            else:
                old_q_img_name = question.img.name if question.img else None

                question.text_uz = q_uz
                question.text_ru = q_ru
                question.text_en = q_en
                question.needs_review = needs_review

                if question_image_file:
                    question.img = question_image_file
                    if old_q_img_name:
                        stale_image_names.append(old_q_img_name)
                elif question_img_clear:
                    question.img = None
                    if old_q_img_name:
                        stale_image_names.append(old_q_img_name)

                question.save()

                if question_image_file:
                    new_image_names.append(question.img.name)

            # ── Answers ──────────────────────────────────────────────────
            submitted_ids = []

            for idx in answer_indexes:
                data = resolved_answers[idx]
                answer_id = post_data.get(f"answer_id_{idx}")

                instance = None
                if answer_id:
                    # IDOR-защита: ищем существующий ответ ТОЛЬКО среди
                    # ответов, принадлежащих текущему question.
                    instance = SelfAnswer.objects.filter(
                        id=answer_id, question=question
                    ).first()

                is_new = instance is None
                if is_new:
                    instance = SelfAnswer(question=question)

                old_a_img_name = (
                    instance.img.name if (not is_new and instance.img) else None
                )

                instance.text_uz = data["uz"]
                instance.text_ru = data["ru"]
                instance.text_en = data["en"]
                instance.is_correct = data["is_correct"]

                img_file = answer_image_files.get(idx)
                if img_file:
                    instance.img = img_file
                    if old_a_img_name:
                        stale_image_names.append(old_a_img_name)
                elif data["img_clear"] and not is_new:
                    instance.img = None
                    if old_a_img_name:
                        stale_image_names.append(old_a_img_name)

                instance.save()

                if img_file:
                    new_image_names.append(instance.img.name)

                submitted_ids.append(instance.id)

            # Ответы, которых нет среди присланных — удаляем (актуально
            # только для редактирования; на создании submitted_ids
            # покрывает все только что созданные записи).
            removed_qs = SelfAnswer.objects.filter(question=question).exclude(
                id__in=submitted_ids
            )
            for removed in removed_qs:
                if removed.img:
                    stale_image_names.append(removed.img.name)
            removed_qs.delete()

    except Exception as exc:
        # Транзакция БД откатилась — но файлы, уже записанные на диск,
        # сами по себе не исчезают. Подчищаем их вручную.
        for name in new_image_names:
            default_storage.delete(name)

        errors.append("Не удалось сохранить вопрос. Попробуйте ещё раз.")
        return render(request, "pages/dashboard/self_check_form.html",
                      _build_error_context(post_data, question, answers, errors), status=400)

    # ── Успех: удаляем старые файлы, которые были заменены/убраны ────────
    for name in stale_image_names:
        default_storage.delete(name)

    return redirect("dlist", tip="selfquestion")