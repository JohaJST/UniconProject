# -*- coding: utf-8 -*-
"""
_seed_pagination_stress_data.py
─────────────────────────────────
Наполняет БД тестовыми данными для проверки ВСЕХ 10 пагинируемых списков
дашборда (9 через dlist()/Keyset Engine + selfuser через Offset Engine):

    subject, potok, result, user, quiz, variant, question, selfctg,
    selfquestion, selfuser

Для каждого списка создаётся ~50 "своих" строк (кроме случаев, когда
для этого нужен один общий родитель — например, 50 Question требуют
ровно ОДИН Test-контейнер, иначе они рассыпятся по 50 разным тестам
и не дадут многостраничный список внутри одного tip).

ВАЖНО: ничего не удаляется автоматически. Все PK created здесь
записываются построчно в JSON-манифест `_pagination_seed_manifest.json`
(в корне проекта) — именно по этому манифесту работает парный скрипт
`_cleanup_pagination_stress_data.py`. Не удаляй/не редактируй манифест
вручную, если планируешь потом чистить данные тем скриптом.

Идемпотентность: НЕ идемпотентен. Повторный запуск создаст ещё одну
порцию данных и ПЕРЕЗАПИШЕТ манифест — это осознанно (для повторных
прогонов теста сначала нужно почистить предыдущую порцию через
_cleanup_pagination_stress_data.py).

Запуск: python _seed_pagination_stress_data.py
"""
import json
import os
import uuid
from datetime import timedelta

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "src.settings")
import django

django.setup()

from django.db import transaction
from django.utils import timezone

from core.models import (
    Potok,
    Question,
    Result,
    Subject,
    Test,
    User,
    Variant,
)
from core.models.auth import Role
from core.models.self import SelfCtg, SelfQuestion, SelfResult, SelfUser

MANIFEST_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_pagination_seed_manifest.json")

COUNT = 50                      # "своих" строк на список
RUN_TAG = uuid.uuid4().hex[:8]  # человекочитаемая метка этого прогона
PREFIX = f"PAGTEST_{RUN_TAG}_"

manifest: dict[str, list[int]] = {}


def _track(key: str, ids):
    manifest.setdefault(key, [])
    manifest[key].extend(int(i) for i in ids)


