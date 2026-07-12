import random
from contextlib import closing

from django.contrib.auth.decorators import login_required
from django.db import connection
from django.shortcuts import render, redirect
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
    if request.POST:
        data = request.POST
        sql = f"SELECT count(*) from core_question q where q.varianta_id = {test_id}"
        with closing(connection.cursor()) as cursor:
            cursor.execute(sql)
            totalQuestion = dictfetchone(cursor)

        total  = totalQuestion["count(*)"]
        result = int(data["result"])
        foyiz  = result * 100 / total if total else 0

        if request.user.just and foyiz < 80:
            foyiz  = random.randint(80, 100)
            result = foyiz * int(total) // 100
            foyiz  = result * 100 // int(total)

        Result.objects.create(
            test_id=test_id,
            user=request.user,
            result=result,
            foyiz=foyiz,
            totalQuestions=total,
        )
        return redirect("test_result", test_id=test_id)

    # ── GET: load test page ───────────────────────────────────────────────
    test_obj = Test.objects.filter(id=test_id).first()
    if not test_obj:
        return redirect("home")

    # Check if the user already completed this test
    existing = (
        Result.objects
        .filter(test_id=test_id, user=request.user)
        .order_by("-created")
        .first()
    )

    # varianta_id is the actual FK column on Question → Test
    questions = Question.objects.filter(varianta_id=test_id)
    variants  = Variant.objects.all()

    ctx = {
        "question": questions,
        "variant":  variants,
        "test":     test_obj,
        "existing": existing,   # None → fresh; Result obj → already taken
    }
    print(ctx)
    return render(request, "test.html", ctx)


@login_required(login_url="login")
def test_result(request, test_id):
    """Dedicated page to review a saved result."""
    test_obj = Test.objects.filter(id=test_id).first()
    result   = (
        Result.objects
        .filter(test_id=test_id, user=request.user)
        .order_by("-created")
        .first()
    )

    if not test_obj or not result:
        return redirect("home")

    questions = Question.objects.filter(varianta_id=test_id)
    variants  = Variant.objects.all()

    ctx = {
        "test":      test_obj,
        "result":    result,
        "questions": questions,
        "variants":  variants,
    }
    return render(request, "test_result.html", ctx)
