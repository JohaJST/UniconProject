# -*- coding: utf-8 -*-
"""
qa_checklist.py — Финальный QA-прогон чек-листа дашборда.

Запуск: python qa_checklist.py
"""
import os
import sys
import time

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "src.settings")

import django

django.setup()

from django.db import connection
from django.test import Client
from django.urls import reverse

from core.models import (
    ClassRooms, ClassRoomsSubjects, Question, Result, Subject, Test,
    TestVarianta, User, Variant,
)
from core.models.auth import Role

RUN_TAG = str(int(time.time()))[-6:]
PASS, FAIL = [], []


def check(name, ok, detail=""):
    (PASS if ok else FAIL).append(name)
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))


def count_queries(fn):
    """Выполняет fn() и возвращает количество SQL-запросов (CaptureQueriesContext)."""
    from django.test.utils import CaptureQueriesContext
    with CaptureQueriesContext(connection) as ctx:
        result = fn()
    return len(ctx.captured_queries), result


class QAClient:
    def __init__(self, user_id, dashboard_pass=None):
        self.client = Client()
        r = self.client.post(reverse("login"), {"user": str(user_id)})
        assert r.status_code == 302, f"login failed: {r.status_code}"
        if dashboard_pass is not None and r.url == reverse("lock"):
            r = self.client.post(reverse("lock"), {"pass": dashboard_pass})
            assert r.status_code == 302 and r.url == reverse("dashboard"), "lock failed"

    def get(self, *a, **kw):
        return self.client.get(*a, **kw)

    def post(self, *a, **kw):
        return self.client.post(*a, **kw)


def cleanup_legacy():
    """Удаляет мусор от предыдущих QA-прогонов."""
    Subject.objects.filter(name_uz__startswith="QA").delete()
    ClassRooms.objects.filter(name__startswith="QA").delete()
    User.objects.filter(username__in=["qa_student", "qa_target"]).delete()


