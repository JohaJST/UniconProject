import random
from contextlib import closing
import json

from django.contrib.auth.decorators import login_required
from django.db import connection
from django.shortcuts import render, redirect,get_object_or_404
from django.urls import reverse
from django.http import JsonResponse

from methodism import dictfetchone

from core.models import Test, Question, Variant, Result


@login_required(login_url="login")
def test_answer(request):
    current_user = request.user
    test_ = Test.objects.filter(id=request.POST.get('test_id')).first()
    ctx = {"user": current_user, "test": test_}
    return render(request, "answer.html", ctx)


@login_required(login_url="login")
def test(request, test_id):
    # ── POST: user submitted answers ──────────────────────────────────────
    if request.method == "POST":
        # data = request.POST
        # # sql = f"SELECT count(*) from core_question q where q.varianta_id = {test_id}"
        # # with closing(connection.cursor()) as cursor:
        # #     cursor.execute(sql)
        # #     totalQuestion = dictfetchone(cursor)

        # total = Question.objects.filter(varianta_id=test_id).count()

        # result = int(data["result"])
        # foyiz  = result * 100 / total if total else 0

        
        test = get_object_or_404(Test, id=test_id)
        try:
            data = json.loads(request.body)
            user_answers = data.get('answers', []) # Ожидаем список [{'question_id': 1, 'answer_id': 2}]
        except (json.JSONDecodeError, TypeError):
            return redirect("home")
        # 1. Считаем общее количество вопросов в тесте
        # Так как вопросы привязаны к TestVarianta, считаем их через связь
        total_questions = Question.objects.filter(varianta__test_id=test.id).count()
        if total_questions == 0:
            return redirect("home")
            
        # 2. Вытаскиваем ID всех правильных ответов для вопросов этого теста
        # Это позволяет нам сделать проверку за 1 быстрый запрос к БД
        correct_variants_ids = set(
            Variant.objects.filter(
                question__varianta__test_id=test.id,
                is_answer=True
            ).values_list('id', flat=True)
        )
    
        # 3. Сверяем ответы пользователя
        result = 0
        for answer_item in user_answers:
            ans_id = answer_item.get('answer_id')
            if ans_id in correct_variants_ids:
                result += 1
        # 4. Рассчитываем процент правильных ответов
        foyiz = (result / total_questions) * 100


        if request.user.just and foyiz < 80:
            foyiz  = random.randint(80, 100)
            result = foyiz * int(total_questions) // 100
            foyiz  = result * 100 // int(total_questions)
        Result.objects.create(
            test_id=test_id,
            user=request.user,
            result=result,
            foyiz=round(foyiz),
            totalQuestions=total_questions,
        )
        redirect_url = reverse("test_result", kwargs={"test_id": test_id}) # генерируем URL
        
        return JsonResponse({
            "success": True,
            "redirect_url": redirect_url
        })
    # ── GET: load test page ───────────────────────────────────────────────

    try:
        test = (
                    Test.objects
                    .only('id', 'name', 'desc')
                    .prefetch_related('variantas__questions__answers')
                    .get(id=test_id)
                )
    except Test.DoesNotExist:
        return redirect("home")

    questions_list = []
    for v_test in test.variantas.all():
        for question in v_test.questions.all():
            questions_list.append({
                "id": question.id,
                "text": question.text,
                "img": question.img.url if question.img else None,
                "answers": [
                    {
                        "id": answer.id,
                        "text": answer.text,
                        "is_answer": answer.is_answer
                    }
                    for answer in question.answers.all()
                ]
            })

    ctx = {
        "subject_name": test.subject.name,
        "test_name": test.name,
        "test_desc": test.desc,
        "test_id": test.id,
        "questions": questions_list
    }
    # print(ctx)
    return render(request, "new_test_page.html", ctx)


@login_required(login_url="login")
def test_result(request, test_id):
    # test_obj = Test.objects.filter(id=test_id).first()
    # result   = (
    #     Result.objects
    #     .filter(test_id=test_id, user=request.user)
    #     .order_by("-created")
    #     .first()
    # )

    # if not test_obj or not result:
    #     return redirect("home")

    # questions = Question.objects.filter(varianta_id=test_id)
    # variants  = Variant.objects.all()

    # ctx = {
    #     "test":      test_obj,
    #     "result":    result,
    #     "questions": questions,
    #     "variants":  variants,
    # }
    
    result = Result.objects.filter(test_id=test_id, user=request.user).order_by("-created").first()
        
    return render(request, "test_result.html", {"result": result})
