# -*- coding: utf-8 -*-
"""
_cleanup_pagination_stress_data.py
─────────────────────────────────────
Удаляет ТОЛЬКО те записи, которые были созданы парным скриптом
`_seed_pagination_stress_data.py` — строго по PK из манифеста
`_pagination_seed_manifest.json`, без паттерн-матчинга по именам/тексту.
Это исключает риск случайно задеть реальные "боевые" данные с похожими
названиями.

Порядок удаления — "дети раньше родителей", чтобы не зависеть от того,
CASCADE там или SET_NULL:
    variant -> question -> result -> selfresult -> selfuser ->
    selfquestion -> helper_question_variants -> helper_test_variants ->
    helper_test_questions -> quiz_test -> helper_test_results -> user ->
    helper_users_results -> selfctg -> helper_selfctg_selfquestions ->
    helper_selfctg_selfusers -> potok -> helper_potok_quiz -> subject ->
    helper_subject_quiz

Если манифеста нет — скрипт ничего не делает и сообщает об этом (не
падает, не пытается угадать, что удалять).

Запуск: python _cleanup_pagination_stress_data.py [--yes]
    --yes  пропустить интерактивное подтверждение
"""
import json
import os
import sys

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "src.settings")
import django

django.setup()

from django.db import transaction

from core.models import Potok, Question, Result, Subject, Test, User, Variant
from core.models.self import SelfCtg, SelfQuestion, SelfResult, SelfUser

MANIFEST_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_pagination_seed_manifest.json")

# (ключ_в_манифесте, Модель) — порядок важен (см. docstring).
DELETE_ORDER = [
    ("variant", Variant),
    ("question", Question),
    ("result", Result),
    ("selfresult", SelfResult),
    ("selfuser", SelfUser),
    ("selfquestion", SelfQuestion),
    ("helper_question_variants", Question),
    ("helper_test_variants", Test),
    ("helper_test_questions", Test),
    ("quiz_test", Test),
    ("helper_test_results", Test),
    ("user", User),
    ("helper_users_results", User),
    ("selfctg", SelfCtg),
    ("helper_selfctg_selfquestions", SelfCtg),
    ("helper_selfctg_selfusers", SelfCtg),
    ("potok", Potok),
    ("helper_potok_quiz", Potok),
    ("subject", Subject),
    ("helper_subject_quiz", Subject),
]


def main():
    if not os.path.exists(MANIFEST_PATH):
        print(f"Манифест не найден: {MANIFEST_PATH}")
        print("Нечего удалять (либо сид ещё не запускался, либо манифест уже был убран после чистки).")
        return

    with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    run_tag = manifest.get("_run_tag", "?")
    prefix = manifest.get("_prefix", "?")

    total_planned = sum(len(v) for k, v in manifest.items() if isinstance(v, list))
    print(f"Манифест: run_tag={run_tag}, префикс={prefix!r}")
    print(f"К удалению запланировано {total_planned} строк по {len(DELETE_ORDER)} ключам.")

    if "--yes" not in sys.argv:
        answer = input("Продолжить удаление? [y/N]: ").strip().lower()
        if answer != "y":
            print("Отменено пользователем.")
            return

    deleted_total = 0
    missing_total = 0

    with transaction.atomic():
        for key, model in DELETE_ORDER:
            ids = manifest.get(key, [])
            if not ids:
                continue
            qs = model.objects.filter(pk__in=ids)
            found = qs.count()
            deleted, _ = qs.delete()
            missing = len(ids) - found
            deleted_total += deleted
            missing_total += missing
            print(f"  {key:32s} -> в манифесте {len(ids):3d}, найдено {found:3d}, удалено объектов (с каскадами) {deleted:4d}"
                  + (f"  [!] {missing} уже отсутствовали" if missing else ""))

    os.remove(MANIFEST_PATH)
    print()
    print(f"Готово. Суммарно удалено объектов (считая каскады FK): {deleted_total}")
    if missing_total:
        print(f"Строк из манифеста уже не было в БД на момент чистки: {missing_total} (не ошибка — возможно, удалены вручную ранее).")
    print(f"Манифест {MANIFEST_PATH} удалён.")


if __name__ == "__main__":
    main()