def main():
    cleanup_legacy()

    admin = User.objects.filter(role__lte=Role.ADMIN).exclude(username="JustUsername").first()
    student = User.objects.filter(role=Role.STUDENT, is_active=True).first()
    if not admin or not student:
        print("Need admin and student in DB"); sys.exit(1)

    subject = Subject.objects.first()
    classroom = ClassRooms.objects.first()
    test_obj = Test.objects.first()

    print("=" * 70)
    print("QA: login")
    print("=" * 70)
    qa = QAClient(admin.id, dashboard_pass="1")
    r = qa.get(reverse("dashboard"))
    check("GET /dashboard/ -> 200", r.status_code == 200, f"status={r.status_code}")

    print("=" * 70)
    print("QA 1: Subject create/view/edit")
    print("=" * 70)
    r = qa.get(reverse("action_no_pk", kwargs={"status": "create", "path": "subject"}))
    check("GET create subject -> 200", r.status_code == 200, f"status={r.status_code}")
    r = qa.post(reverse("action_no_pk", kwargs={"status": "create", "path": "subject"}), {
        "subject_name": f"QA Subj {RUN_TAG}",
        "subject_name_uz": f"QA Subj {RUN_TAG} UZ",
        "subject_name_ru": f"QA Subj {RUN_TAG} RU",
        "subject_name_en": f"QA Subj {RUN_TAG} EN",
        "classroom_1": str(classroom.id),
    })
    new_subject = Subject.objects.filter(name_uz=f"QA Subj {RUN_TAG} UZ").first()
    check("POST create subject -> redirect", r.status_code == 302 and new_subject is not None,
          f"status={r.status_code}, created={new_subject is not None}")
    check("Subject create filled 3 languages",
          bool(new_subject) and new_subject.name_uz == f"QA Subj {RUN_TAG} UZ"
          and new_subject.name_ru == f"QA Subj {RUN_TAG} RU"
          and new_subject.name_en == f"QA Subj {RUN_TAG} EN")
    check("Subject create linked classroom",
          bool(new_subject) and ClassRoomsSubjects.objects.filter(
              subject=new_subject, classroom=classroom).exists())

    nq, r = count_queries(lambda: qa.get(reverse(
        "action", kwargs={"status": "view", "path": "subject", "pk": new_subject.id})))
    check("GET view subject -> 200", r.status_code == 200, f"status={r.status_code}")
    check("view subject N+1 ok (<15 SQL)", 0 <= nq < 15, f"queries={nq}")

    old_test_count = Test.objects.filter(subject=new_subject).count()
    r = qa.post(reverse("action", kwargs={"status": "edit", "path": "subject", "pk": new_subject.id}), {
        "subject_name": "QA Edited", "subject_name_uz": "QA Edited UZ",
        "subject_name_ru": "QA Edited RU", "subject_name_en": "QA Edited EN",
    })
    new_subject.refresh_from_db()
    check("POST edit subject -> redirect to view", r.status_code == 302
          and r.url == reverse("action", kwargs={"status": "view", "path": "subject", "pk": new_subject.id}),
          f"status={r.status_code}")
    check("edit subject changed name", new_subject.name_uz == "QA Edited UZ")
    check("edit subject: unchecked checkbox unlinks classroom",
          not ClassRoomsSubjects.objects.filter(subject=new_subject, classroom=classroom).exists())
    check("edit subject kept old tests",
          Test.objects.filter(subject=new_subject).count() == old_test_count)

    print("=" * 70)
    print("QA 2: ClassRoom view/edit")
    print("=" * 70)
    new_class = ClassRooms.objects.create(name=f"QA Class {RUN_TAG}")
    User.objects.create_user(username=f"qa_student_{RUN_TAG}", password="x",
                             role=Role.STUDENT, classroom=new_class,
                             name="QA", last_name="Student")
    nq, r = count_queries(lambda: qa.get(reverse(
        "action", kwargs={"status": "view", "path": "classroom", "pk": new_class.id})))
    check("GET view classroom -> 200", r.status_code == 200, f"status={r.status_code}")
    check("view classroom N+1 ok (<20 SQL)", 0 <= nq < 20, f"queries={nq}")
    r = qa.post(reverse("action", kwargs={"status": "edit", "path": "classroom", "pk": new_class.id}),
                {"classroom_name": f"QA Class {RUN_TAG} R"})
    new_class.refresh_from_db()
    check("POST edit classroom -> redirect", r.status_code == 302)
    check("edit classroom changed only name",
          new_class.name == f"QA Class {RUN_TAG} R"
          and User.objects.filter(classroom=new_class).count() == 1)

    print("=" * 70)
    print("QA 3: User view/edit")
    print("=" * 70)
    target = User.objects.create_user(username=f"qa_target_{RUN_TAG}", password="oldpass123",
                                      role=Role.STUDENT, name="Target", last_name="User")
    nq, r = count_queries(lambda: qa.get(reverse(
        "action", kwargs={"status": "view", "path": "user", "pk": target.id})))
    check("GET view user -> 200", r.status_code == 200, f"status={r.status_code}")
    check("view user N+1 ok (<15 SQL)", 0 <= nq < 15, f"queries={nq}")
    old_hash = target.password
    r = qa.post(reverse("action", kwargs={"status": "edit", "path": "user", "pk": target.id}), {
        "first_name": "Target2", "last_name": "User2", "birthday": "2005-01-01",
        "phone": "+998901112233", "classroom": str(new_class.id), "role": str(Role.STUDENT),
        "lang": "ru", "password": "",
    })
    target.refresh_from_db()
    check("POST edit user -> redirect", r.status_code == 302)
    check("edit user changed data", target.name == "Target2" and target.phone == "+998901112233")
    check("empty password did NOT reset password", target.password == old_hash)
    r = qa.post(reverse("action", kwargs={"status": "edit", "path": "user", "pk": target.id}), {
        "first_name": "Target2", "last_name": "User2", "birthday": "2005-01-01",
        "phone": "+998901112233", "classroom": str(new_class.id), "role": str(Role.STUDENT),
        "lang": "ru", "password": "newpass456",
    })
    target.refresh_from_db()
    check("entered password changed password", target.check_password("newpass456"))

    print("=" * 70)
    print("QA 4: Quiz view/edit")
    print("=" * 70)
    if test_obj and test_obj.variantas.exists():
        nq, r = count_queries(lambda: qa.get(reverse(
            "action", kwargs={"status": "view", "path": "quiz", "pk": test_obj.id})))
        check("GET view quiz -> 200", r.status_code == 200, f"status={r.status_code}")
        check("view quiz N+1 ok (<20 SQL)", 0 <= nq < 20, f"queries={nq}")

        q1 = Question.objects.filter(varianta__test=test_obj).first()
        if q1:
            variants = list(q1.answers.all())
            if len(variants) >= 2:
                data = {"test_name": test_obj.name_uz, "subject": str(test_obj.subject_id)}
                for i, v in enumerate(variants):
                    data[f"variant_id_0_{i}"] = str(v.id)
                    data[f"variant_0_{i}"] = v.text_uz
                    data[f"variant_0_{i}_uz"] = v.text_uz
                    data[f"variant_0_{i}_ru"] = v.text_ru or v.text_uz
                    data[f"variant_0_{i}_en"] = v.text_en or v.text_uz
                    if v.is_answer:
                        data[f"answer_0_{i}"] = "1"
                data["question_id_0"] = str(q1.id)
                data["question_0"] = q1.text_uz
                data["question_0_uz"] = q1.text_uz
                data["question_0_ru"] = q1.text_ru or q1.text_uz
                data["question_0_en"] = q1.text_en or q1.text_uz

                vc_before = Variant.objects.count()
                r = qa.post(reverse("action", kwargs={"status": "edit", "path": "quiz", "pk": test_obj.id}), data)
                check("POST edit quiz -> redirect", r.status_code == 302, f"status={r.status_code}")
                check("edit quiz idempotent (no duplicates)", Variant.objects.count() == vc_before)

                other_q = Question.objects.filter(varianta__test=test_obj).exclude(pk=q1.id).first()
                if other_q and other_q.answers.exists():
                    other_v = other_q.answers.first()
                    data["variant_id_0_0"] = str(other_v.id)
                    r = qa.post(reverse("action", kwargs={"status": "edit", "path": "quiz", "pk": test_obj.id}), data)
                    check("edit quiz POST with foreign variant_id -> no 500", r.status_code in (200, 302, 400))
                    other_v.refresh_from_db()
                    check("IDOR: foreign variant not overwritten", other_v.question_id == other_q.id)
    else:
        print("  [SKIP] no tests with variants in DB")

    print("=" * 70)
    print("QA 5: Delete")
    print("=" * 70)
    for path, obj in [("subject", new_subject), ("classroom", new_class), ("user", target)]:
        r = qa.get(reverse("action", kwargs={"status": "delete", "path": path, "pk": obj.pk}))
        check(f"delete {path} -> redirect", r.status_code == 302, f"status={r.status_code}")

    print("=" * 70)
    print("QA 6: RBAC student on /action/")
    print("=" * 70)
    sqa = QAClient(student.id)
    for status, path in [("view", "subject"), ("edit", "subject"), ("delete", "subject"),
                          ("view", "quiz"), ("edit", "quiz")]:
        url = reverse("action", kwargs={"status": status, "path": path, "pk": 1})
        r = sqa.get(url)
        ok = r.status_code == 302 and reverse("home") in (r.url or "")
        check(f"student: /action/{status}/{path}/1/ -> redirect home", ok,
              f"status={r.status_code}, url={r.url}")

    print("=" * 70)
    print("QA 7: list.html — existing view/edit buttons open real pages")
    print("=" * 70)
    # В list.html кнопки: Subject v/e/d, ClassRoom v/e/d, User v/e/d, Quiz v/e/d,
    # Result d, Question d, Variant d, SelfQuestion e/d, SelfResult d.
    for tip, obj in [("subject", subject), ("classroom", classroom),
                     ("quiz", test_obj), ("user", admin)]:
        if obj is None:
            continue
        r = qa.get(reverse("dlist", kwargs={"tip": tip}))
        check(f"GET dlist {tip} -> 200", r.status_code == 200, f"status={r.status_code}")
        rv = qa.get(reverse("action", kwargs={"status": "view", "path": tip, "pk": obj.id}))
        check(f"view {tip} {obj.id} -> 200", rv.status_code == 200, f"status={rv.status_code}")

    print("=" * 70)
    print("QA 8: quiz_edit — json_script + JS DOM")
    print("=" * 70)
    if test_obj:
        r = qa.get(reverse("action", kwargs={"status": "edit", "path": "quiz", "pk": test_obj.id}))
        html = r.content.decode("utf-8", errors="replace")
        check("quiz_edit has json_script test-data", '"test-data"' in html and "json_script" in html)
        check("quiz_edit: #questionFields empty on server (JS builds DOM)",
              '<div id="questionFields" class="space-y-3"></div>' in html)
        check("quiz_edit has showToast", "showToast" in html)

    print("=" * 70)
    print("QA 10: showToast on validation error in edit forms")
    print("=" * 70)
    for path, obj in [("subject", subject), ("classroom", classroom)]:
        r = qa.post(reverse("action", kwargs={"status": "edit", "path": path, "pk": obj.id}), {})
        html = r.content.decode("utf-8", errors="replace")
        check(f"{path} edit: empty form -> 200 + showToast",
              r.status_code == 200 and "showToast" in html, f"status={r.status_code}")

    print("=" * 70)
    print("RESULT")
    print("=" * 70)
    print(f"PASS: {len(PASS)}  FAIL: {len(FAIL)}")
    for f in FAIL:
        print(f"  FAILED: {f}")
    sys.exit(0 if not FAIL else 1)


if __name__ == "__main__":
    main()
