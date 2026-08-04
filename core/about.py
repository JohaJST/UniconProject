from django.shortcuts import render

from core.models import About, Courses, News, Partners, Teachers


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
    return render(request, "self.html")


def self_check(request):
    return render(request, "self_check.html")