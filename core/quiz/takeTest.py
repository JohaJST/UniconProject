import random
import json

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse

from core.models import Test, Question, Variant, Result


@login_required(login_url="login")
def test_answer(request):
    current_user = request.user
    test_ = Test.objects.filter(id=request.POST.get('test_id')).first()
    ctx = {"user": current_user, "test": test_}
    return render(request, "answer.html", ctx)


@login_required(login_url="login")
def test(request, test_id):
    # ── POST: пользователь отправил ответы ────────────────────────────────
    if request.method == "POST":
        test = get_object_or_404(Test, id=test_id)

        # Те же ограничения, что и на GET: профиль должен быть заполнен,
        # тест — принадлежать потоку студента, и повторное прохождение
        # запрещено (не даём наплодить дублирующихся Result).
        if not request.user.position or not request.user.company_name:
            return JsonResponse({"success": False, "error": "profile_incomplete"}, status=403)

        if test.potok_id and test.potok_id != request.user.potok_id:
            return JsonResponse({"success": False, "error": "not_allowed"}, status=403)

        if Result.objects.filter(test_id=test_id, user=request.user).exists():
            return JsonResponse({"success": False, "error": "already_done"}, status=409)

        try:
            data = json.loads(request.body)
            user_answers = data.get('answers', [])
        except (json.JSONDecodeError, TypeError):
            return redirect("home")

        # Вопросы теперь привязаны напрямую к Test (без TestVarianta).
        total_questions = Question.objects.filter(test_id=test.id).count()
        if total_questions == 0:
            return redirect("home")

        correct_variants_ids = set(
            Variant.objects.filter(
                question__test_id=test.id,
                is_answer=True,
            ).values_list('id', flat=True)
        )

        result = 0
        for answer_item in user_answers:
            ans_id = answer_item.get('answer_id')
            if ans_id in correct_variants_ids:
                result += 1

        foyiz = (result / total_questions) * 100

        Result.objects.create(
            test_id=test_id,
            user=request.user,
            result=result,
            foyiz=round(foyiz),
            totalQuestions=total_questions,
        )
        redirect_url = reverse("test_result", kwargs={"test_id": test_id})

        return JsonResponse({
            "success": True,
            "redirect_url": redirect_url
        })

    # ── GET: страница теста ────────────────────────────────────────────────
    if not request.user.position or not request.user.company_name:
        return redirect("required")

    if Result.objects.filter(test_id=test_id, user=request.user).exists():
        return redirect(reverse("test_result", kwargs={"test_id": test_id}))

    try:
        test = (
            Test.objects
            .prefetch_related('questions__answers')
            .get(id=test_id)
        )
    except Test.DoesNotExist:
        return redirect("home")

    # Тест доступен только студентам своего потока.
    if test.potok_id and test.potok_id != request.user.potok_id:
        return redirect("home")

    questions_list = []
    for question in test.questions.all():
        questions_list.append({
            "id": question.id,
            "text": question.text,
            "img": question.img.url if question.img else None,
            "answers": [
                {
                    "id": answer.id,
                    "text": answer.text,
                    # is_answer НЕ передаём клиенту — иначе правильные
                    # ответы видны в исходниках страницы до сдачи теста.
                }
                for answer in question.answers.all()
            ]
        })

    ctx = {
        "subject_name": test.subject.name if test.subject else "",
        "test_name": str(test),
        "test_desc": "",
        "test_id": test.id,
        "questions": questions_list
    }
    return render(request, "new_test_page.html", ctx)


@login_required(login_url="login")
def test_result(request, test_id):
    result = Result.objects.filter(test_id=test_id, user=request.user).order_by("-created").first()
    return render(request, "test_result.html", {"result": result})
