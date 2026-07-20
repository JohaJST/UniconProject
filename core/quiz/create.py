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
    test = Test.objects.create(
        name=request.POST.get('test_name'),
        subject=subject,
    )

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
            text=request.POST[f'question_{q_idx}'],
            img=request.POST.get(f'question_{q_idx}_image') if f'question_{q_idx}_image' in request.POST else None,
            varianta=test_varianta,
        )
        v_idx = 1
        while f'variant_{q_idx}_{v_idx}' in request.POST:
            Variant.objects.create(
                text=request.POST[f'variant_{q_idx}_{v_idx}'],
                is_answer=f'answer_{q_idx}_{v_idx}' in request.POST,
                question=question,
            )
            v_idx += 1
        q_idx += 1

    return redirect('dashboard')
