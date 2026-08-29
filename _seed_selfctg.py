# -*- coding: utf-8 -*-
"""
Одноразовый сид: категории SelfCtg (с переводами uz/ru/en) + привязка
существующих SelfQuestion из БД к категориям.

Идемпотентен: категории создаются только если их ещё нет (по name_uz),
вопросы привязываются только если у них ctg IS NULL.
"""
import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "src.settings")
import django

django.setup()

from core.models.self import SelfCtg, SelfQuestion

# (uz, ru, en, [question ids])
CATEGORIES = [
    ("Umumiy asoslar",
     "Общие основы",
     "General basics",
     [1, 2, 8, 37]),
    ("Parol va autentifikatsiya",
     "Пароли и аутентификация",
     "Passwords and authentication",
     [4, 5, 6, 9, 11, 17, 24, 31, 36]),
    ("Fishing va ijtimoiy injeneriya",
     "Фишинг и социальная инженерия",
     "Phishing and social engineering",
     [3, 7, 10, 13, 18, 23, 28, 32, 34]),
    ("Zararli dasturlar",
     "Вредоносное ПО",
     "Malware",
     [12, 14, 16, 25, 30]),
    ("Tarmoq xavfsizligi",
     "Сетевая безопасность",
     "Network security",
     [15, 19, 21, 26, 29]),
    ("Ma'lumotlar maxfiyligi",
     "Конфиденциальность данных",
     "Data privacy",
     [20, 22, 27, 33, 35]),
]

created = 0
ctg_map = {}
for uz, ru, en, qids in CATEGORIES:
    ctg = SelfCtg.objects.filter(name_uz=uz).first()
    if ctg is None:
        ctg = SelfCtg.objects.create(name_uz=uz, name_ru=ru, name_en=en)
        created += 1
        print(f"[+] Категория создана: {uz} (id={ctg.id})")
    else:
        # Дозаполняем переводы, если категория уже была создана без них
        changed = False
        for field, val in (("name_uz", uz), ("name_ru", ru), ("name_en", en)):
            if not getattr(ctg, field):
                setattr(ctg, field, val)
                changed = True
        if changed:
            ctg.save()
        print(f"[=] Категория уже была: {uz} (id={ctg.id})")
    ctg_map[uz] = ctg

assigned = 0
skipped = 0
for uz, ru, en, qids in CATEGORIES:
    ctg = ctg_map[uz]
    for qid in qids:
        q = SelfQuestion.objects.filter(id=qid).first()
        if q is None:
            print(f"[!] Вопроса с id={qid} нет в БД — пропущен")
            continue
        if q.ctg_id is not None:
            print(f"[~] Вопрос {qid} уже имеет категорию (id={q.ctg_id}) — пропущен")
            skipped += 1
            continue
        q.ctg = ctg
        q.save(update_fields=["ctg"])
        assigned += 1

unassigned = SelfQuestion.objects.filter(ctg__isnull=True).count()
print()
print(f"Итог: создано категорий: {created}, привязано вопросов: {assigned}, "
      f"пропущено (уже с категорией): {skipped}, осталось без категории: {unassigned}")
for ctg in SelfCtg.objects.all():
    print(f"  {ctg.name_uz}: {ctg.selfquestion_set.count()} вопросов")
