from django.db.models import Count
from django.http import JsonResponse
from django.shortcuts import render

from core.models import About, Courses, News, Partners, Teachers, Test, SelfQuestion
import random
from core.models.self import SelfQuestion, SelfCtg

def about(request):
    # singleton-паттерн: одна запись About описывает всю страницу "О нас".
    # first() безопасно вернёт None, если запись ещё не создана в админке —
    # шаблон обязан обрабатывать about is None без 500 (см. templates/about.html).
    about_obj = About.objects.first()

    courses = Courses.objects.all()
    teachers = Teachers.objects.all()
    news = News.objects.all().order_by('-date')

    # Блок партнёров управляется флагом About.partners — если about_obj
    # отсутствует или флаг снят, секция должна рендериться пустой.
    partners = (
        Partners.objects.all()
        if (about_obj and about_obj.partners)
        else Partners.objects.none()
    )

    ctx = {
        "about": about_obj,
        "courses": courses,
        "teachers": teachers,
        "news": news,
        "partners": partners,
    }
    return render(request, "about.html", ctx)


def self(request):
    return render(request, "module 3 test/self.html")


def self_check(request):
    """
    Self-Check тест.

    ХОТФИК/ФИЧА: раньше сюда сразу подставлялось 2 случайных вопроса из
    ВСЕХ категорий разом. Теперь пользователь сперва выбирает категорию
    (SelfCtg) на клиенте, и только после выбора сюда же летит AJAX-запрос
    с ?ctg=<id> — тем же самым URL 'self_check' (core/urls.py — no-touch
    zone, поэтому НЕ заводим отдельный роут, а разруливаем через query-
    параметр прямо в этом view).

    GET  (без ?ctg)  -> обычный HTML: форма ФИО + список категорий.
    GET  ?ctg=<id>   -> JsonResponse: до 20 случайных вопросов ИМЕННО этой
                        категории с перемешанными вариантами ответов —
                        та же логика рандомизации, что была раньше
                        (order_by('?') + random.shuffle), просто теперь
                        она масштабируется на категорию, а не на всю таблицу
                        (быстрее: меньше строк до сортировки RANDOM()).
    """
    ctg_id = request.GET.get('ctg')
    if ctg_id is not None:
        return _self_check_questions_json(ctg_id)

    # Только непустые категории — нет смысла показывать пользователю
    # категорию, в которой нет ни одного вопроса.
    ctgs = (
        SelfCtg.objects
        .annotate(question_count=Count('selfquestion'))
        .filter(question_count__gt=0)
        .order_by('name_uz')
    )
    print(ctgs)
    # print(request.GET)
    # print(1)
    return render(request, 'module 3 test/test.html', {
        'ctgs': ctgs,
    })


def _self_check_questions_json(ctg_id):
    """
    Возвращает до 20 случайных вопросов категории ``ctg_id`` вместе
    с перемешанными вариантами ответов, в формате, который напрямую
    скармливается JS-массиву ``questions`` в module3test/script.js
    (см. showQuetions/optionSelected — они не тронуты и продолжают
    работать с этим же форматом объектов).
    """
    if not str(ctg_id).isdigit():
        return JsonResponse({"ok": False, "error": "invalid_ctg"}, status=400)

    ctg = SelfCtg.objects.filter(id=int(ctg_id)).first()
    if ctg is None:
        return JsonResponse({"ok": False, "error": "not_found"}, status=404)

    # Фильтр по категории ДО случайной сортировки — меньше строк для
    # ORDER BY RANDOM(), поэтому быстрее, чем прежний вариант без фильтра.
    random_questions = list(
        SelfQuestion.objects
        .filter(ctg=ctg)
        .prefetch_related('selfanswer_set')
        .order_by('?')[:20]
    )

    data = []
    for q in random_questions:
        answers = list(q.selfanswer_set.all())
        random.shuffle(answers)
        correct = next((a for a in answers if a.is_correct), None)

        data.append({
            "numb": q.id,
            "question": q.text,
            "img": q.img.url if q.img else None,
            "options": [
                {"text": a.text, "img": a.img.url if a.img else None}
                for a in answers
            ],
            # answer сопоставляется по тексту в script.js (optionSelected) —
            # сохраняем тот же контракт, что был раньше.
            "answer": correct.text if correct else None,
        })

    return JsonResponse({"ok": True, "questions": data})