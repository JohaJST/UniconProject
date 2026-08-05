import re
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect
from core.models import ClassRooms, Question, Subject, Test, TestClassRoom, TestVarianta, Variant


@login_required(login_url="login")
def create_test(request):
    if request.method != 'POST':
        return redirect("dashboard")

    subject = Subject.objects.get(id=request.POST.get('subject'))

    test = Test.objects.create(
        name_uz=request.POST.get('test_name_uz') or request.POST.get('test_name', ''),
        name_ru=request.POST.get('test_name_ru', ''),
        name_en=request.POST.get('test_name_en', ''),
        desc_uz=request.POST.get('test_desc_uz') or request.POST.get('test_desc', ''),
        desc_ru=request.POST.get('test_desc_ru', ''),
        desc_en=request.POST.get('test_desc_en', ''),
        subject=subject,
    )
    test_varianta = TestVarianta.objects.create(test=test, variant=1)

    idx = 1
    while f'classroom_{idx}' in request.POST:
        classroom_id = request.POST.get(f'classroom_{idx}')
        if classroom_id:
            TestClassRoom.objects.get_or_create(test=test, classroom_id=int(classroom_id))
        idx += 1

    question_indexes = sorted({
        int(m.group(1)) for key in request.POST
        if (m := re.fullmatch(r'question_(\d+)', key))
    })
    for q_idx in question_indexes:
        question = Question.objects.create(
            text_uz=request.POST.get(f'question_{q_idx}_uz') or request.POST[f'question_{q_idx}'],
            text_ru=request.POST.get(f'question_{q_idx}_ru', ''),
            text_en=request.POST.get(f'question_{q_idx}_en', ''),
            img=request.FILES.get(f'question_{q_idx}_image'),
            varianta=test_varianta,
        )
        variant_indexes = sorted({
            int(m.group(1)) for key in request.POST
            if (m := re.fullmatch(rf'variant_{q_idx}_(\d+)', key))
        })
        for v_idx in variant_indexes:
            Variant.objects.create(
                text_uz=request.POST.get(f'variant_{q_idx}_{v_idx}_uz') or request.POST[f'variant_{q_idx}_{v_idx}'],
                text_ru=request.POST.get(f'variant_{q_idx}_{v_idx}_ru', ''),
                text_en=request.POST.get(f'variant_{q_idx}_{v_idx}_en', ''),
                is_answer=f'answer_{q_idx}_{v_idx}' in request.POST,
                question=question,
            )

    return redirect('dashboard')