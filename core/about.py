import random
import re

from django.core.files.storage import default_storage
from django.db.models import Count
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.template import RequestContext, Template
from django.utils import translation

from core.ai_presenter import VALID_LANGS, get_or_build_presentation
from core.models import About, Courses, News, Partners, SelfQuestion, Teachers, Test
from core.models.self import SelfCtg, SelfQuestion, SelfResult, SelfStudy, SelfUser

_SAFE_HASH_RE = re.compile(r"^[a-f0-9]{16}$")
_SAFE_FILE_RE = re.compile(r"^scene_\d+_[a-z0-9_-]+\.mp3$")


def about(request):
    # 1. Безопасная раздача сгенерированного MP3 (резервный канал, если /media/ не настроен в urls.py)
    if request.GET.get("ai_presenter_audio") == "1":
        lang = str(request.GET.get("lang") or "uz").strip().lower()[:2]
        state_hash = str(request.GET.get("hash") or "").strip().lower()
        filename = str(request.GET.get("file") or "").strip()

        if (
            lang not in VALID_LANGS
            or not _SAFE_HASH_RE.fullmatch(state_hash)
            or not _SAFE_FILE_RE.fullmatch(filename)
        ):
            raise Http404("Invalid audio path")

        rel_path = f"ai_presenter/{lang}/{state_hash}/{filename}"
        if not default_storage.exists(rel_path):
            raise Http404("Audio not found")

        with default_storage.open(rel_path, "rb") as audio_file:
            audio_bytes = audio_file.read()

        response = HttpResponse(audio_bytes, content_type="audio/mpeg")
        response["Accept-Ranges"] = "bytes"
        response["Cache-Control"] = "public, max-age=604800"
        return response

    # 2. Отдача JSON-манифеста голосового гида AI Presenter
    if request.GET.get("ai_presenter") == "1":
        raw_lang = request.GET.get("lang") or translation.get_language() or "uz"
        lang = str(raw_lang).strip().lower()[:2]
        if lang not in VALID_LANGS:
            lang = "uz"

        manifest = get_or_build_presentation(lang=lang)
        return JsonResponse({
            "ok": True,
            "lang": lang,
            "hash": manifest["hash"],
            "scenes": manifest["scenes"],
        })

    # singleton-паттерн: одна запись About описывает всю страницу "О нас".
    # first() безопасно вернёт None, если запись ещё не создана в админке —
    # шаблон обязан обрабатывать about is None без 500 (см. templates/about.html).
    about_obj = About.objects.filter(id=1).first()

    courses = Courses.objects.all()
    teachers = Teachers.objects.all()
    news = News.objects.annotate(gallery_count=Count("images")).order_by('-date')

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
    selfstudy = SelfStudy.objects.filter(id=1).first()
    rendered_html = ""

    if selfstudy and selfstudy.html_text:
        template = Template(selfstudy.html_text)
        rendered_html = template.render(RequestContext(request))

    return render(request, "module 3 test/self.html", {
        "selfstudy": selfstudy,
        "rendered_html": rendered_html,
    })


def self_check(request):
    if request.method == "POST":
        data = request.POST
        first_name = (data.get("first_name") or "").strip()[:255]
        last_name = (data.get("last_name") or "").strip()[:255]

        raw_ctg = str(data.get("ctg") or "").strip()
        ctg = (
            SelfCtg.objects.filter(id=int(raw_ctg)).first()
            if raw_ctg.isdigit() and len(raw_ctg) < 10 else None
        )

        try:
            score = int(data.get("score", ""))
            total = int(data.get("total", ""))
        except (TypeError, ValueError):
            return JsonResponse({"ok": False, "error": "invalid_data"}, status=400)

        if not first_name or not last_name or ctg is None or not (0 < total <= 100) or not (0 <= score <= total):
            return JsonResponse({"ok": False, "error": "invalid_data"}, status=400)

        user = (
            SelfUser.objects.filter(first_name=first_name, last_name=last_name).first()
            or SelfUser.objects.create(first_name=first_name, last_name=last_name)
        )
        SelfResult.objects.create(
            user=user, ctg=ctg,
            score=score, foiz=score / total * 100,   # процент считает сервер, а не клиент
            totalQuestions=total,
        )
        return JsonResponse({'message': 'success'})

    ctg_id = request.GET.get('ctg')
    if ctg_id is not None:
        return _self_check_questions_json(ctg_id)

    ctgs = (
        SelfCtg.objects
        .annotate(question_count=Count('selfquestion'))
        .filter(question_count__gt=0)
        .order_by('name_uz')
    )
    return render(request, 'module 3 test/test.html', {
        'ctgs': ctgs,
    })


def _self_check_questions_json(ctg_id):
    if not str(ctg_id).isdigit():
        return JsonResponse({"ok": False, "error": "invalid_ctg"}, status=400)

    ctg = SelfCtg.objects.filter(id=int(ctg_id)).first()
    if ctg is None:
        return JsonResponse({"ok": False, "error": "not_found"}, status=404)

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
            "answer": correct.text if correct else None,
        })

    return JsonResponse({"ok": True, "questions": data})


def news_page(request, pk=None):
    """
    Публичная страница новостей: слева список всех новостей, справа выбранная
    новость (3D-галерея + описание) и переходы «новее / старше».
    Без pk показывается самая свежая.
    """
    base_qs = News.objects.prefetch_related("images")

    if pk is None:
        current = base_qs.order_by("-date", "-id").first()
    else:
        current = get_object_or_404(base_qs, pk=pk)

    # Список для левой колонки (свежие сверху), ограничен, чтобы страница не тяжелела.
    all_news = list(
        News.objects
        .annotate(gallery_count=Count("images"))
        .order_by("-date", "-id")[:40]
    )

    if current is None:
        return render(request, "news.html", {
            "news_item": None, "slides": [], "all_news": all_news,
            "newer_item": None, "older_item": None,
        })

    slides = []
    if current.photo:
        slides.append({"url": current.photo.url})
    slides.extend({"url": img.image.url} for img in current.images.all() if img.image)

    # Соседние новости для навигации «новее / старше».
    newer_item = older_item = None
    for i, item in enumerate(all_news):
        if item.pk == current.pk:
            newer_item = all_news[i - 1] if i > 0 else None
            older_item = all_news[i + 1] if i + 1 < len(all_news) else None
            break

    return render(request, "news.html", {
        "news_item": current,
        "slides": slides,
        "all_news": all_news,
        "newer_item": newer_item,
        "older_item": older_item,
    })