def main():
    now = timezone.now()

    with transaction.atomic():

        # ── 1. subject (tip="subject") — 50 самостоятельных Subject ────────
        subjects = [
            Subject(name_uz=f"{PREFIX}subject_{i}", name_ru=f"{PREFIX}subj_ru_{i}", name_en=f"{PREFIX}subj_en_{i}")
            for i in range(COUNT)
        ]
        Subject.objects.bulk_create(subjects)
        subject_ids = list(
            Subject.objects.filter(name_uz__startswith=f"{PREFIX}subject_").values_list("id", flat=True)
        )
        _track("subject", subject_ids)
        # Разносим created, чтобы страницы имели предсказуемый порядок,
        # а не все одинаковый timestamp (id-тайбрейк и так справится, но
        # так нагляднее при ручной проверке).
        for offset, pk in enumerate(subject_ids):
            Subject.objects.filter(pk=pk).update(created=now - timedelta(seconds=offset))

        # ── 2. potok (tip="potok") — 50 самостоятельных Potok ───────────────
        potoks = [
            Potok(start=timezone.now().date() - timedelta(days=i), end=timezone.now().date() + timedelta(days=30))
            for i in range(COUNT)
        ]
        Potok.objects.bulk_create(potoks)
        # Potok не имеет уникального текстового маркера — берём последние
        # COUNT созданных по id (в рамках одной транзакции это надёжно).
        potok_ids = list(Potok.objects.order_by("-id").values_list("id", flat=True)[:COUNT])
        _track("potok", potok_ids)

        # ── Общие вспомогательные родители (helper_*) ───────────────────────
        # Один Subject/Potok для всех "квизовых" сущностей (quiz/question/
        # variant/result), чтобы не плодить сотни лишних строк.
        helper_subject = Subject.objects.create(
            name_uz=f"{PREFIX}helper_subject", name_ru=f"{PREFIX}helper_subject_ru", name_en=f"{PREFIX}helper_subject_en"
        )
        helper_potok = Potok.objects.create(start=timezone.now().date(), end=timezone.now().date() + timedelta(days=30))
        _track("helper_subject_quiz", [helper_subject.id])
        _track("helper_potok_quiz", [helper_potok.id])

        # ── 3. quiz (tip="quiz") — 50 самостоятельных Test ──────────────────
        quiz_tests = [Test(subject=helper_subject, potok=helper_potok) for _ in range(COUNT)]
        Test.objects.bulk_create(quiz_tests)
        quiz_test_ids = list(Test.objects.order_by("-id").values_list("id", flat=True)[:COUNT])
        _track("quiz_test", quiz_test_ids)
        for offset, pk in enumerate(quiz_test_ids):
            Test.objects.filter(pk=pk).update(created=now - timedelta(seconds=offset))

        # ── 4. question (tip="question") — 50 Question под ОДНИМ Test ───────
        helper_test_questions = Test.objects.create(subject=helper_subject, potok=helper_potok)
        _track("helper_test_questions", [helper_test_questions.id])

        questions = [
            Question(test=helper_test_questions, text_uz=f"{PREFIX}question_{i}", text_ru="", text_en="")
            for i in range(COUNT)
        ]
        Question.objects.bulk_create(questions)
        question_ids = list(
            Question.objects.filter(text_uz__startswith=f"{PREFIX}question_").values_list("id", flat=True)
        )
        _track("question", question_ids)
        for offset, pk in enumerate(question_ids):
            Question.objects.filter(pk=pk).update(created=now - timedelta(seconds=offset))

        # ── 5. variant (tip="variant") — 50 Variant под ОДНИМ Question ──────
        helper_test_variants = Test.objects.create(subject=helper_subject, potok=helper_potok)
        helper_question_variants = Question.objects.create(
            test=helper_test_variants, text_uz=f"{PREFIX}helper_question_for_variants"
        )
        _track("helper_test_variants", [helper_test_variants.id])
        _track("helper_question_variants", [helper_question_variants.id])

        variants = [
            Variant(question=helper_question_variants, text_uz=f"{PREFIX}variant_{i}", is_answer=(i % 5 == 0))
            for i in range(COUNT)
        ]
        Variant.objects.bulk_create(variants)
        variant_ids = list(
            Variant.objects.filter(text_uz__startswith=f"{PREFIX}variant_").values_list("id", flat=True)
        )
        _track("variant", variant_ids)

        # ── 6. selfctg (tip="selfctg") — 50 самостоятельных SelfCtg ─────────
        selfctgs = [
            SelfCtg(name_uz=f"{PREFIX}selfctg_{i}", name_ru="", name_en="")
            for i in range(COUNT)
        ]
        SelfCtg.objects.bulk_create(selfctgs)
        selfctg_ids = list(
            SelfCtg.objects.filter(name_uz__startswith=f"{PREFIX}selfctg_").values_list("id", flat=True)
        )
        _track("selfctg", selfctg_ids)
        for offset, pk in enumerate(selfctg_ids):
            SelfCtg.objects.filter(pk=pk).update(created=now - timedelta(seconds=offset))

        # ── 7. selfquestion (tip="selfquestion") — 50 под ОДНОЙ SelfCtg ─────
        helper_selfctg_sq = SelfCtg.objects.create(name_uz=f"{PREFIX}helper_selfctg_for_selfquestions")
        _track("helper_selfctg_selfquestions", [helper_selfctg_sq.id])

        selfquestions = [
            SelfQuestion(ctg=helper_selfctg_sq, text_uz=f"{PREFIX}selfquestion_{i}")
            for i in range(COUNT)
        ]
        SelfQuestion.objects.bulk_create(selfquestions)
        selfquestion_ids = list(
            SelfQuestion.objects.filter(text_uz__startswith=f"{PREFIX}selfquestion_").values_list("id", flat=True)
        )
        _track("selfquestion", selfquestion_ids)

        # ── 8. user (tip="user") — 50 самостоятельных студентов ─────────────
        user_ids = []
        for i in range(COUNT):
            u = User.objects.create_user(
                username=f"{PREFIX}user_{i}",
                password="pagtest12345",
                role=Role.STUDENT,
                name=f"{PREFIX}Name{i}",
                last_name=f"{PREFIX}Last{i}",
            )
            user_ids.append(u.id)
        _track("user", user_ids)
        for offset, pk in enumerate(user_ids):
            User.objects.filter(pk=pk).update(created=timezone.now().date() - timedelta(days=offset))

        # ── 9. result (tip="result") — 50 Result, несколько helper-авторов ──
        helper_test_results = Test.objects.create(subject=helper_subject, potok=helper_potok)
        _track("helper_test_results", [helper_test_results.id])

        helper_result_users = []
        for i in range(5):
            hu = User.objects.create_user(
                username=f"{PREFIX}result_author_{i}",
                password="pagtest12345",
                role=Role.STUDENT,
                name=f"{PREFIX}ResultAuthor{i}",
                last_name=f"{PREFIX}RA{i}",
                potok=helper_potok,
            )
            helper_result_users.append(hu)
        _track("helper_users_results", [u.id for u in helper_result_users])

        results = []
        for i in range(COUNT):
            author = helper_result_users[i % len(helper_result_users)]
            results.append(Result(
                user=author,
                test=helper_test_results,
                result=i % 10,
                foyiz=(i * 7) % 101,
                totalQuestions=10,
                time=60 + i,
            ))
        Result.objects.bulk_create(results)
        result_ids = list(Result.objects.filter(test=helper_test_results).order_by("-id").values_list("id", flat=True)[:COUNT])
        _track("result", result_ids)
        for offset, pk in enumerate(result_ids):
            Result.objects.filter(pk=pk).update(created=now - timedelta(seconds=offset))

        # ── 10. selfuser (offset-список, tip="selfresult") ──────────────────
        # Каждому SelfUser даём ровно один SelfResult, иначе last_attempt
        # будет NULL и все 50 схлопнутся в "хвост без даты" — менее полезно
        # для проверки сортировки offset-движка.
        helper_selfctg_su = SelfCtg.objects.create(name_uz=f"{PREFIX}helper_selfctg_for_selfusers")
        _track("helper_selfctg_selfusers", [helper_selfctg_su.id])

        selfuser_ids = []
        selfresult_ids = []
        for i in range(COUNT):
            su = SelfUser.objects.create(
                first_name=f"{PREFIX}SUFirst{i}", last_name=f"{PREFIX}SULast{i}"
            )
            selfuser_ids.append(su.id)
            sr = SelfResult.objects.create(
                user=su, ctg=helper_selfctg_su,
                score=i % 20, foiz=(i * 5) % 101, totalQuestions=20,
            )
            selfresult_ids.append(sr.id)
            # updated (last_attempt) разносим, чтобы offset-сортировка была
            # детерминированной и проверяемой (более новые — выше).
            SelfResult.objects.filter(pk=sr.pk).update(updated=now - timedelta(seconds=i))

        _track("selfuser", selfuser_ids)
        _track("selfresult", selfresult_ids)

    manifest["_run_tag"] = RUN_TAG
    manifest["_prefix"] = PREFIX
    with open(MANIFEST_PATH, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    total = sum(len(v) for k, v in manifest.items() if isinstance(v, list))
    print(f"Готово. run_tag={RUN_TAG}, префикс={PREFIX!r}")
    print(f"Манифест сохранён: {MANIFEST_PATH}")
    print(f"Суммарно создано строк (включая helper-объекты): {total}")
    for key, ids in manifest.items():
        if isinstance(ids, list):
            print(f"  {key:32s} -> {len(ids)} шт.")


if __name__ == "__main__":
    main()