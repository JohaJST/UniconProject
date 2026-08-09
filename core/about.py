from django.shortcuts import render

from core.models import About, Courses, News, Partners, Teachers, Test


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
    if request.method == "POST":
        print(request.POST)
        
    test = (
                Test.objects
                .only('id', 'name', 'desc')
                .prefetch_related('variantas__questions__answers')
                .get(id=10)
            )

    questions_list = []
    for v_test in test.variantas.all():
        for question in v_test.questions.all():
            questions_list.append({
                "id": question.id,
                "text": question.text,
                "img": question.img.url if question.img else None,
                # "answer": question.answers.text if question.answers.is_answer else None,
                "answers": [
                    {
                        "id": answer.id,
                        "text": answer.text,
                        "is_correct": answer.is_answer,
                        # "img": answer.img.url if answer.img else None,
                    }
                    for answer in question.answers.all()
                ]
            })
    
    ctx = {
        "questions": questions_list
    }
    print(ctx)
    return render(request, "module 3 test/test.html", ctx)
    
    