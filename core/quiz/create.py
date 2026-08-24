"""
core/quiz/create.py
───────────────────
Создание теста из дашборда (форма new.html, action == "test").

Структура Test -> Question -> Variant. Вопросы и варианты сохраняются
сразу с переводами (text_uz/ru/en) — форма их присылает, а старый код
их молча выбрасывал. Картинки вопросов читаются из request.FILES и
проходят process_uploaded_image (лимит размера, WEBP).

Ошибки валидации возвращают форму с баннером (400), а не 500.
"""
from __future__ import annotations

import re

from django.contrib.auth.decorators import login_required
from django.core.files.storage import default_storage
from django.db import transaction
from django.shortcuts import redirect, render

from core.media_utils import InvalidImageError, process_uploaded_image
from core.models import Potok, Question, Subject, Test, Variant

_QUESTION_RE = re.compile(r"question_(\d+)")
_VARIANT_RE = re.compile(r"variant_(\d+)_(\d+)")


def _fail(request, error: str):
    """Форма с баннером ошибки и 400 — без потери выпадающих списков."""
    return render(
        request,
        "pages/dashboard/new.html",
        {
            "subjects": Subject.objects.all(),
            "potoks": Potok.objects.all(),
            "action": "test",
            "error": error,
        },
        status=400,
    )


@login_required(login_url="login")
def create_test(request):
    if request.method != "POST":
        return redirect("dashboard")

    post = request.POST
    files = request.FILES

    # ── Метаданные: предмет и поток ───────────────────────────────────────
    # Валидируем СТРОГО: id из формы не обязан быть числом, и мы не должны
    # ронять 500 на int()/Subject.DoesNotExist (как это было раньше).
    subject_id = (post.get("subject") or "").strip()
    subject = Subject.objects.filter(id=subject_id).first() if subject_id.isdigit() else None
    if subject is None:
        return _fail(request, "Выберите корректный предмет")

    potok_id = (post.get("potok") or "").strip()
    potok_id_int = int(potok_id) if potok_id.isdigit() else None

    # ── Индексы вопросов/вариантов из имён полей ──────────────────────────
    question_indexes = sorted({
        int(m.group(1)) for key in post if (m := _QUESTION_RE.fullmatch(key))
    })
    if not question_indexes:
        return _fail(request, "Нужен хотя бы один вопрос")

    variants_by_question: dict[int, set[int]] = {}
    for key in post:
        m = _VARIANT_RE.fullmatch(key)
        if m:
            qidx, vidx = int(m.group(1)), int(m.group(2))
            variants_by_question.setdefault(qidx, set()).add(vidx)

    # ── Валидация контента ────────────────────────────────────────────────
    errors = []
    for qidx in question_indexes:
        raw_q = (post.get(f"question_{qidx}") or "").strip()
        uz_q = (post.get(f"question_{qidx}_uz") or "").strip()
        if not raw_q and not uz_q:
            errors.append(f"Вопрос #{qidx}: текст обязателен")

        v_indexes = sorted(variants_by_question.get(qidx, set()))
        if len(v_indexes) < 2:
            errors.append(f"Вопрос #{qidx}: нужно минимум 2 варианта ответа")
            continue
        if not any(f"answer_{qidx}_{vidx}" in post for vidx in v_indexes):
            errors.append(f"Вопрос #{qidx}: отметьте хотя бы один верный ответ")
        for vidx in v_indexes:
            if not (post.get(f"variant_{qidx}_{vidx}") or "").strip():
                errors.append(f"Вопрос #{qidx}, вариант #{vidx}: текст не может быть пустым")

    if errors:
        return _fail(request, "; ".join(errors))

    # ── Картинки: обработка ДО транзакции (см. self_check.py) ─────────────
    image_files: dict[int, object] = {}
    try:
        for qidx in question_indexes:
            raw_img = files.get(f"question_{qidx}_image")
            if raw_img:
                image_files[qidx] = process_uploaded_image(raw_img)
    except InvalidImageError as exc:
        return _fail(request, f"Ошибка изображения: {exc}")

    # ── Сохранение в одной транзакции ─────────────────────────────────────
    new_image_names: list[str] = []

    try:
        with transaction.atomic():
            test = Test.objects.create(subject=subject, potok_id=potok_id_int)

            for qidx in question_indexes:
                raw_q_text = (post.get(f"question_{qidx}") or "").strip()
                question = Question.objects.create(
                    test=test,
                    text_uz=(post.get(f"question_{qidx}_uz") or "").strip() or raw_q_text,
                    text_ru=(post.get(f"question_{qidx}_ru") or "").strip(),
                    text_en=(post.get(f"question_{qidx}_en") or "").strip(),
                    img=image_files.get(qidx),
                )
                if image_files.get(qidx):
                    new_image_names.append(question.img.name)

                for vidx in sorted(variants_by_question.get(qidx, set())):
                    raw_v_text = (post.get(f"variant_{qidx}_{vidx}") or "").strip()
                    Variant.objects.create(
                        question=question,
                        text_uz=(post.get(f"variant_{qidx}_{vidx}_uz") or "").strip() or raw_v_text,
                        text_ru=(post.get(f"variant_{qidx}_{vidx}_ru") or "").strip(),
                        text_en=(post.get(f"variant_{qidx}_{vidx}_en") or "").strip(),
                        is_answer=f"answer_{qidx}_{vidx}" in post,
                    )
    except Exception:
        # Транзакция откатилась — записанные на диск файлы подчищаем вручную.
        for name in new_image_names:
            default_storage.delete(name)
        return _fail(request, "Не удалось создать тест. Попробуйте ещё раз.")

    return redirect("dashboard")
