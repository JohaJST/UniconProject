from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from core.models import (
    ClassRooms,
    Question,
    Subject,
    Test,
    TestClassRoom,
    TestVarianta,
    Variant,
)


# @login_required(login_url="login")
# def new_test(request):
#     return render(request, "pages/dashboard/new.html", {
#         "classrooms": ClassRooms.objects.all(),
#         "subjects": Subject.objects.all(),
#     })


@login_required(login_url="login")
def create_test(request):
    if request.method != 'POST':
        return redirect("dashboard")

    subject = Subject.objects.get(id=request.POST.get('subject'))
    print(request.POST)
    test = Test.objects.create(
        name_uz=request.POST.get('test_name'),
        subject=subject,
    )
    
    # Опциональные переводы названия/описания теста (RU/EN).
    # test_name_uz покрывается основным полем name= выше (default language).
    test_update_fields = []
    if request.POST.get('test_name_ru'):
        test.name_ru = request.POST.get('test_name_ru')
        test_update_fields.append('name_ru')
    if request.POST.get('test_name_en'):
        test.name_en = request.POST.get('test_name_en')
        test_update_fields.append('name_en')
    if test_update_fields:
        test.save(update_fields=test_update_fields)
    
    # Создаём первый (и единственный на данном этапе) вариант теста.
    test_varianta = TestVarianta.objects.create(test=test, variant=1)

    # Привязываем классы к тесту: перебираем ключи classroom_1, classroom_2, ...
    # без жёсткого ограничения в 4 класса.
    idx = 1
    while f'classroom_{idx}' in request.POST:
        classroom_id = request.POST.get(f'classroom_{idx}')
        if classroom_id:
            TestClassRoom.objects.get_or_create(test=test, classroom_id=int(classroom_id))
        idx += 1

    # Создаём вопросы и варианты ответов для варианта теста.
    q_idx = 1
    while f'question_{q_idx}' in request.POST:
        question = Question.objects.create(
            text_uz=request.POST[f'question_{q_idx}'],
            img=request.POST.get(f'question_{q_idx}_image') if f'question_{q_idx}_image' in request.POST else None,
            varianta=test_varianta,
        )
        # Опциональные переводы текста вопроса (RU/EN).
        question_update_fields = []
        if request.POST.get(f'question_{q_idx}_ru'):
            question.text_ru = request.POST.get(f'question_{q_idx}_ru')
            question_update_fields.append('text_ru')
        if request.POST.get(f'question_{q_idx}_en'):
            question.text_en = request.POST.get(f'question_{q_idx}_en')
            question_update_fields.append('text_en')
        if question_update_fields:
            question.save(update_fields=question_update_fields)
        
        v_idx = 1
        while f'variant_{q_idx}_{v_idx}' in request.POST:
            variant = Variant.objects.create(
                text_uz=request.POST[f'variant_{q_idx}_{v_idx}'],
                is_answer=f'answer_{q_idx}_{v_idx}' in request.POST,
                question=question,
            )
            v_idx += 1
            variant_update_fields = []
            if request.POST.get(f'variant_{q_idx}_{v_idx}_ru'):
                variant.text_ru = request.POST.get(f'variant_{q_idx}_{v_idx}_ru')
                variant_update_fields.append('text_ru')
            if request.POST.get(f'variant_{q_idx}_{v_idx}_en'):
                variant.text_en = request.POST.get(f'variant_{q_idx}_{v_idx}_en')
                variant_update_fields.append('text_en')
            if variant_update_fields:
                variant.save(update_fields=variant_update_fields)
        q_idx += 1

    return redirect('dashboard')
