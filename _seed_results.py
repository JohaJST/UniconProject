# -*- coding: utf-8 -*-
"""
Одноразовый генератор тестовых данных: 50 случайных Result для проверки
дашборда, привязанных к ТЕКУЩИМ потокам, пользователям и тестам.

Правила реалистичности:
  - студент получает результат только по тесту СВОЕГО потока;
  - result (верных ответов) <= числу вопросов теста, foyiz = %;
  - time — случайное время прохождения в секундах;
  - created — случайная дата за последние 30 дней;
  - у пользователей с результатами выставляется is_result=True.
"""
import os
import random

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "src.settings")
import django

django.setup()

from datetime import timedelta

from django.utils import timezone

from core.models import Question, Result, Test, User
from core.models.auth import Role

rng = random.Random()

students = list(
    User.objects.filter(role=Role.STUDENT, is_active=True).exclude(potok__isnull=True)
)
print("Студенты:", [(u.id, u.username, u.potok_id) for u in students])

test_map = {}
for t in Test.objects.all():
    test_map[t.id] = {
        "potok": t.potok_id,
        "total": Question.objects.filter(test_id=t.id).count(),
    }
print("Тесты:", {tid: v for tid, v in test_map.items()})

before = Result.objects.count()
created = 0
for _ in range(50):
    u = rng.choice(students)
    candidates = [
        tid for tid, info in test_map.items()
        if info["potok"] == u.potok_id and info["total"] > 0
    ]
    if not candidates:
        continue

    tid = rng.choice(candidates)
    total = test_map[tid]["total"]
    correct = rng.randint(0, total)
    foyiz = round(correct / total * 100)

    r = Result.objects.create(
        user=u,
        test_id=tid,
        result=correct,
        foyiz=foyiz,
        totalQuestions=total,
        time=rng.randint(45, 1800),
    )

    # auto_now_add не даёт задать created при create() — перекрываем через update().
    created_at = timezone.now() - timedelta(
        days=rng.randint(0, 29),
        hours=rng.randint(0, 23),
        minutes=rng.randint(0, 59),
    )
    Result.objects.filter(pk=r.pk).update(created=created_at)
    created += 1

# Флаг "у пользователя есть результат" — как это делает takeTest.py.
users_with_results = User.objects.filter(results__isnull=False).distinct()
users_with_results.update(is_result=True)

print()
print(f"Создано: {created} результатов (было {before}, стало {Result.objects.count()})")
print("Средний балл по всем:", round(Result.objects.aggregate(
    avg=__import__("django.db.models", fromlist=["Avg"]).Avg("foyiz"))["avg"] or 0, 1))
