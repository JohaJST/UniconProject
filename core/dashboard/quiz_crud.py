"""
core/dashboard/quiz_crud.py
────────────────────────────
CRUD-view для теста (Test) в дашборде.

view_quiz — просмотр (без изменений).
edit_quiz — полное редактирование: метаданные теста (subject + potok) +
            структура Test -> Question -> Variant.

RBAC и sliding-window таймаут дашборда проверяет DashboardSecurityMiddleware —
свои проверки прав здесь не нужны.

Паттерн вложенного id-based diff (create/update/delete + IDOR-защита через
фильтрацию по родителю) скопирован 1-в-1 с core/dashboard/self_check.py.
Обработка картинок переиспользует core/media_utils.process_uploaded_image.
"""
from __future__ import annotations

import re

from django.contrib.auth.decorators import login_required
from django.core.files.storage import default_storage
from django.db import transaction
from django.db.models import Avg, Count
from django.shortcuts import get_object_or_404, redirect, render

from core.media_utils import InvalidImageError, process_uploaded_image
from core.models import (
    Potok,
    Question,
    Result,
    Subject,
    Test,
    Variant,
)

_QUESTION_RE = re.compile(r"question_(\d+)")
_VARIANT_RE = re.compile(r"variant_(\d+)_(\d+)")


@login_required(login_url="login")
def view_quiz(request, pk):
    """
    Карточка теста: предмет + поток, статистика попыток + полная структура
    Question -> Answer для просмотра содержимого теста.

    prefetch_related('questions__answers') обязателен: в шаблоне цикл
    questions -> answers иначе даст классический N+1.
    """
    test = get_object_or_404(
        Test.objects
        .select_related('subject', 'potok')
        .prefetch_related('questions__answers'),
        pk=pk,
    )

    results = Result.objects.filter(test=test)
    attempt_count = results.count()
    avg_score = results.aggregate(avg=Avg('foyiz'))['avg']

    ctx = {
        "test": test,
        "attempt_count": attempt_count,
        "avg_score": round(avg_score, 1) if avg_score is not None else None,
    }
    return render(request, "pages/dashboard/quiz_detail.html", ctx)


# ─────────────────────────────────────────────────────────────────────────────
# edit_quiz
# ─────────────────────────────────────────────────────────────────────────────

def _build_test_data(test: Test) -> dict:
    """
    Собирает JSON-сериализуемый снимок теста для шаблона (json_script).

    DOM вопросов/вариантов строит ТОЛЬКО JS (addQuestionField/addVariantField) —
    сервер никогда не рендерит question-card напрямую в шаблон, иначе
    JS-счётчики (questionCounter/variantCounters) и Django-индексы разъедутся
    при первом же добавлении/удалении карточки на клиенте.
    """
    questions_data = []
    for q in test.questions.prefetch_related('answers').all():
        questions_data.append({
            "id": q.id,
            "text_uz": q.text_uz or "",
            "text_ru": q.text_ru or "",
            "text_en": q.text_en or "",
            "img_url": q.img.url if q.img else None,
            "variants": [
                {
                    "id": v.id,
                    "text_uz": v.text_uz or "",
                    "text_ru": v.text_ru or "",
                    "text_en": v.text_en or "",
                    "is_answer": v.is_answer,
                }
                for v in q.answers.all()
            ],
        })

    return {
        "subject_id": test.subject_id,
        "potok_id": test.potok_id,
        "questions": questions_data,
    }


@login_required(login_url="login")
def edit_quiz(request, pk):
    """
    Полное редактирование теста.

    GET  — рендерит форму, снимок текущего состояния передаётся в шаблон
           через test_data (json_script), поля/вопросы/варианты заполняет JS.

    POST — валидация -> обработка картинок вопросов ДО транзакции ->
           одна атомарная транзакция:
             1. метаданные теста (subject, potok);
             2. id-based diff вопросов (test=this_test) и, вложенно,
                id-based diff вариантов ответа (question=<этот вопрос>) —
                IDOR-защита через обязательную фильтрацию по родителю.
           Файлы на диске, реально записанные в этом запросе, но не
           закоммиченные (транзакция упала) — подчищаются вручную; заменённые/
           убранные картинки старых записей удаляются ПОСЛЕ успешного commit.
    """
    test = get_object_or_404(Test, pk=pk)

    subjects = Subject.objects.all()
    potoks = Potok.objects.all()

    def _render(errors=None, status=200):
        return render(request, "pages/dashboard/quiz_edit.html", {
            "test": test,
            "subjects": subjects,
            "potoks": potoks,
            "test_data": _build_test_data(test),
            "errors": errors,
        }, status=status)

    if request.method != "POST":
        return _render()

    post_data = request.POST
    files = request.FILES
    errors = []

    # ═══════════════════════════════════════════════════════════════════════
    # 1. ВАЛИДАЦИЯ ФОРМЫ
    # ═══════════════════════════════════════════════════════════════════════
    subject_id = post_data.get("subject")
    if not subject_id or not Subject.objects.filter(id=subject_id).exists():
        errors.append("Выберите корректный предмет")

    question_indexes = sorted({
        int(m.group(1)) for key in post_data
        if (m := _QUESTION_RE.fullmatch(key))
    })

    # индексы вариантов на вопрос, собираются один раз и переиспользуются
    # и в валидации, и в блоке сохранения
    variants_by_question: dict[int, set[int]] = {}
    for key in post_data:
        m = _VARIANT_RE.fullmatch(key)
        if m:
            qidx, vidx = int(m.group(1)), int(m.group(2))
            variants_by_question.setdefault(qidx, set()).add(vidx)

    if not question_indexes:
        errors.append("Нужен как минимум один вопрос")

    for qidx in question_indexes:
        v_indexes = sorted(variants_by_question.get(qidx, set()))
        if len(v_indexes) < 2:
            errors.append(f"Вопрос #{qidx}: нужно как минимум 2 варианта ответа")
            continue
        correct_count = sum(
            1 for vidx in v_indexes if f"answer_{qidx}_{vidx}" in post_data
        )
        if correct_count < 1:
            errors.append(f"Вопрос #{qidx}: нужно отметить хотя бы один верный ответ")
        for vidx in v_indexes:
            if not (post_data.get(f"variant_{qidx}_{vidx}") or "").strip():
                errors.append(f"Вопрос #{qidx}, вариант #{vidx}: текст не может быть пустым")

    if errors:
        return _render(errors, status=400)

    # ═══════════════════════════════════════════════════════════════════════
    # 2. ОБРАБОТКА КАРТИНОК ВОПРОСОВ — ДО ТРАНЗАКЦИИ
    # ═══════════════════════════════════════════════════════════════════════
    question_image_files = {}  # qidx -> ContentFile
    try:
        for qidx in question_indexes:
            raw_img = files.get(f"question_{qidx}_image")
            if raw_img:
                question_image_files[qidx] = process_uploaded_image(raw_img)
    except InvalidImageError as exc:
        errors.append(f"Ошибка изображения в вопросе: {exc}")
        return _render(errors, status=400)

    # ═══════════════════════════════════════════════════════════════════════
    # 3. СОХРАНЕНИЕ В ТРАНЗАКЦИИ
    # ═══════════════════════════════════════════════════════════════════════
    new_image_names: list[str] = []
    stale_image_names: list[str] = []

    try:
        with transaction.atomic():
            # ── Метаданные теста: subject + potok ──────────────────────────
            test.subject_id = int(subject_id)
            potok_id = post_data.get("potok")
            test.potok_id = int(potok_id) if potok_id else None
            test.save()

            # ── Вопросы (id-based diff, test=this_test) ─────────────────────
            submitted_question_ids = []

            for qidx in question_indexes:
                q_id = post_data.get(f"question_id_{qidx}")
                question = None
                if q_id:
                    # IDOR-защита: вопрос должен принадлежать ИМЕННО этому тесту.
                    question = Question.objects.filter(
                        id=q_id, test=test
                    ).first()

                is_new_question = question is None
                if is_new_question:
                    question = Question(test=test)

                raw_q_text = (post_data.get(f"question_{qidx}") or "")
                question.text_uz = (post_data.get(f"question_{qidx}_uz") or "").strip() or raw_q_text.strip()
                question.text_ru = (post_data.get(f"question_{qidx}_ru") or "").strip()
                question.text_en = (post_data.get(f"question_{qidx}_en") or "").strip()

                old_q_img_name = (
                    question.img.name if (not is_new_question and question.img) else None
                )

                img_file = question_image_files.get(qidx)
                img_clear = post_data.get(f"question_{qidx}_img_clear") == "1"

                if img_file:
                    question.img = img_file
                    if old_q_img_name:
                        stale_image_names.append(old_q_img_name)
                elif img_clear and not is_new_question:
                    question.img = None
                    if old_q_img_name:
                        stale_image_names.append(old_q_img_name)

                question.save()

                if img_file:
                    new_image_names.append(question.img.name)

                submitted_question_ids.append(question.id)

                # ── Варианты ответа этого вопроса (id-based diff) ──────────
                v_indexes = sorted(variants_by_question.get(qidx, set()))
                submitted_variant_ids = []

                for vidx in v_indexes:
                    v_id = post_data.get(f"variant_id_{qidx}_{vidx}")
                    variant = None
                    if v_id:
                        # IDOR-защита: вариант должен принадлежать ИМЕННО
                        # этому вопросу, а не любому в базе.
                        variant = Variant.objects.filter(id=v_id, question=question).first()

                    if variant is None:
                        variant = Variant(question=question)

                    raw_v_text = post_data.get(f"variant_{qidx}_{vidx}", "")
                    variant.text_uz = (post_data.get(f"variant_{qidx}_{vidx}_uz") or "").strip() or raw_v_text.strip()
                    variant.text_ru = (post_data.get(f"variant_{qidx}_{vidx}_ru") or "").strip()
                    variant.text_en = (post_data.get(f"variant_{qidx}_{vidx}_en") or "").strip()
                    variant.is_answer = f"answer_{qidx}_{vidx}" in post_data

                    variant.save()
                    submitted_variant_ids.append(variant.id)

                # Варианты, не пришедшие в сабмите для ЭТОГО вопроса — удаляем.
                Variant.objects.filter(question=question).exclude(
                    id__in=submitted_variant_ids
                ).delete()

            # Вопросы, которых нет среди присланных — удаляем (каскадно
            # удалит и их Variant-ы). Собираем картинки на удаление ДО delete().
            removed_questions = Question.objects.filter(
                test=test
            ).exclude(id__in=submitted_question_ids)
            for removed in removed_questions:
                if removed.img:
                    stale_image_names.append(removed.img.name)
            removed_questions.delete()

    except Exception:
        # Транзакция откатилась — но уже записанные на диск файлы сами
        # по себе не исчезают, подчищаем вручную.
        for name in new_image_names:
            default_storage.delete(name)

        errors.append("Не удалось сохранить тест. Попробуйте ещё раз.")
        return _render(errors, status=400)

    # ── Успех: удаляем старые/убранные файлы, которые больше не нужны ──────
    for name in stale_image_names:
        default_storage.delete(name)

    return redirect("action", status="view", path="quiz", pk=test.id)
